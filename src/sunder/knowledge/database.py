import sqlite3
import json
from typing import List
from sunder.schema import CodeNode
import re
import logging

logger = logging.getLogger(__name__)

class KnowledgeDatabase:
    def __init__(self):
        # ':memory:' spins up an in-memory SQLite instance
        # Allow the connection to be used across multiple threads
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        # Query results are returned as row objects to allow access by column name
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

        logger.info("Initialized in-memory SQLite knowledge database")

    def _init_schema(self):
        cursor = self.conn.cursor()
        
        # Standard table for exact lookups and relationship maps
        cursor.execute("""
            CREATE TABLE code_nodes (
                node_id TEXT PRIMARY KEY,
                node_type TEXT,
                file_path TEXT,
                symbol_name TEXT,
                source_code TEXT,
                child_nodes TEXT,   
                parent_nodes TEXT,
                language TEXT
            )
        """)
        
        # FTS5 Virtual Table for fuzzy searching Target Functions
        cursor.execute("""
            CREATE VIRTUAL TABLE code_nodes_fts USING fts5(
                node_id UNINDEXED,
                symbol_name,
                tokenize='trigram case_sensitive 0'
            )
        """)
        self.conn.commit()

        logger.info("Created code_nodes table and FTS5 virtual table")

    def insert_nodes_batch(self, nodes: List[CodeNode]):
        """Inserts a batch of CodeNodes into both the standard and FTS5 tables in a single transaction."""
        if not nodes:
            logger.warning("Nodes not provided to insert")
            return

        logger.debug(f"Inserting batch of {len(nodes)} code nodes")
    
        cursor = self.conn.cursor()
        
        # Prepare data tuples for the code nodes table
        code_nodes_data = [
            (
                node.node_id,
                node.node_type,
                node.file_path,
                node.symbol_name,
                node.source_code,
                json.dumps(node.child_nodes),
                json.dumps(node.parent_nodes),
                node.language
            )
            for node in nodes
        ]
        
        # Prepare data tuples for the FTS5 table
        fts_data = [
            (
                node.node_id,
                node.symbol_name
            )
            for node in nodes
        ]
        
        # Execute both bulk inserts inside a single transaction block
        with self.conn:
            cursor.executemany("""
                INSERT INTO code_nodes (node_id, node_type, file_path, symbol_name, source_code, child_nodes, parent_nodes, language)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, code_nodes_data)
            
            cursor.executemany("""
                INSERT INTO code_nodes_fts (node_id, symbol_name)
                VALUES (?, ?)
            """, fts_data)

        logger.debug(f"Successfully inserted {len(nodes)} nodes")

    def get_node(self, node_id: str) -> CodeNode:
        """Fetches a single node by its ID."""
        if not node_id:
            logger.warning("Node not provided")
            return None

        logger.debug(f"Fetching node: {node_id}")

        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM code_nodes WHERE node_id = ?", (node_id,))
        row = cursor.fetchone()
        
        if not row:
            logger.warning(f"Node not found: {node_id}")
            return None
        return CodeNode(
            node_id=row["node_id"],
            node_type = row['node_type'],
            file_path=row["file_path"],
            symbol_name=row["symbol_name"],
            source_code=row["source_code"],
            child_nodes=json.loads(row["child_nodes"]),
            parent_nodes=json.loads(row["parent_nodes"]),
            language=row["language"]
        )

    def get_nodes(self, node_ids: List[str]) -> List[CodeNode]:
        """Fetches multiple nodes in a single DB roundtrip using an IN clause."""
        if not node_ids:
            logger.warning(f"Nodes not provided")
            return []
            
        cursor = self.conn.cursor()
        placeholders = ",".join("?" * len(node_ids))
        cursor.execute(f"SELECT * FROM code_nodes WHERE node_id IN ({placeholders})", tuple(node_ids))
        
        nodes = []
        for row in cursor.fetchall():
            nodes.append(CodeNode(
                node_id=row["node_id"],
                node_type = row['node_type'],
                file_path=row["file_path"],
                symbol_name=row["symbol_name"],
                source_code=row["source_code"],
                child_nodes=json.loads(row["child_nodes"]),
                parent_nodes=json.loads(row["parent_nodes"]),
                language=row["language"]
            ))

        logger.debug(f"Retrieved {len(nodes)} nodes")

        return nodes
 
    def fuzzy_search_symbols(self, query: str, limit: int = 10) -> List[tuple[str, str]]:
        """Used by the TUI for Human-In-The-Loop Target Disambiguation."""
        cursor = self.conn.cursor()

        # Sanitize query to prevent FTS5 syntax errors
        clean_query = query.strip().lower()
        if not clean_query:
            return []

        # Trigrams need 3 chars minimum. For short queries, we use LIKE.
        if len(clean_query) < 3:
            cursor.execute("""
                SELECT node_id, symbol_name FROM code_nodes_fts 
                WHERE symbol_name LIKE ? 
                ORDER BY length(symbol_name) ASC 
                LIMIT ?
            """, (f'%{clean_query}%', limit))
            
        # Pure trigram matching ordered by SQLite's internal BM25 ranking.
        else:
            # Extract only alphanumeric chunks to resolve FTS5 syntax vulnerabilities.
            parts = re.findall(r'\w+', clean_query)
            
            if not parts:
                return []

            clean_query = " ".join(parts)

            cursor.execute("""
                SELECT node_id, symbol_name FROM code_nodes_fts 
                WHERE symbol_name MATCH ? 
                ORDER BY rank 
                LIMIT ?
            """, (clean_query, limit))
        
        results = []
        for row in cursor.fetchall():
            results.append((row["node_id"], row["symbol_name"]))
        
        logger.debug(f"Found {len(results)} matches for '{query}'")

        return results