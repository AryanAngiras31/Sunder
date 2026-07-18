import os
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import Header, Footer, Tabs, Input, TabbedContent
from dotenv import load_dotenv
from rich.syntax import Syntax
from rich.text import Text
from pygments.util import ClassNotFound

# Sunder Core Imports
from sunder.execution.bootstrapper import Bootstrapper
from sunder.knowledge.database import KnowledgeDatabase
from sunder.knowledge.ingestion import IngestionEngine
from sunder.knowledge.retrieval import ContextRetriever
from sunder.knowledge.context_manager import ContextManager

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
    $border-color: #2B2B2B;
    $focus-border-color: #82BDBD;
    $text-primary: #e0e0e0;
    $surface-color: #0D0D0D;

    Screen { background: $surface-color; }

    #main-container {
        layout: grid;
        grid-size: 2 1; 
        grid-columns: 3fr 7fr; 
        height: 100%; width: 100%;
        padding: 0 1; 
    }
    
    /* COLLAPSIBLE SIDEBAR CLASSES */
    #main-container.sidebar-hidden {
        grid-size: 1 1;
        grid-columns: 1fr;
    }
    #main-container.sidebar-hidden #sidebar-column {
        display: none;
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
        color: $text-primary; text-style: bold;
        margin-bottom: 1; content-align: center middle; width: 100%;
    }
    
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
        color: $text-primary;
        content-align: center middle;
    }
    #env-var-btn:hover, #env-var-btn:focus {
        color: $focus-border-color;
        text-style: bold;
    }

    /* --- TABBED CONTENT CLEANUP --- */
    TabbedContent { height: 100%; margin: 0; padding: 0; }
    TabbedContent > ContentTabs { height: 1; margin: 0; padding: 0; background: transparent; }
    TabbedContent > ContentSwitcher { height: 1fr; padding: 0; margin: 0; }
    TabPane { height: 100%; padding: 0; margin: 0; }
    
    #context-viewer { 
        height: auto; 
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

    /* --- GLOBAL BUTTON STYLING --- */
    
    /* Target all variant="success" buttons */
    Button.-success {
        background: $surface-color;
        border: round $focus-border-color;
        color: $text-primary;
    }

    /* Target all variant="error" buttons */
    Button.-error {
        background: $surface-color;
        border: round $border-color;
        color: $text-primary;
    }

    #picker-actions Button:focus {
        background: $surface-color;
        color: $text-primary;
        text-style: none; 
    }
    
    #picker-actions Button.-success:focus {
        background: transparent;
        border: round $focus-border-color;
    }
    
    #picker-actions Button.-error:focus {
        background: transparent;
        border: round $border-color;
    }

    /* --- FLOATING COPY BUTTONS --- */
    .pane-wrapper {
        height: 100%;
        width: 100%;
        layers: base overlay; 
    }
    
    Button.copy-btn {
        layer: overlay;       
        dock: right;         
        margin-top: 1;        
        margin-right: 4;             
        min-width: 1;        
        height: 1;   
        padding: 0;
        border: none;
        content-align: center middle;
        background: $surface-color;
    }
    
    Button.copy-btn:hover {
        background: $focus-border-color;
        color: $surface-color;
        text-style: bold;
    }

    /* --- TARGET EXPLORER STYLING --- */
    #search-input {
        background: $surface-color;
        border: round $border-color;
    }
    
    #search-input:focus {
        background: transparent;
    }
    
    #target-results {
        background: $surface-color;
        border: none;
    }

    #target-results:focus {
        background: transparent;
    }

    #target-explorer Input { margin-bottom: 0; }

    #target-results > .option-list--option-highlighted {
        background: $focus-border-color;
        color: $surface-color;
        text-style: bold;
    }

    Tab:focus, Tab.-active {
        background: $focus-border-color !important;
        color: $surface-color !important;
    }
    Underline > .underline--bar {
        color: $focus-border-color !important;
        background: $focus-border-color !important;
    }

    Switch.-on > .switch--slider {
        color: $focus-border-color !important; 
        background: $surface-color !important;
    }
    Switch:focus {
        border: round $border-color !important;
        background: $surface-color;
    }

    RadioButton, 
    RadioButton:focus, 
    RadioButton.-on,
    RadioButton.-off {
        background: transparent !important;
        text-style: none !important;
    }

    RadioSet:focus, 
    RadioSet:focus-within {
        background: transparent !important;
        border: round $border-color !important;
        text-style: none !important;
    }

    RadioButton > .toggle--button,
    RadioButton:focus > .toggle--button,
    RadioButton:hover > .toggle--button,
    RadioButton.-on > .toggle--button {
        background: transparent !important;
        color: $border-color;
        text-style: none !important;
    }

    RadioButton > .toggle--label,
    RadioButton:focus > .toggle--label,
    RadioButton:hover > .toggle--label,
    RadioButton.-on > .toggle--label {
        background: transparent !important;
        text-style: none !important; 
    }

    RadioButton.-on > .toggle--button, 
    RadioSet:focus-within RadioButton.-on > .toggle--button {
        color: $focus-border-color !important;
        background: transparent !important; 
    }

    RadioButton.-off > .toggle--button, 
    RadioSet:focus-within RadioButton.-off > .toggle--button {
        color: $border-color !important;
        background: transparent !important; 
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("b", "toggle_sidebar", "Toggle Sidebar"),
        ("s", "start_run", "Start Run"),
        ("p", "pick_models", "Pick Models") 
    ]

    def __init__(self):
        super().__init__()
        self.image_tag = None
        self.knowledge_db = None
        self.selected_target_node = None
        self.children_nodes = None
        self.parent_nodes = None
        
        self.llm_selections = {
            "baseline": "-NA-",
            "adversarial": "-NA-",
            "evaluator": "-NA-"
        }

        env_path = os.path.join(os.getcwd(), ".sunder", ".env")
        if os.path.exists(env_path):
            load_dotenv(env_path)

    def _clear_run_logs(self) -> None:
        """Clears the logs/agent.md and logs/sandbox.md files at the start of a run."""
        log_dir = os.path.join(os.getcwd(), ".sunder", "logs")
        os.makedirs(log_dir, exist_ok=True)
        for filename in ["agent.md", "sandbox.md"]:
            file_path = os.path.join(log_dir, filename)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(f"# {filename.split('.')[0].capitalize()} Log\n\n")

    def _log_to_file(self, filename: str, content: str, block_type: str = "") -> None:
        """Appends plain text to the local markdown log file."""
        log_dir = os.path.join(os.getcwd(), ".sunder", "logs")
        os.makedirs(log_dir, exist_ok=True)
        file_path = os.path.join(log_dir, filename)
        
        with open(file_path, "a", encoding="utf-8") as f:
            if block_type:
                f.write(f"\n```{block_type}\n{content}\n```\n")
            else:
                f.write(f"{content}\n")

    def on_mount(self) -> None:
        """Fires immediately when the UI is drawn to the terminal."""
        self.notify("Starting Bootstrapper & Ingestion Engine...", title="Sunder Startup")

        # Clear logs from previous run
        self._clear_run_logs()
        
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
        
        # 1. Fetch the raw node to set the target
        target_node = self.knowledge_db.get_node(selected_id)
        
        if target_node:
            self.selected_target_node = target_node
            dashboard = self.query_one(TelemetryDashboard)

            # 2. Retrieve and Prune the full Blast Radius
            retriever = ContextRetriever(self.knowledge_db)
            raw_context = retriever.get_blast_radius(selected_id)
            
            manager = ContextManager() # Default 20k token limit
            pruned_context = manager.prune_context(raw_context)

            # 3. Format the display string for the Dashboard
            display_text = f"// === TARGET: {target_node.symbol_name} ===\n\n{target_node.source_code}\n\n"
            
            if pruned_context.children:
                self.children_nodes = pruned_context.children
                display_text += "// === DEPENDENCIES (CHILDREN) ===\n\n"
                for child in pruned_context.children:
                    display_text += f"// {child.file_path}:\n{child.source_code}\n\n"
                    
            if pruned_context.parents:
                self.parent_nodes = pruned_context.parents
                display_text += "// === USAGE EXAMPLES (PARENTS) ===\n\n"
                for parent in pruned_context.parents:
                    display_text += f"// {parent.file_path}:\n{parent.source_code}\n\n"
            
            # 4. Update the dashboard with the combined syntax block
            dashboard.update_context(
                source_code=display_text.strip(), 
                language=target_node.language, 
                header_text=""
            )

    async def on_input_submitted(self, message: Input.Submitted) -> None:
        """Triggered when the user presses Enter in the search bar."""
        option_list = self.query_one("#target-results")
        
        # Only switch focus if there are actual results to interact with
        if option_list.option_count > 0:
            option_list.focus()
            option_list.highlighted = 0

    def action_toggle_sidebar(self) -> None:
        """Triggered via the [b] hotkey to toggle the left sidebar's visibility."""
        container = self.query_one("#main-container")
        container.toggle_class("sidebar-hidden")

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
            self.notify("Press p to choose models for all 3 roles before starting.", title="Incomplete Models", severity="error")
            return

        # 2. Retrieve State Components
        config_panel = self.query_one(ConfigPanel)
        mode = config_panel.get_current_mode()
        profile = config_panel.get_sandbox_profile(custom_image=self.image_tag)
        max_retries = config_panel.get_max_retries()
        target_node = self.selected_target_node
        children_nodes = self.children_nodes
        parent_nodes = self.parent_nodes 
        
        # 3. Setup Dashboard & Clear Logs
        dashboard = self.query_one(TelemetryDashboard)
        dashboard.clear_agent()
        dashboard.clear_sandbox()
        
        tabs = self.query_one("TabbedContent")
        tabs.active = "tab-telemetry"

        dashboard.write_agent("[bold cyan]Initiating LangGraph Orchestrator...[/bold cyan]")
        self._log_to_file("agent.md", "Initiating LangGraph Orchestrator...")

        dashboard.write_agent(f"Mode: {mode.value}")
        self._log_to_file("agent.md", f"Mode: {mode.value}")

        dashboard.write_agent(f"Target:{target_node.symbol_name} ({target_node.file_path})")
        self._log_to_file("agent.md", f"Target: {target_node.symbol_name} ({target_node.file_path})")
        
        dashboard.write_agent(f"Baseline Coder: {self.llm_selections['baseline']}")
        self._log_to_file("agent.md", f"Baseline Coder: {self.llm_selections['baseline']}")

        dashboard.write_agent(f"Adversary Coder: {self.llm_selections['adversarial']}")
        self._log_to_file("agent.md", f"Adversary Coder: {self.llm_selections['adversarial']}")

        dashboard.write_agent(f"Evaluator Node: {self.llm_selections['evaluator']}")
        self._log_to_file("agent.md", f"Evaluator Node: {self.llm_selections['evaluator']}")

        dashboard.write_agent("---")
        self._log_to_file("agent.md", "---")
        
        self.notify(f"Starting {mode.value} execution loop...", title="Run Started")
        
        # 4. Initialize LLMs & Orchestrator
        try:
            def create_llm(model_id: str, temperature: float):
                if "/" in model_id:
                    provider, model_name = model_id.split("/", 1)
                else:
                    provider, model_name = "unknown", model_id

                provider_map = {
                    "gemini": "google_genai",
                    "vertex_ai": "google_vertexai",
                    "azure": "azure_openai",
                    "mistral": "mistralai",
                    "together_ai": "together"
                }
                provider = provider_map.get(provider, provider)

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
                target_path=os.getcwd(),
                image_tag=self.image_tag
            )
            
            graph = orchestrator.build_graph()
            
            # Construct the Initial State
            initial_state = SunderAgentState(
                mode=mode,
                context=BlastRadiusContext(
                    target_node=target_node,
                    children=children_nodes,
                    parents=parent_nodes
                ),
                sandbox_config=profile,
                env_state=EnvironmentState(),
                retry_count=0,
                max_retries=max_retries
            )
            
            # 5. Kick off background execution
            self.run_orchestration_loop(graph, initial_state)
            
        except Exception as e:
            dashboard.write_agent(f"[bold red]Failed to initialize Orchestrator: {e}[/bold red]")
            self._log_to_file("agent.md", f"Failed to initialize Orchestrator: {e}")
            self.notify(f"Failed to start Orchestrator.", title="Error", severity="error")

    @work
    async def run_orchestration_loop(self, graph, initial_state: SunderAgentState) -> None:
        """Runs the compiled LangGraph asynchronously and routes telemetry cleanly."""
        dashboard = self.query_one(TelemetryDashboard)

        report_data = {
            "target_name": self.selected_target_node.symbol_name,
            "language": self.selected_target_node.language,
            "verdict": "UNKNOWN",
            "script": "",
            "feedback": "No feedback provided.",
            "retries_left": initial_state.max_retries
        }

        try:
            async for output in graph.astream(initial_state):
                for node_name, state_update in output.items():
                    # --- 1. AGENT LOG: Node Transition ---
                    dashboard.write_agent(f"\n[bold]▶[/bold] [cyan]{node_name}[/cyan]")
                    self._log_to_file("agent.md", f"\n▶ {node_name}")

                    # Capture retries dynamically
                    if "retry_count" in state_update:
                        report_data["retries_left"] = initial_state.max_retries - state_update["retry_count"]
                    
                    # --- 2. CODER NODES: Script Generation ---
                    if "current_test_script" in state_update:
                        script = state_update["current_test_script"]
                        report_data["script"] = script
                        dashboard.write_agent(f"  └─ Generated payload (length: {len(script)} chars)")
                        self._log_to_file("agent.md", f"  └─ Generated payload (length: {len(script)} chars)")
                        
                        # Sandbox Log: Syntax highlighted injection
                        dashboard.write_sandbox(f"\n[bold]--- INJECTED PAYLOAD ({node_name}) ---[/bold]")
                        self._log_to_file("sandbox.md", f"\n--- INJECTED PAYLOAD ({node_name}) ---")
                        # Pass syntax block directly to avoid rich markup injection errors
                        try: 
                            enhanced_script = Syntax(
                                script, 
                                lexer=self.selected_target_node.language, 
                                theme="nord-darker", 
                                word_wrap=True, 
                                tab_size=2, 
                                line_numbers=True
                            )
                        except ClassNotFound:
                            enhanced_script = Syntax(
                                script, 
                                lexer='text', 
                                theme="nord-darker", 
                                word_wrap=True, 
                                tab_size=2, 
                                line_numbers=True
                            )
                        dashboard.write_sandbox(enhanced_script)
                        self._log_to_file("sandbox.md", script, block_type=self.selected_target_node.language)
                        
                    # --- 3. EXECUTOR NODE: Execution Report ---
                    if "execution_report" in state_update:
                        report = state_update["execution_report"]
                        color = "green" if report.exit_code == 0 else "red"
                        
                        dashboard.write_agent(f"  └─ Execution finished. Exit Code: [bold {color}]{report.exit_code}[/bold {color}]")
                        self._log_to_file("agent.md", f"  └─ Execution finished. Exit Code: {report.exit_code}")
                        
                        # Sandbox Log: Environment Outputs
                        dashboard.write_sandbox(f"\n[bold {color}]--- EXECUTION REPORT ---[/bold {color}]")
                        dashboard.write_sandbox(f"Exit Code: {report.exit_code}")
                        self._log_to_file("sandbox.md", f"\n--- EXECUTION REPORT ---\nExit Code: {report.exit_code}")
                        
                        if report.stdout:
                            dashboard.write_sandbox("\n[bold]STDOUT:[/bold]")
                            # Wrap in rich.text.Text so random brackets in stdout don't crash markup
                            dashboard.write_sandbox(Text(report.stdout))
                            self._log_to_file("sandbox.md", "STDOUT:")
                            self._log_to_file("sandbox.md", report.stdout, block_type="text")
                            
                        if report.stderr:
                            dashboard.write_sandbox("\n[bold red]STDERR:[/bold red]")
                            dashboard.write_sandbox(Text(report.stderr, style="red"))
                            self._log_to_file("sandbox.md", "STDERR:")
                            self._log_to_file("sandbox.md", report.stderr, block_type="text")
                            
                    # --- 4. EVALUATOR NODE: Feedback & Verdict ---
                    if "evaluator_feedback" in state_update:
                        feedback = state_update["evaluator_feedback"]
                        report_data["feedback"] = feedback

                        dashboard.write_agent(f"  ├─ [bold]Evaluator Feedback:[/bold]")
                        dashboard.write_agent(f"  │  [italic]{feedback}[/italic]")
                        self._log_to_file("agent.md", f"  ├─ Evaluator Feedback:\n  │  {feedback}")
                        
                    if "final_verdict" in state_update:
                        verdict = state_update["final_verdict"]
                        report_data["verdict"] = verdict.name
                        # Give secure results green text, vulnerabilities red/yellow
                        v_color = "bold green" if "SECURE" in verdict.name else "bold red"
                        dashboard.write_agent(f"  └─ [bold]Verdict:[/bold] [{v_color}]{verdict.value}[/{v_color}]")
                        self._log_to_file("agent.md", f"  └─ Verdict: {verdict.value}")
                        
            # Generate Final Report
            dashboard.update_report(report_data)

            dashboard.write_agent(f"\n[bold green]Run Completed.[/bold green]")
            self._log_to_file("agent.md", "\nRun Completed.")
            dashboard.write_sandbox(f"\n[bold green]Container Terminated.[/bold green]")
            self._log_to_file("sandbox.md", "\nContainer Terminated.")

            # Go to the Execution Report tab after finishing run
            tabs = self.query_one(TabbedContent)
            tabs.active = "tab-report"
                        
        except Exception as e:
            dashboard.write_agent(f"\n[bold red]Orchestrator Execution Error: {e}[/bold  red]")
            self._log_to_file("agent.md", f"\nOrchestrator Execution Error: {e}")
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

def main():
    """CLI Entry Point."""
    app = SunderApp()
    app.run()

if __name__ == "__main__":
    main()