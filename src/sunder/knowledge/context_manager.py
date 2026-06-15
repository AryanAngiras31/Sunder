import tiktoken
from sunder.schema import BlastRadiusContext
import logging

logger = logging.getLogger(__name__)

class ContextManager:
    def __init__(self, max_tokens: int = 20000):
        self.max_tokens = max_tokens
        # Use OpenAI's standard encoder
        self.encoder = tiktoken.get_encoding("cl100k_base")

    def prune_context(self, context: BlastRadiusContext) -> BlastRadiusContext:
        """
        Automatically truncates retrieved context strictly in order of:
        Target > Immediate Children > Parents.
        """
        current_tokens = len(self.encoder.encode(context.target_node.source_code))
        
        if current_tokens > self.max_tokens:
            logger.warning(
                f"Target node {context.target_node.node_id} is ({current_tokens} tokens long, exceeding max limit of {self.max_tokens}."
            )
            # Target alone is too large (handled defensively)
            return BlastRadiusContext(
                target_node=context.target_node,
                children=[],
                parents=[]
            )

        # Prune the children so that they fit within the context window
        # Sort the children by increasing size to maximuze usage examples
        sorted_children = sorted(context.children, key=lambda c: len(c.source_code))

        pruned_children = []
        for child in sorted_children:
            child_tokens = len(self.encoder.encode(child.source_code))
            if current_tokens + child_tokens <= self.max_tokens:
                pruned_children.append(child)
                current_tokens += child_tokens
            else:
                break # Token limit reached
            
        # Prune the parents so that they fit within the context window
        # Sort the parents by increasing size to maximuze usage examples
        sorted_parents = sorted(context.parents, key=lambda p: len(p.source_code))

        pruned_parents = []
        if current_tokens < self.max_tokens:
            for parent in sorted_parents:
                parent_tokens = len(self.encoder.encode(parent.source_code))
                if current_tokens + parent_tokens <= self.max_tokens:
                    pruned_parents.append(parent)
                    current_tokens += parent_tokens
                else:
                    break # Token limit reached

        children_dropped = len(pruned_children) - len(context.children)
        parents_dropped = len(pruned_parents) - len(context.parents)
        if children_dropped > 0 or parents_dropped > 0:
            logger.debug(
                f"Token limit reached ({current_tokens}/{self.max_tokens})."
                f"Pruned {children_dropped} children and {parents_dropped} parents."
            )
        else:
            logger.debug(f"Context fits within budget. Total tokens: {current_tokens}/{self.max_tokens}")

        return BlastRadiusContext(
            target_node=context.target_node,
            children=pruned_children,
            parents=pruned_parents
        )