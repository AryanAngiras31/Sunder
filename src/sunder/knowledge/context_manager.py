import tiktoken
from sunder.schema import BlastRadiusContext

class ContextManager:
    def __init__(self, max_tokens: int = 8000):
        self.max_tokens = max_tokens
        self.cur_tokens = 0
        # Use OpenAI's standard encoder
        self.encoder = tiktoken.get_encoding("cl100k_base")

    def prune_context(self, context: BlastRadiusContext) -> BlastRadiusContext:
        """
        Automatically truncates retrieved context strictly in order of:
        Target > Immediate Children > Parents.
        """
        self.cur_tokens = len(self.encoder.encode(context.target_node.source_code))
        
        if self.cur_tokens > self.max_tokens:
            # Target alone is too massive (edge case, but handled defensively)
            return BlastRadiusContext(
                target_node=context.target_node,
                children=[],
                parents=[]
            )

        pruned_children = []
        for child in context.children:
            child_tokens = len(self.encoder.encode(child.source_code))
            if self.cur_tokens + child_tokens <= self.max_tokens:
                pruned_children.append(child)
                self.cur_tokens += child_tokens
            else:
                break # Token limit reached

        pruned_parents = []
        if self.cur_tokens < self.max_tokens:
            for parent in context.parents:
                parent_tokens = len(self.encoder.encode(parent.source_code))
                if self.cur_tokens + parent_tokens <= self.max_tokens:
                    pruned_parents.append(parent)
                    self.cur_tokens += parent_tokens
                else:
                    break # Token limit reached

        return BlastRadiusContext(
            target_node=context.target_node,
            children=pruned_children,
            parents=pruned_parents
        )