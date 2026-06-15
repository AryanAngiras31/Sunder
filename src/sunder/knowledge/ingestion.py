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
        batch: List[CodeNode] = []
        
        logger.info(f"Found {len(filepath_language_dict)} files to ingest.")

        for filepath, lang in filepath_language_dict.items():
            # Read the bytes from the target file for parsing 
            try:
                with open(filepath, 'rb') as f:
                    source_bytes = f.read()
            except Exception as e:
                logger.warning(f"Could not read bytes for {filepath}:\n", e)
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
                logger.warning(f"Skipping {lang}: tags.scm is incompatible with the bundled grammar binary. ({e})")
                continue

            matches = def_query.matches(node = tree.root_node)

            # First create a record for every function 
            for match in matches:
                captures = match[1]
                
                # Find the specific definition key ('definition.function', 'definition.class', 'definition.method')
                def_key = next((k for k in captures.keys() if k.startswith('definition')), None)
                
                if 'name' not in captures or not def_key:
                    continue

                # Extract the specific tag type (e.g., 'function', 'class', 'struct', 'constant')
                tag_type = def_key.split('.')[-1]
                
                # Get node type
                if tag_type in {'function', 'macro'}:
                    node_type = NodeType.FUNCTION
                elif tag_type == 'method':
                    node_type = NodeType.METHOD
                elif tag_type in {'class', 'struct', 'interface', 'trait'}:
                    node_type = NodeType.CLASS
                else:
                    # Ignore constants, variables, types, modules, etc.
                    continue

                def_node = captures[def_key]
                name_node = captures['name']

                source_code = def_node.text.decode('utf-8')
                symbol_name = name_node.text.decode('utf-8')

                # Create a deterministic uuid by combining the fileapth and start byte with the function name
                rel_path = os.path.relpath(filepath, target_path)
                func_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{rel_path}:{def_node.start_byte}:{symbol_name}"))

                code_node = CodeNode(
                    node_id = func_id,
                    node_type=node_type,
                    file_path = rel_path,
                    symbol_name = symbol_name,
                    source_code = source_code,
                    child_nodes = [],
                    parent_nodes = [],
                    language = lang
                )

                # Batch insert the code nodes into the database
                batch.append(code_node)
                if len(batch) >= batch_size:
                    self.db.insert_nodes_batch(batch)
                    batch = []

        if batch:
            self.db.insert_nodes_batch(batch)

        logger.info("Ingestion Complete.")
