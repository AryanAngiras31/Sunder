import logging
from pygments.util import ClassNotFound
from textual.app import ComposeResult
from textual.containers import Grid, VerticalScroll
from textual.widgets import Static, TabbedContent, TabPane, RichLog
from rich.syntax import Syntax
from rich.console import Group
from rich.text import Text

logger = logging.getLogger(__name__)

class TelemetryDashboard(Static):
    """The main workspace containing the telemetry logs, context viewer, and execution reports."""

    def compose(self) -> ComposeResult:
        with TabbedContent(initial="tab-context"):

            # Tab 1: Code Context
            with TabPane("Code Context", id="tab-context"):
                with VerticalScroll(id="context-scroll-container"):
                    yield Static("Search for a target to view its source code here.", id="context-viewer")

            # Tab 2: Live Telemetry (Split Pane)
            with TabPane("Live Telemetry", id="tab-telemetry"):
                with Grid(id="telemetry-grid"):
                    yield RichLog(id="agent-workspace", highlight=True, markup=True)
                    yield RichLog(id="docker-sandbox", highlight=True, markup=True)
            
            # Tab 3: Execution Report
            with TabPane("Execution Report", id="tab-report"):
                yield Static("Verdict, JWTs, Mock IDs, and Stats.", id="report-viewer")

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