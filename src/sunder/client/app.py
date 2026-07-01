from textual.app import App, ComposeResult
from textual.containers import Container, Vertical, Grid
from textual.widgets import (
    Header,
    Footer,
    Input,
    OptionList,
    RadioSet,
    RadioButton,
    Switch,
    TabbedContent,
    TabPane,
    RichLog,
    Label,
    Static,
)

class SunderApp(App):
    """The main unified interface for the Sunder application."""

    # Using Textual CSS with custom variables for coloring and grid layouts
    CSS = """
    /* --- Color Variables --- */
    $panel-bg: #1e1e1e;
    $border-idle: #444444;
    $border-focus: #00ff00;
    $text-muted: #888888;
    $accent: #00bcd4;

    /* --- Global Layout --- */
    Screen {
        background: $background;
    }

    #main-workspace {
        layout: grid;
        grid-size: 2 1; /* 2 columns, 1 row */
        grid-columns: 20% 80%; /* 20:80 sidebar to dashboard ratio */
        height: 100%;
        width: 100%;
    }

    /* --- Pane Styling --- */
    .pane {
        background: $panel-bg;
        border: round $border-idle;
        padding: 0 1;
        margin: 0 1;
    }

    .pane:focus-within {
        border: round $border-focus;
    }
    
    .pane-title {
        color: $accent;
        text-style: bold;
        margin-bottom: 1;
    }

    /* --- Sidebar: Target Explorer --- */
    #target-explorer {
        height: 15; /* Fixed small height for search bar and a few options */
    }
    
    #target-explorer Input {
        margin-bottom: 1;
    }

    /* --- Sidebar: Configuration --- */
    #sandbox-config {
        height: 1fr; /* Occupies the rest of the sidebar space */
    }

    .config-label {
        color: $text-muted;
        margin-top: 1;
    }

    /* --- Main Dashboard --- */
    #dashboard {
        height: 100%;
    }

    /* --- Telemetry Split View --- */
    #telemetry-grid {
        layout: grid;
        grid-size: 2 1;
        grid-columns: 1fr 1fr; /* 50/50 split for thoughts and logs */
        height: 100%;
    }

    #telemetry-grid RichLog {
        border: solid $border-idle;
        height: 100%;
    }
    
    #telemetry-grid RichLog:focus {
        border: solid $border-focus;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("s", "start_run", "Start Test"),
        ("tab", "focus_next", "Change Pane"),
    ]

    def compose(self) -> ComposeResult:
        """Compose the user interface."""
        yield Header(show_clock=True)
        
        with Container(id="main-workspace"):
            
            # --- LEFT COLUMN (20%) ---
            with Vertical(id="sidebar"):
                
                # Target Explorer (Small footprint)
                with Vertical(id="target-explorer", classes="pane"):
                    yield Label("🎯 Target Explorer", classes="pane-title")
                    yield Input(placeholder="Search function (e.g. verify_jwt)...")
                    # Placeholder options to show layout footprint
                    yield OptionList(
                        "verify_jwt [FUNC]", 
                        "AuthManager [CLASS]", 
                        "validate_payload [FUNC]"
                    )
                
                # Zero-Trust Config (Occupies majority of the sidebar)
                with Vertical(id="sandbox-config", classes="pane"):
                    yield Label("⚙️  Sandbox Config", classes="pane-title")
                    
                    yield Label("Execution Mode", classes="config-label")
                    with RadioSet():
                        yield RadioButton("Baseline Mode", value=True)
                        yield RadioButton("Adversarial Mode")
                    
                    yield Label("Network Access", classes="config-label")
                    yield Switch(value=False) # Zero-trust default
                    
                    yield Label("Memory Limit", classes="config-label")
                    yield Input(value="256m", placeholder="e.g. 512m")
                    
                    yield Label("CPU Quota", classes="config-label")
                    yield Input(value="1.0", placeholder="e.g. 0.5")

            # --- RIGHT COLUMN (80%) ---
            with Vertical(id="dashboard", classes="pane"):
                with TabbedContent(initial="tab-telemetry"):
                    
                    # Tab 1: Live Telemetry
                    with TabPane("Live Telemetry", id="tab-telemetry"):
                        with Grid(id="telemetry-grid"):
                            yield RichLog(id="agent-workspace", highlight=True, markup=True)
                            yield RichLog(id="docker-sandbox", highlight=True)
                    
                    # Tab 2: Code Context (Phase 1: Just Source)
                    with TabPane("Code Context", id="tab-context"):
                        yield Static("Source code for selected target will render here...")
                    
                    # Tab 3: Execution Report
                    with TabPane("Execution Report", id="tab-report"):
                        yield Static("Post-execution metrics and vulnerability verdicts will render here...")

        yield Footer()

if __name__ == "__main__":
    app = SunderApp()
    app.run()