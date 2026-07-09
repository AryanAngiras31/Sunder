from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.containers import Vertical, Horizontal
from textual.widgets import Label, RadioSet, RadioButton, Switch, Input, Button, TextArea
from sunder.schema import SandboxProfile, NetworkMode, AgentMode
import logging

logger = logging.getLogger(__name__)

class EnvVarModal(ModalScreen[dict]):
    """A pop-up modal to input custom Environment Variables safely."""
    
    CSS = """
    $border-color: #2B2B2B;
    $focus-border-color: #82BDBD;
    $text-primary: #e0e0e0;
    $surface-color: #0D0D0D;
    
    EnvVarModal {
        align: center middle;
        background: $surface-color;
    }
    #env-modal-container {
        width: 50%;
        height: 50%;
        background: $surface-color;
        border: round $border-color;
        padding: 0 1;
    }
    #env-buttons {
        height: auto;
        margin-top: 0;
        align: right middle;
    }
    #env-buttons Button { margin-left: 1; }
    """

    def __init__(self, current_env: dict, **kwargs):
        super().__init__(**kwargs)
        self.current_env = current_env

    def compose(self) -> ComposeResult:
        with Vertical(id="env-modal-container"):
            yield Label("Inject Environment Variables (KEY=VALUE per line)", classes="pane-title")
            
            # Pre-fill the text area with any previously saved variables
            initial_text = "\n".join(f"{k}={v}" for k, v in self.current_env.items())
            yield TextArea(initial_text, id="env-text-area")
            
            with Horizontal(id="env-buttons"):
                yield Button("Save", id="save-env-btn", variant="success")
                yield Button("Cancel", id="cancel-env-btn", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle save and cancel actions."""
        if event.button.id == "save-env-btn":
            text = self.query_one("#env-text-area", TextArea).text
            env_dict = {}
            for line in text.splitlines():
                if "=" in line:
                    key, val = line.split("=", 1)
                    env_dict[key.strip()] = val.strip()
            self.dismiss(env_dict) # Return dictionary back to ConfigPanel
        else:
            self.dismiss(self.current_env) # Cancel changes


class ConfigPanel(Vertical):
    """The Zero-Trust Sandbox Configuration Panel mapped to SandboxProfile schema."""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Store internal state of injected variables
        self.env_vars = {}

    def compose(self) -> ComposeResult:
        yield Label("Zero-Trust Config", classes="pane-title")
        
        yield Label("Execution Mode", classes="config-label")
        with RadioSet(id="mode-toggle"):
            yield RadioButton("Baseline (Seeding)", value=True, id="mode-baseline")
            yield RadioButton("Adversarial (Fuzzing)", id="mode-adversarial")
        
        yield Label("Network Access (Bridge)", classes="config-label")
        yield Switch(value=False, id="network-switch")
        
        yield Label("Memory Limit", classes="config-label")
        yield Input(value="512m", id="memory-input")
        
        yield Label("CPU Quota", classes="config-label")
        yield Input(value="1.0", id="cpu-input")
        
        yield Label("Timeout (Seconds)", classes="config-label")
        yield Input(value="30", id="timeout-input")
        
        yield Button("Inject Env Vars", id="env-var-btn", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Open the Modal when the inject button is clicked."""
        if event.button.id == "env-var-btn":
            def update_env(env: dict):
                self.env_vars = env
                if env:
                    self.app.notify(f"Injected {len(env)} environment variables.", title="Config Updated")

            # Push the modal screen onto the UI stack
            self.app.push_screen(EnvVarModal(self.env_vars), update_env)

    def get_current_mode(self) -> AgentMode:
        """Returns the AgentMode enum based on the radio toggle."""
        radio_set = self.query_one("#mode-toggle", RadioSet)
        if radio_set.pressed_button and radio_set.pressed_button.id == "mode-adversarial":
            return AgentMode.ADVERSARIAL
        return AgentMode.BASELINE

    def get_sandbox_profile(self, custom_image: str = None) -> SandboxProfile:
        """Extracts UI state and enforces it into the Pydantic SandboxProfile schema."""
        network_switch = self.query_one("#network-switch", Switch).value
        network_mode = NetworkMode.BRIDGE if network_switch else NetworkMode.NONE
        
        memory_limit = self.query_one("#memory-input", Input).value
        
        try:
            cpu_quota = float(self.query_one("#cpu-input", Input).value)
        except ValueError:
            cpu_quota = 1.0
            
        try:
            timeout_seconds = int(self.query_one("#timeout-input", Input).value)
        except ValueError:
            timeout_seconds = 30

        return SandboxProfile(
            network_mode=network_mode,
            memory_limit=memory_limit,
            cpu_quota=cpu_quota,
            timeout_seconds=timeout_seconds,
            environment_vars=self.env_vars,
            custom_image=custom_image
        )