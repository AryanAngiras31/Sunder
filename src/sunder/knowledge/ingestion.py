import os
from typing import Dict, List
from sunder.knowledge.code_hierarchy import CodeHierarchyNodeParser
from sunder.schema import CodeNode, EXTENSION_TO_LANGUAGE, SKIP_FOLDERS
from sunder.knowledge.database import KnowledgeDatabase
import logging
import tree_sitter
from tree_sitter_languages import get_parser 
import uuid

class IngestionEngine:
    def __init__(self, db: KnowledgeDatabase):
        self.db = db

    def _get_files(self, target_path: str) -> List[str]:
        """
        Return all files that need to be parsed for knowledge extraction.
        """
        valid_extensions = tuple(EXTENSION_TO_LANGUAGE.keys())
        filepath_language_dict = {}
        for root, dirs, files in os.walk(target_path):
            # Skip hidden directories and standard build folders
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in SKIP_FOLDERS]
            for file in files:
                ext = f".{file.split('.')[-1]}"
                if ext in valid_extensions:
                    # map path to language
                    filepath_language_dict[os.path.join(root, file)] = EXTENSION_TO_LANGUAGE[ext]
        return filepath_language_dict

    def ingest_repository(self, target_path: str, batch_size: int = 1000):
        """Parses the entire repository into AST chunks and inserts them into SQLite."""
        filepath_language_dict = self._get_files(target_path)
        batch: List[CodeNode] = []
        
        logging.info(f"Found {len(filepath_language_dict)} files to ingest.")

        for filepath, lang in filepath_language_dict.items():
            # Read the bytes from the target file for parsing 
            try:
                with open(filepath, 'rb') as f:
                    source_bytes = f.read()
            except Exception as e:
                logging.warning(f"Could not read bytes for {filepath}:\n", e)
                continue

            # Create AST for a particular file 
            parser = get_parser(lang)
            tree = parser.parse(source = source_bytes)

            # Execute the corresponding query for every language supported
            language = get_language(lang)
            query_tags_path = os.path.join('queries', lang, 'tags.scm')

            if not os.path.exists(query_tags_path):
                logging.warning(f"Missing tags.scm for {lang} at {query_path}")
                continue
            with open(query_tags_path, 'r') as f:
                def_query_str = f.read()

            def_query = language.query(def_query_str)
            matches = def_query.matches(node = tree.root_node)

            # First create a record for every function 
            filename = os.path.basename(filepath)
            for match in matches:
                captures = match[1]
                if 'definition.function' or 'name' not in captures:
                    continue

                def_node = captures['definition.function'][0]
                name_node = captures['name'][0]

                source_code = def_node.text.decode('utf-8')
                symbol_name = name_node.text.decode('utf-8')

                # Create a deterministic uuid by combining the filename with the function name
                func_id = uuid.uuid5(namespace = uuid.NAMESPACE_URL, name = f"{filename}:{symbol_name}")

                code_node = CodeNode(
                    node_id = func_id,
                    file_path = filepath,
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
            
        logging.info("Ingestion Complete.")
