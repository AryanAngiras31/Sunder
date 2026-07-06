import logging
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Input, OptionList, Button, Static
from textual.widgets.option_list import Option
from textual.message import Message
from litellm import model_cost
from sunder.client.credentials_modal import CredentialsModal

logger = logging.getLogger(__name__)

class RoleCard(Static):
    """Custom clickable card for the top 30% of the modal."""
    
    class RoleClicked(Message):
        def __init__(self, role_id: str):
            self.role_id = role_id
            super().__init__()

    def __init__(self, role_id: str, label: str, **kwargs):
        super().__init__(**kwargs)
        self.role_id = role_id
        self.label = label
        self.model_id = "-NA-"

    def render(self):
        # Uses Rich formatting for the title and dim small text
        return f"[bold cyan]{self.label}[/bold cyan]\n[dim]{self.model_id}[/dim]"

    def on_click(self) -> None:
        self.post_message(self.RoleClicked(self.role_id))
        
    def update_model(self, model_id: str):
        self.model_id = model_id
        self.refresh()


class ModelPickerModal(ModalScreen[dict]):
    """A 30:70 split modal to pick LangGraph models using LiteLLM."""
    
    CSS = """
    ModelPickerModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.85);
    }
    
    #picker-container {
        width: 85%;
        height: 85%;
        background: #1e1e1e;
        border: round #00ffff;
        padding: 0 0;
        layout: grid;
        grid-size: 3 3; 
        grid-columns: 1fr 1fr 1fr;
        grid-rows: 30% 1fr 3;
    }
    
    RoleCard {
        border: round #5a5a5a;
        background: #2a2a2a;
        content-align: center middle;
        height: 100%;
        margin: 0 0;
    }
    RoleCard:hover {
        background: #333333;
    }
    RoleCard.active {
        border: round #00ff00; 
    }
    
    #bottom-section {
        column-span: 3;
        layout: vertical;
        height: 100%;
        margin-top: 0;
        padding: 0 0;
    }
    
    #model-search {
        height: 3;
        border: round #5a5a5a;
        background: #2a2a2a;
        margin-bottom: 0;
    }
    #model-search:focus { border: round #00ff00; }
    
    #model-list {
        height: 1fr;
        border: round #5a5a5a;
        background: transparent;
    }
    #model-list:focus { border: round #00ff00; }
    
    #picker-actions {
        column-span: 3;
        align: right middle;
        height: 3;
        margin-top: 0;
        padding-right: 0;
    }
    #picker-actions Button { margin-left: 0; }
    """

    def __init__(self, current_selections: dict = None, **kwargs):
        super().__init__(**kwargs)
        self.model_selections = current_selections.copy() if current_selections else {
            "baseline": "-NA-",
            "adversarial": "-NA-",
            "evaluator": "-NA-"
        }
        self.active_role = "baseline"
        self.has_picked_first = False

    def compose(self) -> ComposeResult:
        with Container(id="picker-container"):
            yield RoleCard("baseline", "Baseline Coder", id="role-baseline", classes="active")
            yield RoleCard("adversarial", "Adversary Coder", id="role-adversarial")
            yield RoleCard("evaluator", "Evaluator Node", id="role-evaluator")
            
            with Vertical(id="bottom-section"):
                yield Input(placeholder="Search Model Registry", id="model-search")
                yield OptionList(id="model-list")

            with Horizontal(id="picker-actions"):
                    yield Button("Manage API Keys", id="btn-keys", variant="primary") 
                    yield Button("Save & Close", id="btn-start", variant="success")
                    yield Button("Cancel", id="btn-cancel", variant="error")

    def on_mount(self) -> None:
        self._populate_list("")
        # Pre-populate the cards if there are existing selections passed from app.py
        for role_id, model_id in self.model_selections.items():
            if model_id != "-NA-":
                for card in self.query(RoleCard):
                    if card.role_id == role_id:
                        card.update_model(model_id)
        
    def set_active_role(self, role_id: str):
        self.active_role = role_id
        for card in self.query(RoleCard):
            if card.role_id == role_id:
                card.add_class("active")
            else:
                card.remove_class("active")

    def on_role_card_role_clicked(self, message: RoleCard.RoleClicked) -> None:
        self.set_active_role(message.role_id)

    def _get_available_providers(self) -> set:
        """Determines which provider prefixes to show based on available API keys."""
        import os
        
        available = {"ollama"} 
        
        if os.environ.get("OPENAI_API_KEY"):
            available.add("openai")
        if os.environ.get("ANTHROPIC_API_KEY"):
            available.add("anthropic")
        if os.environ.get("OPENROUTER_API_KEY"):
            available.add("openrouter")
        if os.environ.get("GROQ_API_KEY"):
            available.add("groq")
        if os.environ.get("MISTRAL_API_KEY"):
            available.add("mistral")
        if os.environ.get("COHERE_API_KEY"):
            available.add("cohere")
        if os.environ.get("TOGETHER_API_KEY"):
            available.add("together_ai")
        if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
            available.update(["gemini", "vertex_ai"])
            
        return available

    def _populate_list(self, search_term: str) -> None:
        option_list = self.query_one("#model-list", OptionList)
        option_list.clear_options()
        search_term = search_term.lower()

        # Fetch the set of providers the user is actually allowed to use
        available_providers = self._get_available_providers()
        
        options = []
        for model_id, data in model_cost.items():
            # Extract the provider prefix from the LiteLLM string (e.g. 'openai' from 'openai/gpt-4o')
            provider = model_id.split("/")[0] if "/" in model_id else "unknown"
            
            # If the user doesn't have the key, don't show the model.
            if provider not in available_providers:
                continue

            if search_term in model_id.lower():
                cost = data.get('input_cost_per_token', 0)
                max_tokens = data.get('max_tokens', 'Unknown')
                display = f"[bold]{model_id}[/bold] [dim italic]- Context: {max_tokens} | Cost/1M Tokens: ${cost*10**6:.2f}[/dim italic]"
                options.append(Option(display, id=model_id))
                
        for opt in options:
            option_list.add_option(opt)

    def on_input_changed(self, message: Input.Changed) -> None:
        """Trigger fuzzy search as the user types."""
        self._populate_list(message.value)

    def on_option_list_option_selected(self, message: OptionList.OptionSelected) -> None:
        model_id = message.option_id
        if not model_id:
            return
            
        if not self.has_picked_first:
            # First pick copies everywhere
            self.model_selections["baseline"] = model_id
            self.model_selections["adversarial"] = model_id
            self.model_selections["evaluator"] = model_id
            self.has_picked_first = True
            
            for card in self.query(RoleCard):
                card.update_model(model_id)
                
            # Auto-advance focus to the next logical role
            self.set_active_role("adversarial")
        else:
            self.model_selections[self.active_role] = model_id
            for card in self.query(RoleCard):
                if card.role_id == self.active_role:
                    card.update_model(model_id)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-keys":
            def on_keys_closed(keys_changed: bool):
                if keys_changed:
                    self._populate_list(self.query_one("#model-search", Input).value)
            
            self.app.push_screen(CredentialsModal(), on_keys_closed)
        elif event.button.id == "btn-start":
            if any(v == "-NA-" for v in self.model_selections.values()):
                self.app.notify("Please select models for all 3 roles before saving.", title="Incomplete", severity="error")
                return
            self.dismiss(self.model_selections)
        elif event.button.id == "btn-cancel":
            self.dismiss(None)