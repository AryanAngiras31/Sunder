import os
from typing import List
from sunder.schema import CodeNode, NodeType, EXTENSION_TO_LANGUAGE, SKIP_FOLDERS
from sunder.knowledge.database import KnowledgeDatabase
from tree_sitter_languages import get_parser, get_language
import uuid
import logging

logger = logging.getLogger(__name__)

class IngestionEngine:
    def __init__(self, db: KnowledgeDatabase):
        self.db = db

    def _get_files(self, target_path: str) -> List[str]:
        """
        Return all files that need to be parsed for knowledge extraction.
        """
        # Tuple of extensions of all supported languages
        valid_extensions = tuple(EXTENSION_TO_LANGUAGE.keys())
        filepath_language_dict = {}

        for root, dirs, files in os.walk(target_path):
            # Skip hidden directories and standard build folders
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in SKIP_FOLDERS]
            for file in files:
                ext = os.path.splitext(file)[1]
                if ext in valid_extensions:
                    # map path to language
                    filepath_language_dict[os.path.join(root, file)] = EXTENSION_TO_LANGUAGE[ext]
        return filepath_language_dict

    def ingest_repository(self, target_path: str, batch_size: int = 1000):
        """Parses the entire repository into AST chunks and inserts them into SQLite."""
        filepath_language_dict = self._get_files(target_path)
        
        logger.info(f"Found {len(filepath_language_dict)} files to ingest.")

        # In-memory structures for the 2-pass resolution
        node_id_to_node = {}         # UUID -> CodeNode
        symbol_to_node_ids = {}      # Symbol Name -> List of UUIDs 
        node_id_to_calls = {}        # Caller UUID -> Set of Called Symbol Names

        # Pass 1: Extract Definitions & References
        for filepath, lang in filepath_language_dict.items():
            # Read the bytes from the target file for parsing 
            try:
                with open(filepath, 'rb') as f:
                    source_bytes = f.read()
            except Exception as e:
                logger.warning(f"Could not read bytes for {filepath}:\n{e}")
                continue
            
            try:
                language = get_language(lang)
            except (AttributeError, Exception) as e:
                logger.warning(f"Skipping {lang}: Parser not bundled in tree_sitter_languages.")
                continue
            
            # Build AST for this file
            parser = get_parser(lang)
            tree = parser.parse(source_bytes)

            # Execute the corresponding query for every language supported
            query_tags_path = os.path.join(os.path.dirname(__file__), 'queries', lang, 'tags.scm')

            if not os.path.exists(query_tags_path):
                logger.warning(f"Missing tags.scm for {lang} at {query_tags_path}")
                continue
                
            with open(query_tags_path, 'r') as f:
                def_query_str = f.read()

            try:
                def_query = language.query(def_query_str)
            except Exception as e:
                logger.warning(f"Skipping {lang} file: tags.scm is incompatible with bundled grammar. ({e})")
                continue

            matches = def_query.matches(node=tree.root_node)

            file_definitions = []  # Tuples of (start_byte, end_byte, func_id)
            file_references = []   # Tuples of (start_byte, end_byte, symbol_name)

            for match in matches:
                captures = match[1]
                
                # Identify if this match is a definition or a reference call
                def_key = next((k for k in captures.keys() if k.startswith('definition')), None)
                ref_key = next((k for k in captures.keys() if k.startswith('reference')), None)
                
                if 'name' not in captures:
                    continue
                    
                name_node = captures['name']
                if isinstance(name_node, list): 
                    name_node = name_node[0]
                symbol_name = name_node.text.decode('utf-8')

                # --- Handle Definitions ---
                if def_key:
                    def_node = captures[def_key]
                    if isinstance(def_node, list): 
                        def_node = def_node[0]

                    tag_type = def_key.split('.')[-1]
                    if tag_type in {'function', 'macro'}:
                        node_type = NodeType.FUNCTION
                    elif tag_type == 'method':
                        node_type = NodeType.METHOD
                    elif tag_type in {'class', 'struct', 'interface', 'trait'}:
                        node_type = NodeType.CLASS
                    else:
                        continue

                    source_code = def_node.text.decode('utf-8')
                    rel_path = os.path.relpath(filepath, target_path)
                    func_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{rel_path}:{def_node.start_byte}:{symbol_name}"))

                    code_node = CodeNode(
                        node_id=func_id,
                        node_type=node_type,
                        file_path=rel_path,
                        symbol_name=symbol_name,
                        source_code=source_code,
                        child_nodes=[],  # Populated in Pass 2
                        parent_nodes=[], # Populated in Pass 2
                        language=lang
                    )

                    node_id_to_node[func_id] = code_node
                    symbol_to_node_ids.setdefault(symbol_name, []).append(func_id)
                    node_id_to_calls.setdefault(func_id, set())
                    
                    # Track byte boundaries so we can map references to this scope later
                    file_definitions.append((def_node.start_byte, def_node.end_byte, func_id))

                # --- Handle References (Function Calls) ---
                if ref_key:
                    ref_node = captures[ref_key]
                    if isinstance(ref_node, list): 
                        ref_node = ref_node[0]
                    file_references.append((ref_node.start_byte, ref_node.end_byte, symbol_name))

            # Ast Containment Check: Find which definition encapsulates each reference
            for ref_start, ref_end, called_symbol in file_references:
                enclosing_node_id = None
                min_size = float('inf')
                
                for def_start, def_end, func_id in file_definitions:
                    # If the reference's byte boundaries sit entirely inside a definition's boundaries
                    if def_start <= ref_start and def_end >= ref_end:
                        size = def_end - def_start
                        if size < min_size:
                            # Captures the narrowest scope (handles nested functions perfectly)
                            min_size = size
                            enclosing_node_id = func_id
                            
                if enclosing_node_id:
                    node_id_to_calls[enclosing_node_id].add(called_symbol)

        # Pass 2: Global Blast-Radius Resolution
        logger.info("Resolving relational parent/child Blast-Radius mapping...")
        
        for caller_id, called_symbols in node_id_to_calls.items():
            caller_node = node_id_to_node[caller_id]
            
            for symbol in called_symbols:
                # Find all known definition UUIDs for the called symbol
                callee_ids = symbol_to_node_ids.get(symbol, [])
                
                for callee_id in callee_ids:
                    # Prevent endless self-loops in the lists
                    if callee_id != caller_id:
                        
                        # 1. Add the callee UUID to the caller's 'child_nodes'
                        if callee_id not in caller_node.child_nodes:
                            caller_node.child_nodes.append(callee_id)
                            
                        # 2. Add the caller UUID to the callee's 'parent_nodes'
                        callee_node = node_id_to_node[callee_id]
                        if caller_id not in callee_node.parent_nodes:
                            callee_node.parent_nodes.append(caller_id)

        # Batch Database Insertion
        logger.info("Pushing resolved CodeNodes to the SQLite Database...")
        
        batch = []
        for node in node_id_to_node.values():
            batch.append(node)
            if len(batch) >= batch_size:
                self.db.insert_nodes_batch(batch)
                batch = []

        if batch:
            self.db.insert_nodes_batch(batch)

        logger.info("Ingestion Complete.")