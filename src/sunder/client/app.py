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

# Sunder Core Imports
from sunder.execution.bootstrapper import Bootstrapper
from sunder.knowledge.database import KnowledgeDatabase
from sunder.knowledge.ingestion import IngestionEngine

# Import our newly created HITL Search Pane
from sunder.client.hitl_search import TargetExplorerPane

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

    Screen { background: #0b0b0b; }

    #main-container {
        layout: grid;
        grid-size: 2 1; 
        grid-columns: 3fr 7fr; 
        height: 100%;
        width: 100%;
    }

    #sidebar-column {
        layout: grid;
        grid-size: 1 2; 
        grid-rows: 6fr 4fr; 
        height: 100%;
    }

    .pane {
        border: round $border-color;
        background: $panel-bg;
        color: $text-primary;
        margin: 0 1 1 1;
        padding: 0 1;
    }

    .pane:focus-within { border: round $focus-border-color; }

    .pane-title {
        color: $accent-color;
        text-style: bold;
        margin-bottom: 1;
        content-align: center middle;
        width: 100%;
    }

    #target-explorer Input { margin-bottom: 1; }
    .config-label { margin-top: 1; color: #888888; }
    #workspace-column { height: 100%; }
    TabbedContent { height: 100%; }
    
    #telemetry-grid {
        layout: grid;
        grid-size: 2 1;
        grid-columns: 1fr 1fr;
        height: 100%;
    }
    
    #telemetry-grid RichLog { border: solid $border-color; height: 100%; }
    #telemetry-grid RichLog:focus { border: solid $focus-border-color; }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("tab", "app.focus_next", "Change Pane"),
        ("s", "start_run", "Start Run"),
        ("m", "toggle_mode", "Toggle Mode")
    ]

    def __init__(self):
        super().__init__()
        self.image_tag = None
        self.knowledge_db = None
        self.selected_target_id = None

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
            self.image_tag = bootstrapper.ensure_environment(target_dir) 

            # 2. Knowledge Layer: AST Ingestion
            self.app.call_from_thread(self.notify, "Parsing AST into SQLite...", title="Ingestion Engine")
            db = KnowledgeDatabase()
            ingestion_engine = IngestionEngine(db)
            ingestion_engine.ingest_repository(target_dir) 
            self.knowledge_db = db 

            self.app.call_from_thread(
                self.notify, 
                "Sunder is ready. Search for a target function to begin.", 
                title="System Ready 🟢", 
                severity="information"
            )
        except Exception as e:
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
        except Exception:
            pass 

    async def on_option_list_option_selected(self, message: OptionList.OptionSelected) -> None:
        """Fires when the user hits 'Enter' on an AST search result."""
        # Grab the node_id we tucked into the Option object
        self.selected_target_id = message.option.id
        
        # Fetch the full CodeNode from the database
        target_node = self.knowledge_db.get_node(self.selected_target_id)
        
        if target_node:
            # Shift UI focus to the Dashboard and open the Code Context tab
            tabs = self.query_one(TabbedContent)
            tabs.active = "tab-context"
            
            # Print the source code to the context viewer
            context_viewer = self.query_one("#context-viewer", Static)
            
            # Format nicely for the UI
            header = f"[bold cyan]Selected Target:[/bold cyan] {target_node.symbol_name} ({target_node.file_path})\n\n"
            context_viewer.update(header + target_node.source_code)
            
            self.notify(f"Target selected: {target_node.symbol_name}", title="Target Selected")

    def compose(self) -> ComposeResult:
        """Construct the UI hierarchy."""
        yield Header(show_clock=True)
        
        with Container(id="main-container"):
            
            # --- LEFT COLUMN: Control Sidebar ---
            with Container(id="sidebar-column"):
                
                # INJECTED HITL SEARCH PANE
                yield TargetExplorerPane(classes="pane", id="target-explorer")
                
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
                with TabbedContent(initial="tab-telemetry"):
                    with TabPane("Live Telemetry", id="tab-telemetry"):
                        with Grid(id="telemetry-grid"):
                            yield RichLog(id="agent-workspace", highlight=True, markup=True)
                            yield RichLog(id="docker-sandbox", highlight=True)
                    
                    with TabPane("Code Context", id="tab-context"):
                        # Now used to display the selected search target
                        yield Static("Search for a target to view its source code here.", id="context-viewer")
                    
                    with TabPane("Execution Report", id="tab-report"):
                        yield Static("Verdict, JWTs, Mock IDs, and Stats.", id="report-viewer")

        yield Footer()

if __name__ == "__main__":
    app = SunderApp()
    app.run()