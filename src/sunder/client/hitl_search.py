from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Label, Input, OptionList
from textual.widgets.option_list import Option
import logging

logger = logging.getLogger(__name__)

class TargetExplorerPane(Vertical):
    """Pane for searching and selecting target functions from the AST database."""
    
    def compose(self) -> ComposeResult:
        yield Label("Target Explorer", classes="pane-title")
        yield Input(placeholder="Search function (e.g. verify_jwt)...", id="search-input")
        # An empty OptionList to hold our FTS5 results
        yield OptionList(id="target-results")

    async def on_input_changed(self, message: Input.Changed) -> None:
        """Triggered asynchronously whenever the user types in the search bar."""
        # Ensure the database has finished bootstrapping before allowing queries
        if not getattr(self.app, "knowledge_db", None):
            return
            
        search_query = message.value.strip()
        option_list = self.query_one("#target-results", OptionList)
        
        # Clear existing results on every keystroke
        option_list.clear_options()
        
        if not search_query:
            return

        try:
            # Query the KnowledgeDatabase with limit=5 as requested
            results = self.app.knowledge_db.fuzzy_search_symbols(search_query, limit=5)
            
            for node_id, symbol_name, node_type, file_path in results:
                # Format the text using Textual's Rich markup for clean visuals
                display_text = f"{symbol_name} [[dim]{node_type.upper()}[/dim]] \n  ↳ [dim italic]{file_path}[/dim]"
                
                # We store the node_id as the Option ID so we can retrieve the exact AST chunk later
                option_list.add_option(Option(display_text, id=node_id))
                
        except Exception as e:
            logger.error(f"AST Search failed: {e}")