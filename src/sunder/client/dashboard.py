import logging
from pygments.util import ClassNotFound
from textual.app import ComposeResult
from textual.containers import Grid, VerticalScroll, Container
from textual.widgets import Static, TabbedContent, TabPane, RichLog, Button
from rich.syntax import Syntax
from rich.console import Group
from rich.text import Text

logger = logging.getLogger(__name__)

class TelemetryDashboard(Static):
    """The main workspace containing the telemetry logs, context viewer, and execution reports."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Store raw text in memory for the static tabs so they can be copied instantly
        self._raw_context = ""
        self._raw_report = ""

    def compose(self) -> ComposeResult:
        with TabbedContent(initial="tab-context"):

            # Tab 1: Code Context
            with TabPane("Code Context", id="tab-context"):
                with Container(classes="pane-wrapper"):
                    yield Button("⎘", id="copy-context", classes="copy-btn")
                    with VerticalScroll(id="context-scroll-container"):
                        yield Static("Search for a target to view its source code here.", id="context-viewer")

            # Tab 2: Live Telemetry (Split Pane)
            with TabPane("Live Telemetry", id="tab-telemetry"):
                with Grid(id="telemetry-grid"):
                    with Container(classes="pane-wrapper"):
                        yield Button("⎘", id="copy-context", classes="copy-btn")
                        yield RichLog(id="agent-workspace", highlight=True, markup=True)
                        
                    with Container(classes="pane-wrapper"):
                        yield Button("⎘", id="copy-context", classes="copy-btn")
                        yield RichLog(id="docker-sandbox", highlight=True, markup=True)
            
            # Tab 3: Execution Report
            with TabPane("Execution Report", id="tab-report"):
                with Container(classes="pane-wrapper"):
                    yield Button("⎘", id="copy-context", classes="copy-btn")
                    yield Static("Verdict, JWTs, Mock IDs, and Stats.", id="report-viewer")

    # ---- Dashboard Handlers ----

    def write_agent(self, text) -> None:
        """Write to the left-hand Agent Workspace log."""
        try:
            log = self.query_one("#agent-workspace", RichLog)
            log.write(text)
        except Exception as e:
            logger.error(f"Failed to write to agent log: {e}")

    def clear_agent(self) -> None:
        """Clear the left-hand Agent Workspace log."""
        try:
            self.query_one("#agent-workspace", RichLog).clear()
        except Exception:
            pass

    def write_sandbox(self, content) -> None:
        """Write to the right-hand Docker Sandbox log. Accepts strings or Rich renderables."""
        try:
            log = self.query_one("#docker-sandbox", RichLog)
            log.write(content)
        except Exception as e:
            logger.error(f"Failed to write to sandbox log: {e}")
            
    def clear_sandbox(self) -> None:
        """Clear the right-hand Docker Sandbox log."""
        try:
            self.query_one("#docker-sandbox", RichLog).clear()
        except Exception:
            pass

    def update_context(self, source_code: str, language: str, header_text: str) -> None:
        """Update the Code Context tab with syntax-highlighted source code."""
        try:
            # Save the raw code to memory so the Copy button can grab it easily
            self._raw_context = source_code 
            
            # Render the syntax block
            viewer = self.query_one("#context-viewer", Static)
            try:
                syntax_block = Syntax(
                    source_code, 
                    lexer=language, 
                    theme="monokai", 
                    line_numbers=True, 
                    word_wrap=True,
                    background_color="default",
                    tab_size=2
                )
            except ClassNotFound:
                syntax_block = Syntax(
                    source_code, 
                    lexer='text', 
                    theme="monokai", 
                    line_numbers=True, 
                    word_wrap=True,
                    background_color="default",
                    tab_size=2
                )
            header = Text.from_markup(header_text)
            viewer.update(Group(header, syntax_block))
            
            tabs = self.query_one(TabbedContent)
            tabs.active = "tab-context"
            
            scroll_container = self.query_one("#context-scroll-container", VerticalScroll)
            scroll_container.scroll_to(0, 0)
        except Exception as e:
            logger.error(f"Failed to update context viewer: {e}")

    # ---- Clipboard Handlers ----

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Routes the copy button clicks to the appropriate text source."""
        text_to_copy = ""
        
        if event.button.id == "copy-context":
            text_to_copy = self._raw_context
        elif event.button.id == "copy-agent":
            text_to_copy = self._read_log_file("agent.md")
        elif event.button.id == "copy-sandbox":
            text_to_copy = self._read_log_file("sandbox.md")
        elif event.button.id == "copy-report":
            text_to_copy = self._raw_report

        if text_to_copy.strip():
            self.app.copy_to_clipboard(text_to_copy)

    def _read_log_file(self, filename: str) -> str:
        """Helper to fetch perfectly unformatted raw text from the markdown logs."""
        try:
            file_path = os.path.join(os.getcwd(), ".sunder", "logs", filename)
            if os.path.exists(file_path):
                with open(file_path, "r", encoding="utf-8") as f:
                    return f.read()
        except Exception as e:
            logger.error(f"Failed to read {filename} for copying: {e}")
        return ""