from textual.app import App, ComposeResult
from textual.containers import Container, Vertical
from textual.widgets import Header, Footer, Static, TabbedContent, TabPane, Placeholder

class SunderApp(App):
    """Sunder's primary LazyDocker-style TUI interface."""

    TITLE = "SUNDER"
    SUB_TITLE = "Zero-Trust Agentic Fuzzer"

    # Define the UI theme and grid layout using Textual CSS (TCSS)
    CSS = """
    /* --- CSS Variables for Theming --- */
    $border-color: #5a5a5a;
    $focus-border-color: #00ff00;
    $panel-bg: #1e1e1e;
    $text-primary: #e0e0e0;
    $accent-color: #00ffff;

    /* --- Base Screen --- */
    Screen {
        background: #0b0b0b;
    }

    /* --- Main Grid Layout --- */
    #main-container {
        layout: grid;
        grid-size: 2 1; /* 2 columns, 1 row */
        grid-columns: 3fr 7fr; /* 30% left sidebar, 70% right workspace */
        height: 100%;
        width: 100%;
    }

    /* --- Left Column: Control Sidebar --- */
    #sidebar-column {
        layout: grid;
        grid-size: 1 2; /* 1 column, 2 rows */
        grid-rows: 6fr 4fr; /* Target explorer is slightly taller than Config */
        height: 100%;
    }

    /* --- Universal Pane Styling --- */
    .pane {
        border: round $border-color;
        background: $panel-bg;
        color: $text-primary;
        margin: 0 1 1 1;
        padding: 0 1;
    }

    /* Glowing effect when a pane (or a widget inside it) is focused */
    .pane:focus-within {
        border: round $focus-border-color;
    }

    .pane-title {
        color: $accent-color;
        text-style: bold;
        margin-bottom: 1;
        content-align: center middle;
        width: 100%;
    }

    /* --- Right Column Workspace Specifics --- */
    #workspace-column {
        height: 100%;
    }
    
    TabbedContent {
        height: 100%;
    }
    """

    # Global Hotkeys map directly to the Footer and trigger App-level events
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("tab", "app.focus_next", "Change Pane"),
        ("s", "start_run", "Start Run"),
        ("m", "toggle_mode", "Toggle Mode")
    ]

    def compose(self) -> ComposeResult:
        """Construct the UI hierarchy."""
        
        yield Header(show_clock=True)
        
        with Container(id="main-container"):
            
            # --- LEFT COLUMN: Control Sidebar ---
            with Container(id="sidebar-column"):
                
                # Pane 1: Target Explorer
                with Vertical(classes="pane", id="target-explorer"):
                    yield Static("🎯 Target Explorer", classes="pane-title")
                    yield Placeholder("Search Bar & AST Node List here")
                
                # Pane 2: Sandbox Config
                with Vertical(classes="pane", id="sandbox-config"):
                    yield Static("🛡️ Zero-Trust Config", classes="pane-title")
                    yield Placeholder("Network / Host / Memory Toggles here")

            # --- RIGHT COLUMN: Main Workspace ---
            with Container(classes="pane", id="workspace-column"):
                
                with TabbedContent():
                    # Tab 1: Live Telemetry (Split Grid)
                    with TabPane("Live Telemetry", id="tab-telemetry"):
                        yield Placeholder("Split View: LLM Output (Left) | Docker Logs (Right)")
                    
                    # Tab 2: Code Context
                    with TabPane("Code Context", id="tab-context"):
                        yield Placeholder("Read-Only Source Code Viewer")
                    
                    # Tab 3: Execution Report
                    with TabPane("Execution Report", id="tab-report"):
                        yield Placeholder("Verdict, JWTs, Mock IDs, and Stats")

        yield Footer()

if __name__ == "__main__":
    app = SunderApp()
    app.run()