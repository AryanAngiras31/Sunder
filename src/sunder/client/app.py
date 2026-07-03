import os
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Container, Vertical, Grid
from textual.widgets import Header, Footer, Static, TabbedContent, TabPane, RichLog

# Sunder Core Imports
from sunder.execution.bootstrapper import Bootstrapper
from sunder.knowledge.database import KnowledgeDatabase
from sunder.knowledge.ingestion import IngestionEngine

# TUI Components
from sunder.client.hitl_search import TargetExplorerPane
from sunder.client.config_panel import ConfigPanel

class SunderApp(App):
    """Sunder's primary LazyDocker-style TUI interface."""

    TITLE = "SUNDER"
    SUB_TITLE = "Zero-Trust Agentic Fuzzer"

    CSS = """
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
        height: 100%; width: 100%;
    }
    #sidebar-column {
        layout: grid;
        grid-size: 1 2; 
        grid-rows: 4fr 6fr; /* Config Panel needs a bit more space now */
        height: 100%;
    }
    .pane {
        border: round $border-color; background: $panel-bg;
        color: $text-primary; margin: 0 1 1 1; padding: 0 1;
    }
    .pane:focus-within { border: round $focus-border-color; }
    .pane-title {
        color: $accent-color; text-style: bold;
        margin-bottom: 1; content-align: center middle; width: 100%;
    }
    #target-explorer Input { margin-bottom: 1; }
    .config-label { margin-top: 1; color: #888888; }
    
    #env-var-btn { margin-top: 1; width: 100%; }

    #workspace-column { height: 100%; }
    TabbedContent { height: 100%; }
    
    #telemetry-grid {
        layout: grid; grid-size: 2 1; grid-columns: 1fr 1fr; height: 100%;
    }
    #telemetry-grid RichLog { border: solid $border-color; height: 100%; }
    #telemetry-grid RichLog:focus { border: solid $focus-border-color; }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("tab", "app.focus_next", "Change Pane"),
        ("s", "start_run", "Start Run")
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
            self.app.call_from_thread(self.notify, error_message, title="Fatal Error 🔴", severity="error", timeout=15)

    async def on_option_list_option_selected(self, message) -> None:
        """Fires when the user hits 'Enter' on an AST search result."""
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

    def action_start_run(self) -> None:
        """Triggered via the [s] hotkey."""
        if not self.selected_target_id:
            self.notify("Please select a target function first.", title="Error", severity="error")
            return
            
        config_panel = self.query_one(ConfigPanel)
        mode = config_panel.get_current_mode()
        profile = config_panel.get_sandbox_profile(custom_image=self.image_tag)
        
        # Log to telemetry to verify everything is hooked up
        agent_log = self.query_one("#agent-workspace", RichLog)
        agent_log.clear()
        agent_log.write(f"[bold green]Initiating LangGraph Orchestrator...[/bold green]")
        agent_log.write(f"Mode: [cyan]{mode.value}[/cyan]")
        agent_log.write(f"Network: [cyan]{profile.network_mode.value}[/cyan]")
        agent_log.write(f"Limits: RAM={profile.memory_limit}, CPU={profile.cpu_quota}, Timeout={profile.timeout_seconds}s")
        agent_log.write(f"Injected Env Vars: {len(profile.environment_vars)}")
        
        self.notify(f"Starting {mode.value} execution loop...", title="Run Started")
        
        # PHASE 2 TODO: Call Orchestrator passing the selected target and profile schemas.

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        
        with Container(id="main-container"):
            with Container(id="sidebar-column"):
                yield TargetExplorerPane(classes="pane", id="target-explorer")
                
                # INJECTED CONFIG PANEL
                yield ConfigPanel(classes="pane", id="sandbox-config")

            with Container(classes="pane", id="workspace-column"):
                with TabbedContent(initial="tab-telemetry"):
                    with TabPane("Live Telemetry", id="tab-telemetry"):
                        with Grid(id="telemetry-grid"):
                            yield RichLog(id="agent-workspace", highlight=True, markup=True)
                            yield RichLog(id="docker-sandbox", highlight=True)
                    
                    with TabPane("Code Context", id="tab-context"):
                        yield Static("Search for a target to view its source code here.", id="context-viewer")
                    
                    with TabPane("Execution Report", id="tab-report"):
                        yield Static("Verdict, JWTs, Mock IDs, and Stats.", id="report-viewer")

        yield Footer()

if __name__ == "__main__":
    app = SunderApp()
    app.run()