import os
import dotenv
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.containers import Vertical, Horizontal, VerticalScroll
from textual.widgets import Label, Input, Button

class CredentialsModal(ModalScreen[bool]):
    """A modal to manage Host LLM API Keys."""

    CSS = """
    $border-color: #2B2B2B;
    $focus-border-color: #82BDBD;
    $text-primary: #e0e0e0;
    $surface-color: #0D0D0D;

    CredentialsModal {
        align: center middle;
        background: $surface-color;
    }

    #cred-container {
        width: 50%;
        height: auto;
        background: $surface-color;
        border: round $border-color;
        padding: 1 1;
    }

    .cred-row { height: 3; margin-bottom: 0; }
    .cred-row Label { width: 20%; content-align: left middle; height: 100%; color: $text-primary; }
    .cred-row Input { width: 80%; background: $surface-color; border: round $border-color; }
    .cred-row Input:focus {
        border: round $border-color;
        background: transparent;
    }

    #cred-actions { height: 3; align: right middle; margin-top: 0;}
    #cred-actions Button { margin-left: 0; }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="cred-container"):
            yield Label("[bold]LLM Provider API Keys[/bold]\n[dim]Keys are saved locally to .sunder/.env.[/dim]\n")
            
            # Create masked inputs for the top providers
            providers = [
                ("OpenAI", "OPENAI_API_KEY"),
                ("OpenRouter", "OPENROUTER_API_KEY"),
                ("Google Gemini", "GEMINI_API_KEY"),
                ("DeepSeek", "DEEPSEEK_API_KEY"),
                ("Groq", "GROQ_API_KEY"),
                ("Mistral AI", "MISTRAL_API_KEY"),
                ("Cohere", "COHERE_API_KEY"),
                ("Together AI", "TOGETHER_API_KEY"),
                ("LangSmith API", "LANGCHAIN_API_KEY"),
                ("LangSmith Project", "LANGCHAIN_PROJECT"),
            ]
            
            for name, env_key in providers:
                with Horizontal(classes="cred-row"):
                    yield Label(f"[bold]{name}[/bold]")
                    # Pre-fill with existing key if it exists, but mask it
                    existing = os.environ.get(env_key, "")
                    
                    # Project names shouldn't be masked, but API keys should
                    is_password = "PROJECT" not in env_key
                    yield Input(value=existing, password=is_password, id=env_key, placeholder=f"Enter {name} Key...")

            with Horizontal(id="cred-actions"):
                yield Button("Save Keys", id="btn-save", variant="success")
                yield Button("Cancel", id="btn-cancel", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-save":
            # 1. Ensure .sunder directory and .env file exist safely
            sunder_dir = os.path.join(os.getcwd(), ".sunder")
            os.makedirs(sunder_dir, exist_ok=True) 
            
            env_path = os.path.join(sunder_dir, ".env")
            if not os.path.exists(env_path):
                open(env_path, 'a').close()

            # 2. Update os.environ and the .env file
            for input_widget in self.query(Input):
                key = input_widget.id
                val = input_widget.value.strip()
                if val:
                    os.environ[key] = val
                    dotenv.set_key(env_path, key, val)
                else:
                    os.environ.pop(key, None)
                    dotenv.unset_key(env_path, key)
                    
            # 3. Auto-enable LangSmith Tracing if API key was provided
            if os.environ.get("LANGCHAIN_API_KEY"):
                os.environ["LANGCHAIN_TRACING_V2"] = "true"
                dotenv.set_key(env_path, "LANGCHAIN_TRACING_V2", "true")
                # Default project name if they didn't supply one
                if not os.environ.get("LANGCHAIN_PROJECT"):
                    os.environ["LANGCHAIN_PROJECT"] = "Sunder"
                    dotenv.set_key(env_path, "LANGCHAIN_PROJECT", "Sunder")
            else:
                os.environ.pop("LANGCHAIN_TRACING_V2", None)
                dotenv.unset_key(env_path, "LANGCHAIN_TRACING_V2")
            
            self.app.notify("API Keys saved to .env", title="Credentials Updated")
            self.dismiss(True) 
            
        elif event.button.id == "btn-cancel":
            self.dismiss(False)