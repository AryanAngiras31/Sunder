from sunder.knowledge.database import KnowledgeDatabase
from sunder.schema import BlastRadiusContext, CodeNode

class ContextRetriever:
    def __init__(self, db: KnowledgeDatabase):
        self.db = db

    def get_blast_radius(self, target_node_id: str) -> BlastRadiusContext:
        """Fetches the Target, its Children (mock targets), and its Parents (usage examples)."""
        target_node = self.db.get_node(target_node_id)
        if not target_node:
            raise ValueError(f"Target node {target_node_id} not found in Knowledge Base.")

        children = self.db.get_nodes(target_node.child_nodes[:10])     # Limit to 10 children
        parents = self.db.get_nodes(target_node.parent_nodes[:5])      # Limit to 5 parents

        return BlastRadiusContext(
            target_node=target_node,
            children=children,
            parents=parents
        )