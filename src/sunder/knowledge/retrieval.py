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

        children = []
        for child_id in target_node.child_nodes:
            child = self.db.get_node(child_id)
            if child:
                children.append(child)

        parents = []
        for parent_id in target_node.parent_nodes:
            parent = self.db.get_node(parent_id)
            if parent:
                parents.append(parent)

        return BlastRadiusContext(
            target_node=target_node,
            children=children,
            parents=parents
        )