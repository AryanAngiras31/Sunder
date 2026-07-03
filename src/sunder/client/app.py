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
from sunder.client.dashboard import TelemetryDashboard

class SunderApp(App):
    """Sunder's primary LazyDocker-style TUI interface."""

    TITLE = "SUNDER"
    SUB_TITLE = "Zero-Trust Agentic Fuzzer"

    CSS = """
    $border-color: #5a5a5a;
    $focus-border-color: #00ff00;
    $text-primary: #e0e0e0;
    $accent-color: #00ffff;

    Screen { background: #0b0b0b; }

    #main-container {
        layout: grid;
        grid-size: 2 1; 
        grid-columns: 3fr 7fr; 
        height: 100%; width: 100%;
        padding: 0 1; 
    }
    #sidebar-column {
        layout: grid;
        grid-size: 1 2; 
        grid-rows: 18 1fr; 
        height: 100%;
    }
    .pane {
        border: round $border-color; 
        background: transparent;
        color: $text-primary; 
        margin: 0; 
        padding: 0 1;
    }
    .pane:focus-within { border: round $focus-border-color; }
    .pane-title {
        color: $accent-color; text-style: bold;
        margin-bottom: 1; content-align: center middle; width: 100%;
    }
    #target-explorer Input { margin-bottom: 1; }
    
    /* --- COMPACT CONFIG PANEL --- */
    .config-label { 
        margin: 0; 
        color: #888888; 
    }
    
    #mode-toggle, #sandbox-config Input, #network-switch, #env-var-btn {
        border: round $border-color;
        background: transparent;
        margin: 0;
        margin-bottom: 1; 
    }

    #mode-toggle:focus-within, #sandbox-config Input:focus, #network-switch:focus, #env-var-btn:focus, #env-var-btn:hover {
        border: round $focus-border-color;
    }

    #mode-toggle {
        height: auto;
        padding: 0;
    }

    #sandbox-config Input, #network-switch {
        height: 3; 
        padding: 0 1;
    }

    #env-var-btn {
        width: 100%;
        height: 3;
        color: $accent-color;
        content-align: center middle;
    }
    #env-var-btn:hover, #env-var-btn:focus {
        color: $focus-border-color;
        text-style: bold;
    }

    /* --- TELEMETRY DASHBOARD OVERRIDES --- */
    #workspace-column { 
        height: 100%; 
        padding: 1; 
    }
    
    TelemetryDashboard {
        height: 100%;
        width: 100%;
    }
    
    TelemetryDashboard > TabbedContent { 
        height: 100%; 
    }
    
    ContentTabs {
        height: 3;
        margin-bottom: 1;
        background: transparent; 
    }

    ContentSwitcher {
        height: 1fr;
    }

    TabPane {
        height: 100%;
        padding: 0; 
    }
    
    #telemetry-grid {
        layout: grid; 
        grid-size: 2 1; 
        grid-columns: 1fr 1fr; 
        height: 100%;
    }
    
    #telemetry-grid RichLog { 
        border: round $border-color; 
        height: 100%; 
        background: transparent; 
        margin: 0 1; 
    }
    
    #telemetry-grid RichLog:focus { 
        border: round $focus-border-color; 
    }
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
            dashboard = self.query_one(TelemetryDashboard)
            
            # Pass the raw components to the dashboard so it can render the Syntax block
            header = f"[bold cyan]Selected Target:[/bold cyan] {target_node.symbol_name} ({target_node.file_path})\n"
            
            dashboard.update_context(
                source_code=target_node.source_code, 
                language=target_node.language, 
                header_text=header
            )
            self.notify(f"Target selected: {target_node.symbol_name}", title="Target Selected")

    def action_start_run(self) -> None:
        """Triggered via the [s] hotkey."""
        if not self.selected_target_id:
            self.notify("Please select a target function first.", title="Error", severity="error")
            return
            
        config_panel = self.query_one(ConfigPanel)
        mode = config_panel.get_current_mode()
        profile = config_panel.get_sandbox_profile(custom_image=self.image_tag)
        
        # Grab the dashboard and use its API
        dashboard = self.query_one(TelemetryDashboard)
        dashboard.clear_agent()
        
        # Switch the UI back to the telemetry tab automatically when a run starts
        tabs = self.query_one("TabbedContent")
        tabs.active = "tab-telemetry"

        dashboard.write_agent(f"[bold green]Initiating LangGraph Orchestrator...[/bold green]")
        dashboard.write_agent(f"Mode: [cyan]{mode.value}[/cyan]")
        dashboard.write_agent(f"Network: [cyan]{profile.network_mode.value}[/cyan]")
        dashboard.write_agent(f"Limits: RAM={profile.memory_limit}, CPU={profile.cpu_quota}, Timeout={profile.timeout_seconds}s")
        dashboard.write_agent(f"Injected Env Vars: {len(profile.environment_vars)}")
        
        self.notify(f"Starting {mode.value} execution loop...", title="Run Started")
        
        # PHASE 2 TODO: Call Orchestrator passing the selected target and profile schemas.

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        
        with Container(id="main-container"):
            with Container(id="sidebar-column"):
                yield TargetExplorerPane(classes="pane", id="target-explorer")
                yield ConfigPanel(classes="pane", id="sandbox-config")

            with Container(classes="pane", id="workspace-column"):
                yield TelemetryDashboard()

        yield Footer()

if __name__ == "__main__":
    app = SunderApp()
    app.run()