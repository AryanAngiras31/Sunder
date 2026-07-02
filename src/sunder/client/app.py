import os
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Container, Vertical, Grid
from textual.widgets import (
    Header, 
    Footer, 
    Static, 
    TabbedContent, 
    TabPane,
    Input,
    OptionList,
    RadioSet,
    RadioButton,
    Switch,
    RichLog,
    Label
)

# Sunder Core Imports mapped directly to your codebase
from sunder.execution.bootstrapper import Bootstrapper
from sunder.knowledge.database import KnowledgeDatabase
from sunder.knowledge.ingestion import IngestionEngine

class SunderApp(App):
    """Sunder's primary LazyDocker-style TUI interface."""

    TITLE = "SUNDER"
    SUB_TITLE = "Zero-Trust Agentic Fuzzer"

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

    /* --- Sidebar Specifics --- */
    #target-explorer Input { margin-bottom: 1; }
    .config-label { margin-top: 1; color: #888888; }

    /* --- Right Column Workspace Specifics --- */
    #workspace-column { height: 100%; }
    TabbedContent { height: 100%; }
    
    #telemetry-grid {
        layout: grid;
        grid-size: 2 1;
        grid-columns: 1fr 1fr;
        height: 100%;
    }
    
    #telemetry-grid RichLog {
        border: solid $border-color;
        height: 100%;
    }
    
    #telemetry-grid RichLog:focus {
        border: solid $focus-border-color;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("tab", "app.focus_next", "Change Pane"),
        ("s", "start_run", "Start Run"),
        ("m", "toggle_mode", "Toggle Mode")
    ]

    def __init__(self):
        super().__init__()
        # State variables to hold Sunder components after boot
        self.image_tag = None
        self.knowledge_db = None

    def on_mount(self) -> None:
        """Fires immediately when the UI is drawn to the terminal."""
        self.notify("Starting Bootstrapper & Ingestion Engine...", title="Sunder Startup")
        self.initialize_sunder()

    @work(thread=True)
    def initialize_sunder(self) -> None:
        """Background thread to handle heavy Docker builds and AST parsing."""
        target_dir = os.getcwd() # Assumes the tool is executed from the repository root

        try:
            # 1. Execution Layer: Bootstrapper
            self.app.call_from_thread(self.notify, "Building .sunder/Dockerfile...", title="Bootstrapper")
            bootstrapper = Bootstrapper()
            # This handles building the image and returns the tag
            image_tag = bootstrapper.ensure_environment(target_dir) 
            self.image_tag = image_tag # Save to instance for the Orchestrator later

            # 2. Knowledge Layer: AST Ingestion
            self.app.call_from_thread(self.notify, "Parsing AST into SQLite...", title="Ingestion Engine")
            db = KnowledgeDatabase()
            ingestion_engine = IngestionEngine(db)
            # Parses the repo and populates FTS5
            ingestion_engine.ingest_repository(target_dir) 
            self.knowledge_db = db # Save to instance for the Target Explorer later

            # Initialization Success!
            self.app.call_from_thread(
                self.notify, 
                "Sunder is ready. Search for a target function to begin.", 
                title="System Ready 🟢", 
                severity="information"
            )

        except Exception as e:
            # Catch FileNotFoundError (missing Dockerfile), BuildError, etc.
            error_message = f"Startup Failed: {str(e)}"
            
            self.app.call_from_thread(
                self.notify, 
                error_message, 
                title="Fatal Error 🔴", 
                severity="error", 
                timeout=10
            )
            self.app.call_from_thread(self._log_system_error, error_message)

    def _log_system_error(self, message: str) -> None:
        """Safely writes system errors to the UI from the background thread."""
        try:
            agent_log = self.query_one("#agent-workspace", RichLog)
            agent_log.write(f"[bold red]SYSTEM ERROR:[/bold red] {message}")
            agent_log.write("Please check your terminal execution path, `.sunder/Dockerfile`, and Docker daemon.")
        except Exception:
            pass 

    def compose(self) -> ComposeResult:
        """Construct the UI hierarchy."""
        yield Header(show_clock=True)
        
        with Container(id="main-container"):
            
            # --- LEFT COLUMN: Control Sidebar ---
            with Container(id="sidebar-column"):
                
                with Vertical(classes="pane", id="target-explorer"):
                    yield Static("Target Explorer", classes="pane-title")
                    yield Input(placeholder="Search function (e.g. verify_jwt)...", id="search-input")
                    yield OptionList(id="target-results")
                
                with Vertical(classes="pane", id="sandbox-config"):
                    yield Static("Zero-Trust Config", classes="pane-title")
                    
                    yield Label("Execution Mode", classes="config-label")
                    with RadioSet(id="mode-toggle"):
                        yield RadioButton("Baseline (Seeding)", value=True)
                        yield RadioButton("Adversarial (Fuzzing)")
                    
                    yield Label("Network Access (Bridge)", classes="config-label")
                    yield Switch(value=False, id="network-switch")
                    
                    yield Label("Memory Limit", classes="config-label")
                    yield Input(value="512m", id="memory-input")

            # --- RIGHT COLUMN: Main Workspace ---
            with Container(classes="pane", id="workspace-column"):
                
                with TabbedContent():
                    with TabPane("Live Telemetry", id="tab-telemetry"):
                        with Grid(id="telemetry-grid"):
                            # Agent Workspace (Thoughts, Code) | Docker Logs (Stdout, Stderr)
                            yield RichLog(id="agent-workspace", highlight=True, markup=True)
                            yield RichLog(id="docker-sandbox", highlight=True)
                    
                    with TabPane("Code Context", id="tab-context"):
                        yield Static("Selected Target code will render here.", id="context-viewer")
                    
                    with TabPane("Execution Report", id="tab-report"):
                        yield Static("Verdict, JWTs, Mock IDs, and Stats.", id="report-viewer")

        yield Footer()

if __name__ == "__main__":
    app = SunderApp()
    app.run()