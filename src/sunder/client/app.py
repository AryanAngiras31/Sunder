import os
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import Header, Footer

# Sunder Core Imports
from sunder.execution.bootstrapper import Bootstrapper
from sunder.knowledge.database import KnowledgeDatabase
from sunder.knowledge.ingestion import IngestionEngine

# TUI Components
from sunder.client.hitl_search import TargetExplorerPane
from sunder.client.config_panel import ConfigPanel
from sunder.client.dashboard import TelemetryDashboard
from sunder.client.model_picker import ModelPickerModal

# Orchestration
from langchain.chat_models import init_chat_model
from sunder.orchestration.orchestrator import SunderOrchestrator
from sunder.schema import SunderAgentState, BlastRadiusContext, EnvironmentState
from langchain_openai import ChatOpenAI

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

    /* --- TABBED CONTENT CLEANUP --- */
    TabbedContent { height: 100%; margin: 0; padding: 0; }
    TabbedContent > ContentTabs { height: 3; margin: 0; padding: 0; background: transparent; }
    TabbedContent > ContentSwitcher { height: 1fr; padding: 0; margin: 0; }
    TabPane { height: 100%; padding: 0; margin: 0; }
    
    #context-viewer { 
        height: 100%; 
        width: 100%; 
        padding: 0; 
        margin: 0;
        overflow-y: auto; 
    }

    /* --- TELEMETRY --- */
    #workspace-column { 
        height: 100%; 
        padding: 0; 
    }
    TelemetryDashboard {
        height: 100%;
        width: 100%;
    }
    #telemetry-grid {
        layout: grid; grid-size: 2 1; grid-columns: 1fr 1fr; height: 100%;
    }
    #telemetry-grid RichLog { 
        border: round $border-color; 
        height: 100%; 
        background: transparent; 
        margin: 0 0; 
    }
    #telemetry-grid RichLog:focus { border: round $focus-border-color; }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("tab", "app.focus_next", "Change Pane"),
        ("s", "start_run", "Start Run"),
        ("p", "pick_models", "Pick Models") 
    ]

    def __init__(self):
        super().__init__()
        self.image_tag = None
        self.knowledge_db = None
        self.selected_target_node = None
        
        self.llm_selections = {
            "baseline": "-NA-",
            "adversarial": "-NA-",
            "evaluator": "-NA-"
        }

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
        selected_id = message.option.id
        
        # Fetch the full CodeNode from the database
        target_node = self.knowledge_db.get_node(selected_id)
        
        if target_node:
            self.selected_target_node = target_node

            dashboard = self.query_one(TelemetryDashboard)
            
            # Pass the raw components to the dashboard so it can render the Syntax block
            header = f"[bold cyan]Selected Target:[/bold cyan] {target_node.symbol_name} ({target_node.file_path})\n"
            
            dashboard.update_context(
                source_code=target_node.source_code, 
                language=target_node.language, 
                header_text=header
            )
            self.notify(f"Target selected: {target_node.symbol_name}", title="Target Selected")

    def action_pick_models(self) -> None:
        """Triggered via the [p] hotkey to open the Model Palette."""
        def update_models(new_selections: dict | None):
            if new_selections:
                self.llm_selections = new_selections

        # Push the modal onto the screen and pass it the current selections
        self.app.push_screen(ModelPickerModal(self.llm_selections), update_models)

    def action_start_run(self) -> None:
        """Triggered via the [s] hotkey. Checks prerequisites and instantly starts the run."""
        
        # 1. Prerequisite Checks
        if not self.selected_target_node:
            self.notify("Please select a target function first.", title="Error", severity="error")
            return
            
        if not self.image_tag:
            self.notify("Please wait for the Docker Bootstrapper to finish building.", title="Not Ready", severity="warning")
            return
            
        if any(v == "-NA-" for v in self.llm_selections.values()):
            self.notify("Please press [p] to configure models for all 3 roles before starting.", title="Incomplete Models", severity="error")
            return

        # 2. Retrieve State Components
        config_panel = self.query_one(ConfigPanel)
        mode = config_panel.get_current_mode()
        profile = config_panel.get_sandbox_profile(custom_image=self.image_tag)
        target_node = self.selected_target_node
        
        # 3. Setup Dashboard
        dashboard = self.query_one(TelemetryDashboard)
        dashboard.clear_agent()
        
        tabs = self.query_one("TabbedContent")
        tabs.active = "tab-telemetry"

        dashboard.write_agent(f"[bold green]Initiating LangGraph Orchestrator...[/bold green]")
        dashboard.write_agent(f"Mode: [cyan]{mode.value}[/cyan]")
        dashboard.write_agent(f"Target: [cyan]{target_node.symbol_name}[/cyan] ({target_node.file_path})")
        
        dashboard.write_agent(f"Baseline Coder: [yellow]{self.llm_selections['baseline']}[/yellow]")
        dashboard.write_agent(f"Adversary Coder: [yellow]{self.llm_selections['adversarial']}[/yellow]")
        dashboard.write_agent(f"Evaluator Node: [yellow]{self.llm_selections['evaluator']}[/yellow]")
        dashboard.write_agent("---")
        
        self.notify(f"Starting {mode.value} execution loop...", title="Run Started")
        
        # 4. Initialize LLMs & Orchestrator
        try:
            def create_llm(model_id: str, temperature: float):
                if "/" in model_id:
                    provider, model_name = model_id.split("/", 1)
                else:
                    provider, model_name = "unknown", model_id

                # 1. Route OpenRouter through the OpenAI Universal API
                if provider == "openrouter":
                    return ChatOpenAI(
                        model=model_id, 
                        # Look for a custom URL, otherwise default to the public API
                        base_url=os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"), 
                        api_key=os.environ.get("OPENROUTER_API_KEY", "missing_key"),
                        temperature=temperature
                    )
                    
                # 2. Route Ollama through the OpenAI Universal API for guaranteed structured output support
                elif provider == "ollama":
                    return ChatOpenAI(
                        model=model_name,
                        # Look for a remote/custom Ollama URL, otherwise default to localhost
                        base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
                        api_key="ollama", 
                        temperature=temperature
                    )
                    
                # 3. Let LangChain natively handle standard providers (openai, anthropic, google_genai, etc.)
                else:
                    return init_chat_model(model=model_name, model_provider=provider, temperature=temperature)

            baseline_llm = create_llm(self.llm_selections['baseline'], 0.2)
            adversary_llm = create_llm(self.llm_selections['adversarial'], 0.7)
            evaluator_llm = create_llm(self.llm_selections['evaluator'], 0)
            
            orchestrator = SunderOrchestrator(
                baseline_coder_llm=baseline_llm,
                adversary_coder_llm=adversary_llm,
                evaluator_llm=evaluator_llm,
                target_path=target_node.file_path,
                image_tag=self.image_tag
            )
            
            graph = orchestrator.build_graph()
            
            # Construct the Initial State
            initial_state = SunderAgentState(
                mode=mode,
                context=BlastRadiusContext(
                    target_node=target_node,
                    children=[],
                    parents=[]
                ),
                sandbox_config=profile,
                env_state=EnvironmentState(),
                retry_count=0,
                max_retries=3
            )
            
            # 5. Kick off background execution
            self.run_orchestration_loop(graph, initial_state)
            
        except Exception as e:
            dashboard.write_agent(f"[bold red]Failed to initialize Orchestrator: {e}[/bold red]")
            self.notify(f"Failed to start Orchestrator.", title="Error", severity="error")

    @work
    async def run_orchestration_loop(self, graph, initial_state: SunderAgentState) -> None:
        """Runs the compiled LangGraph asynchronously to prevent UI freezing."""
        dashboard = self.query_one(TelemetryDashboard)
        try:
            # LangGraph's astream yields dicts containing updates from each node as they complete
            async for output in graph.astream(initial_state):
                for node_name, state_update in output.items():
                    dashboard.write_agent(f"\n[bold magenta]>[/bold magenta] Node [cyan]{node_name}[/cyan] completed.")
                    
                    # Log interesting parts of the state update safely
                    if "current_test_script" in state_update:
                        dashboard.write_agent(f"Generated payload (length: {len(state_update['current_test_script'])} chars)")
                        
                    if "execution_report" in state_update:
                        report = state_update["execution_report"]
                        color = "green" if report.exit_code == 0 else "red"
                        dashboard.write_agent(f"Sandbox Exit Code: [bold {color}]{report.exit_code}[/bold {color}]")
                        
                    if "final_verdict" in state_update:
                        verdict = state_update["final_verdict"]
                        dashboard.write_agent(f"Evaluator Verdict: [bold yellow]{verdict.value}[/bold yellow]")
                        
                    if "evaluator_feedback" in state_update:
                        dashboard.write_agent(f"Feedback: [dim]{state_update['evaluator_feedback']}[/dim]")
                        
            dashboard.write_agent(f"\n[bold green]Run Completed.[/bold green]")
            self.notify("Orchestration loop finished.", title="Run Complete", severity="information")
            
        except Exception as e:
            dashboard.write_agent(f"\n[bold red]Orchestrator Execution Error: {e}[/bold red]")
            self.notify("Execution failed. See telemetry for details.", title="Fatal Error", severity="error")

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