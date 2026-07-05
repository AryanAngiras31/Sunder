import os
import dotenv
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.containers import Vertical, Horizontal, VerticalScroll
from textual.widgets import Label, Input, Button

class CredentialsModal(ModalScreen[bool]):
    """A modal to manage Host LLM API Keys."""

    CSS = """
    CredentialsModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.85);
    }
    #cred-container {
        width: 50%;
        height: auto;
        background: #1e1e1e;
        border: round #00ffff;
        padding: 1 2;
    }
    .cred-row { height: 3; margin-bottom: 1; }
    .cred-row Label { width: 20%; content-align: left middle; height: 100%; color: #00ffff; }
    .cred-row Input { width: 80%; }
    #cred-actions { height: 3; align: right middle; margin-top: 1;}
    #cred-actions Button { margin-left: 1; }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="cred-container"):
            yield Label("[bold]LLM Provider API Keys[/bold]\n[dim]Keys are saved locally to .sunder/.env.[/dim]\n")
            
            # Create masked inputs for the top providers
            providers = [
                ("OpenAI", "OPENAI_API_KEY"),
                ("Anthropic", "ANTHROPIC_API_KEY"),
                ("OpenRouter", "OPENROUTER_API_KEY"),
                ("Google Gemini", "GEMINI_API_KEY"),
                ("Groq", "GROQ_API_KEY"),
                ("Mistral AI", "MISTRAL_API_KEY"),
                ("Cohere", "COHERE_API_KEY"),
                ("Together AI", "TOGETHER_API_KEY"),
                ("Fireworks AI", "FIREWORKS_API_KEY"),
                ("HuggingFace", "HF_TOKEN"),
                ("Azure OpenAI", "AZURE_OPENAI_API_KEY"),
            ]
            
            with VerticalScroll():
                for name, env_key in providers:
                    with Horizontal(classes="cred-row"):
                        yield Label(name)
                        # Pre-fill with existing key if it exists, but mask it
                        existing = os.environ.get(env_key, "")
                        yield Input(value=existing, password=True, id=env_key, placeholder=f"Enter {name} key...")

            with Horizontal(id="cred-actions"):
                yield Button("Save Keys", id="btn-save", variant="success")
                yield Button("Cancel", id="btn-cancel", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-save":
            # 1. Ensure .env file exists
            env_path = os.path.join(os.getcwd(), ".sunder/.env")
            if not os.path.exists(env_path):
                open(env_path, 'a').close()

            # 2. Update os.environ and the .env file
            for input_widget in self.query(Input):
                key = input_widget.id
                val = input_widget.value.strip()
                if val:
                    os.environ[key] = val
                    dotenv.set_key(env_path, key, val)
            
            self.app.notify("API Keys saved to .env", title="Credentials Updated")
            self.dismiss(True) # Return True to indicate keys changed
            
        elif event.button.id == "btn-cancel":
            self.dismiss(False)