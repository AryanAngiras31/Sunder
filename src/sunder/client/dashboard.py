import logging
from textual.app import ComposeResult
from textual.containers import Grid
from textual.widgets import Static, TabbedContent, TabPane, RichLog
from rich.syntax import Syntax

logger = logging.getLogger(__name__)

class TelemetryDashboard(Static):
    """The main workspace containing the telemetry logs, context viewer, and execution reports."""

    def compose(self) -> ComposeResult:
        with TabbedContent(initial="tab-telemetry"):

            # Tab 1: Code Context
            with TabPane("Code Context", id="tab-context"):
                # We use a static widget here to render the highlighted Markdown/Source
                yield Static("Search for a target to view its source code here.", id="context-viewer")
            
            # Tab 2: Live Telemetry (Split Pane)
            with TabPane("Live Telemetry", id="tab-telemetry"):
                with Grid(id="telemetry-grid"):
                    yield RichLog(id="agent-workspace", highlight=True, markup=True)
                    yield RichLog(id="docker-sandbox", highlight=True)
            
            # Tab 3: Execution Report
            with TabPane("Execution Report", id="tab-report"):
                yield Static("Verdict, JWTs, Mock IDs, and Stats.", id="report-viewer")

    def write_agent(self, text: str) -> None:
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

    def write_sandbox(self, text: str) -> None:
        """Write to the right-hand Docker Sandbox log."""
        try:
            log = self.query_one("#docker-sandbox", RichLog)
            log.write(text)
        except Exception as e:
            logger.error(f"Failed to write to sandbox log: {e}")

    def update_context(self, source_code: str, language: str, header_text: str) -> None:
        """Update the Code Context tab with syntax-highlighted source code."""
        try:
            viewer = self.query_one("#context-viewer", Static)
            
            syntax_block = Syntax(
                source_code, 
                lexer=language, 
                theme="monokai", 
                line_numbers=True, 
                word_wrap=True,
                background_color="default" 
            )
            
            # Safely group the header text and the highlighted code
            header = Text.from_markup(header_text)
            viewer.update(Group(header, syntax_block))
            
            # Automatically switch to the context tab
            tabs = self.query_one(TabbedContent)
            tabs.active = "tab-context"
        except Exception as e:
            logger.error(f"Failed to update context viewer: {e}")