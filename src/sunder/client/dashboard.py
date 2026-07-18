import logging
import os
from pygments.util import ClassNotFound
from textual.app import ComposeResult
from textual.containers import Grid, VerticalScroll, Container
from textual.widgets import Static, TabbedContent, TabPane, RichLog, Button
from rich.syntax import Syntax
from rich.console import Group
from rich.text import Text
from rich.panel import Panel
from rich.markdown import Markdown

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
                        yield Static("\nSearch for a target to view its source code here.", id="context-viewer")

            # Tab 2: Live Telemetry (Split Pane)
            with TabPane("Live Telemetry", id="tab-telemetry"):
                with Grid(id="telemetry-grid"):
                    with Container(classes="pane-wrapper"):
                        yield Button("⎘", id="copy-agent", classes="copy-btn")
                        yield RichLog(id="agent-workspace", highlight=True, markup=True, wrap=True)
                        
                    with Container(classes="pane-wrapper"):
                        yield Button("⎘", id="copy-sandbox", classes="copy-btn")
                        yield RichLog(id="docker-sandbox", highlight=True, markup=True, wrap=True)
            
            # Tab 3: Execution Report
            with TabPane("Execution Report", id="tab-report"):
                with Container(classes="pane-wrapper"):
                    yield Button("⎘", id="copy-report", classes="copy-btn")
                    with VerticalScroll(id="report-scroll-container"):
                        yield Static("\nRun an agent loop to generate a report.", id="report-viewer")

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

    def update_context(self, target_node, children_nodes, parent_nodes) -> None:
        """Update the Code Context tab with syntax-highlighted source code in nested panels."""
        try:
            language = target_node.language
            renderables = []
            raw_text_parts = []

            # Helper to generate syntax blocks safely
            def create_syntax(code: str):
                try:
                    return Syntax(code, lexer=language, theme="nord-darker", line_numbers=True, word_wrap=True, background_color="default", tab_size=2)
                except ClassNotFound:
                    return Syntax(code, lexer='text', theme="nord-darker", line_numbers=True, word_wrap=True, background_color="default", tab_size=2)

            # 1. Target Panel (Nested)
            target_syntax = create_syntax(target_node.source_code)
            target_inner_panel = Panel(target_syntax, title=f"[bold]{target_node.file_path}[/bold]", title_align="left")
            
            renderables.append(
                Panel(target_inner_panel, title=f"[bold]> TARGET: {target_node.symbol_name}[/bold]", title_align="left")
            )
            raw_text_parts.append(f"// === TARGET: {target_node.symbol_name} ===\n// {target_node.file_path}\n{target_node.source_code}")

            # 2. Children Panels (Nested)
            if children_nodes:
                child_panels = []
                raw_children = []
                
                # Create an inner panel for each child
                for c in children_nodes:
                    child_syntax = create_syntax(c.source_code)
                    child_panels.append(Panel(child_syntax, title=f"[bold]{c.file_path}[/bold]", title_align="left"))
                    raw_children.append(f"// {c.file_path}\n{c.source_code}")
                
                # Group them and wrap them in the outer parent panel
                renderables.append(
                    Panel(Group(*child_panels), title="[bold]> CHILDREN[/bold]", title_align="left")
                )
                raw_text_parts.append(f"// === CHILDREN ===\n" + "\n\n".join(raw_children))

            # 3. Parents Panels (Nested)
            if parent_nodes:
                parent_panels = []
                raw_parents = []
                
                # Create an inner panel for each parent
                for p in parent_nodes:
                    parent_syntax = create_syntax(p.source_code)
                    parent_panels.append(Panel(parent_syntax, title=f"[bold]{p.file_path}[/bold]", title_align="left"))
                    raw_parents.append(f"// {p.file_path}\n{p.source_code}")
                
                # Group them and wrap them in the outer parent panel
                renderables.append(
                    Panel(Group(*parent_panels), title="[bold]> PARENTS[/bold]", title_align="left")
                )
                raw_text_parts.append(f"// === PARENTS ===\n" + "\n\n".join(raw_parents))

            # Save the raw string for the floating copy button
            self._raw_context = "\n\n".join(raw_text_parts)

            # Render to UI
            viewer = self.query_one("#context-viewer", Static)
            viewer.update(Group(*renderables))
            
            tabs = self.query_one(TabbedContent)
            tabs.active = "tab-context"
            
            scroll_container = self.query_one("#context-scroll-container", VerticalScroll)
            scroll_container.scroll_to(0, 0)
            
        except Exception as e:
            logger.error(f"Failed to update context viewer: {e}")

    def update_report(self, report_data: dict) -> None:
        """Dynamically builds the Simple Security Report."""
        target = report_data.get("target_name", "Unknown")
        verdict = report_data.get("verdict", "UNKNOWN")
        is_secure = "SECURE" in verdict.upper()
        
        v_color = "bold green" if is_secure else "bold red"
        v_icon = "SECURE" if is_secure else "VULNERABILITY FOUND"
        
        retries_left = report_data.get("retries_left", 0)
        feedback = report_data.get("feedback", "No evaluator feedback provided.")
        script = report_data.get("script", "")
        language = report_data.get("language", "text")

        # 1. Header Panel
        header_panel = Panel(
            f"[{v_color}]TARGET: {target}[/{v_color}]\n"
            f"[bold]Retries Remaining:[/bold] {retries_left}",
            title=f"[{v_color}]{v_icon}[/{v_color}]",
            title_align="left",
            border_style="green" if is_secure else "red"
        )

        # 2. Markdown Feedback Panel
        feedback_panel = Panel(
            Markdown(feedback),
            title="[bold]> EVALUATOR FEEDBACK[/bold]",
            title_align="left"
        )
        
        # 3. Code Syntax Panel
        try:
            syntax_block = Syntax(
                script, 
                lexer=language, 
                theme="nord-darker", 
                line_numbers=True, 
                word_wrap=True, # Ensures code wraps to screen limits
                tab_size=2
            )
        except ClassNotFound:
            syntax_block = Syntax(script, lexer="text", theme="nord-darker", word_wrap=True)

        script_panel = Panel(
            syntax_block,
            title="[bold]> FINAL TEST SCRIPT[/bold]",
            title_align="left"
        )

        # 4. Render to UI
        viewer = self.query_one("#report-viewer", Static)
        viewer.update(Group(header_panel, feedback_panel, script_panel))
        
        # 5. Save Raw Text for the Copy Button
        self._raw_report = (
            f"--- SECURITY AUDIT REPORT ---\n"
            f"Verdict: {v_icon} ({target})\n"
            f"Retries Left: {retries_left}\n\n"
            f"> EVALUATOR FEEDBACK\n"
            f"{feedback}\n\n"
            f"> FINAL TEST SCRIPT\n"
            f"{script}\n"
        )

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