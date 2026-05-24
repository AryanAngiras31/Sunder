import os
from typing import Dict, List
from llama_index.core import Document
from llama_index.core.schema import NodeRelationship
from llama_index.core.node_parser import CodeHierarchyNodeParser
from sunder.schema import CodeNode, EXTENSION_TO_LANGUAGE, SKIP_FOLDERS
from sunder.knowledge.database import KnowledgeDatabase

class IngestionEngine:
    def __init__(self, db: KnowledgeDatabase):
        self.db = db

    def _get_files(self, target_path: str) -> List[str]:
        """
        Return all files that need to be parsed for knowledge extraction.
        """
        valid_extensions = tuple(EXTENSION_TO_LANGUAGE.keys())
        filepaths = []
        for root, dirs, files in os.walk(target_path):
            # Skip hidden directories and standard build folders
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in SKIP_FOLDERS]
            for file in files:
                if file.endswith(valid_extensions):
                    filepaths.append(os.path.join(root, file))
        return filepaths

    def ingest_repository(self, target_path: str, batch_size: int = 1000):
        """Parses the entire repository into AST chunks and inserts them into SQLite."""
        filepaths = self._get_files(target_path)
        
        # Group documents by language for the parser
        docs_by_lang: Dict[str, List[Document]] = {}
        
        for path in filepaths:
            ext = os.path.splitext(path)[1]
            language = EXTENSION_TO_LANGUAGE.get(ext)
            if not language:
                continue
                
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
            except UnicodeDecodeError:
                continue # Skip binaries or malformed encodings
                
            doc = Document(
                text=content,
                metadata={"file_path": os.path.relpath(path, target_path)}
            )
            docs_by_lang.setdefault(language, []).append(doc)

        # Active batch memory cache
        batch: List[CodeNode] = []

        # Parse and ingest per language
        for language, docs in docs_by_lang.items():
            parser = CodeHierarchyNodeParser(language=language)
            llama_nodes = parser.get_nodes_from_documents(docs)
            
            for l_node in llama_nodes:
                # Extract relationships
                child_ids = [rel.node_id for rel in l_node.relationships.get(NodeRelationship.CHILD, [])]
                parent_ids = [rel.node_id for rel in l_node.relationships.get(NodeRelationship.PARENT, [])]
                
                # Sunder defines 'symbol_name' as the structural signature
                symbol_name = l_node.metadata.get("inclusive_scopes", [{}])[-1].get("name", "global_scope")
                
                code_node = CodeNode(
                    node_id=l_node.node_id,
                    file_path=l_node.metadata.get("file_path"),
                    symbol_name=symbol_name,
                    source_code=l_node.text,
                    child_nodes=child_ids,
                    parent_nodes=parent_ids,
                    language=language
                )
                batch.append(code_node)

                # Insert batch when it reaches the specified size
                if len(batch) >= batch_size:
                    self.db.insert_nodes_batch(batch)
                    batch.clear()
        # Flush any remaining nodes left over in the final partial batch
        if batch:
            self.db.insert_nodes_batch(batch)
