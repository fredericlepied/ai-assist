"""Unified output rendering for agent activity.

All agent output (tool calls, progress, streaming text, inner execution)
goes through an OutputRenderer. Two implementations:
- PlainRenderer: stdout for CLI, AWL, monitors
- RichRenderer: Rich console with Live/spinners for TUI
"""

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from rich.console import Console


def _format_display_name(tool_name: str) -> str:
    """Format a tool name for user-friendly display."""
    return tool_name.replace("mcp__", "").replace("__", " → ").replace("_", " ")


def _format_args_plain(input_dict: dict, max_len: int = 100) -> str:
    """Format tool arguments for plain text display."""
    parts = []
    for key, value in input_dict.items():
        value_str = str(value).replace("\n", " ").replace("\r", "")
        if len(value_str) > max_len:
            value_str = value_str[:max_len] + "..."
        parts.append(f"{key}={value_str}")
    return ", ".join(parts)


class OutputRenderer(Protocol):
    """Protocol for rendering agent output to the user."""

    def show_tool_call(self, tool_name: str, arguments: dict) -> None:
        """Display an outer tool call (from the main agent loop)."""
        ...

    def show_inner_tool_call(self, tool_name: str, arguments: dict) -> None:
        """Display a nested tool call (from MCP prompt or AWL execution)."""
        ...

    def show_progress(self, status: str, detail: str = "") -> None:
        """Display progress (thinking, calling claude, executing tool)."""
        ...

    def show_text_delta(self, text: str) -> None:
        """Display a streaming text chunk."""
        ...

    def show_text_done(self) -> None:
        """Signal that streaming text is complete."""
        ...

    def show_warning(self, message: str) -> None:
        """Display a warning message."""
        ...

    def show_error(self, message: str) -> None:
        """Display an error message."""
        ...

    def on_inner_execution(self, chunk: Any) -> None:
        """Handle a raw inner execution chunk (str or dict).

        This is the callback compatible with agent.on_inner_execution.
        Dispatches to show_inner_tool_call, show_error, etc.
        """
        ...


class PlainRenderer:
    """Plain stdout renderer for CLI, AWL, and monitor modes."""

    def show_tool_call(self, tool_name: str, arguments: dict) -> None:
        display_name = _format_display_name(tool_name)
        print(f"\n  🔧 {display_name}", flush=True)
        if arguments:
            if tool_name == "internal__think":
                thought = arguments.get("thought", "")
                for line in thought.splitlines():
                    print(f"     {line}")
            else:
                print(f"     {self._format_args(arguments)}")

    def show_inner_tool_call(self, tool_name: str, arguments: dict) -> None:
        display_name = _format_display_name(tool_name)
        print(f"\n    🔧 {display_name}", flush=True)
        if arguments:
            if tool_name == "internal__think":
                thought = arguments.get("thought", "")
                for line in thought.splitlines():
                    print(f"       {line}")
            else:
                print(f"       {self._format_args(arguments)}")

    def show_progress(self, status: str, detail: str = "") -> None:
        # Minimal progress for plain mode -- only show on verbose
        pass

    def show_text_delta(self, text: str) -> None:
        # PlainRenderer doesn't stream text -- the final result is printed by the caller
        pass

    def show_text_done(self) -> None:
        pass

    def show_warning(self, message: str) -> None:
        print(f"  [!] {message}", flush=True)

    def show_error(self, message: str) -> None:
        print(f"  [ERROR] {message}", flush=True)

    def on_inner_execution(self, chunk: Any) -> None:
        """Handle raw inner execution chunks from agent.on_inner_execution."""
        if isinstance(chunk, dict):
            if chunk.get("type") == "tool_use":
                self.show_inner_tool_call(chunk.get("name", "?"), chunk.get("input", {}))
            elif chunk.get("type") == "error":
                self.show_error(chunk.get("message", "Unknown error"))
        # Text chunks are silently ignored (agent reasoning, not for display)

    def _format_args(self, input_dict: dict, max_len: int = 100) -> str:
        return _format_args_plain(input_dict, max_len)


def _format_args_rich(input_dict: dict, max_len: int = 100) -> str:
    """Format tool arguments for Rich display (with markup escaping)."""
    from rich.markup import escape

    parts = []
    for key, value in input_dict.items():
        value_str = str(value).replace("\n", " ").replace("\r", "")
        if len(value_str) > max_len:
            value_str = value_str[:max_len] + "..."
        parts.append(f"{key}={escape(value_str)}")
    return ", ".join(parts)


class RichRenderer:
    """Rich console renderer with Live widgets, spinners, and Markdown streaming."""

    def __init__(self, console: "Console", assistant_name: str = "Assistant"):
        self._console = console
        self._assistant_name = assistant_name
        self._live: Any = None
        self._live_running = False
        self._full_response = ""
        self._committed_response = ""
        self._response_started = False
        self._status = "Starting..."

    def start(self):
        """Start the initial spinner display."""
        from rich.live import Live
        from rich.spinner import Spinner

        spinner = Spinner("dots", text=self._status, style="cyan")
        self._live = Live(spinner, console=self._console, refresh_per_second=10)
        self._live.start()
        self._live_running = True
        self._full_response = ""
        self._committed_response = ""
        self._response_started = False

    def stop(self):
        """Stop and clean up the display."""
        if self._live_running and self._live:
            self._live.stop()
            self._live_running = False
        self._live = None

    def show_tool_call(self, tool_name: str, arguments: dict) -> None:
        # Stop Live before printing to avoid display corruption
        if self._live_running and self._live:
            self._live.stop()
            self._live_running = False
        # Mark current text as committed (already printed by live.stop())
        self._committed_response = self._full_response

        display_name = _format_display_name(tool_name)
        self._console.print(f"\n[dim]🔧 {display_name}[/dim]")
        if arguments:
            if tool_name == "internal__think":
                thought = arguments.get("thought", "")
                for line in thought.splitlines():
                    self._console.print(f"[dim]   {line}[/dim]")
            else:
                self._console.print(f"[dim]   {_format_args_rich(arguments)}[/dim]")

        # Restart with spinner
        self._restart_spinner()

    def show_inner_tool_call(self, tool_name: str, arguments: dict) -> None:
        # Stop Live before printing
        if self._live_running and self._live:
            self._live.stop()
            self._live_running = False

        display_name = _format_display_name(tool_name)
        self._console.print(f"\n[dim]  🔧 {display_name}[/dim]")
        if arguments:
            if tool_name == "internal__think":
                thought = arguments.get("thought", "")
                for line in thought.splitlines():
                    self._console.print(f"[dim]     {line}[/dim]")
            else:
                self._console.print(f"[dim]     {_format_args_rich(arguments)}[/dim]")

        # Restart with simple spinner (not full markdown)
        self._restart_spinner(text="  executing prompt...")

    def show_progress(self, status: str, detail: str = "") -> None:
        from rich.spinner import Spinner

        if status == "thinking":
            self._status = "🤔 Analyzing your question..."
        elif status == "calling_claude":
            self._status = "💭 Thinking..."
        elif status == "executing_tool":
            self._status = f"🔧 Using tool: {detail}"
        elif status == "complete":
            self._status = "✨ Complete!"

        # Only update spinner before response streaming starts
        if not self._response_started and self._live_running and self._live:
            self._live.update(Spinner("dots", text=self._status, style="cyan"))

    def show_text_delta(self, text: str) -> None:
        from rich.markdown import Markdown

        if not self._response_started:
            self._console.print()
            self._console.print(f"[bold cyan]{self._assistant_name}:[/bold cyan]")
            self._response_started = True

        self._full_response += text
        new_text = self._full_response[len(self._committed_response) :]
        if self._live:
            self._live.update(Markdown(new_text))

    def show_text_done(self) -> None:
        if self._live_running and self._live:
            self._live.stop()
            self._live_running = False

    def show_warning(self, message: str) -> None:
        self._console.print(f"[yellow]  {message}[/yellow]")

    def show_error(self, message: str) -> None:
        if self._live_running and self._live:
            self._live.stop()
            self._live_running = False
        self._console.print(f"\n[red]{message}[/red]")

    def on_inner_execution(self, chunk: Any) -> None:
        """Handle raw inner execution chunks."""
        if not isinstance(chunk, dict):
            return
        if chunk.get("type") == "tool_use":
            self.show_inner_tool_call(chunk.get("name", "?"), chunk.get("input", {}))
        elif chunk.get("type") == "error":
            self.show_error(chunk.get("message", "Unknown error"))

    def _restart_spinner(self, text: str | None = None) -> None:
        """Restart Live with a simple spinner."""
        from rich.live import Live
        from rich.spinner import Spinner

        spinner = Spinner("dots", text=text or self._status, style="cyan")
        self._live = Live(spinner, console=self._console, refresh_per_second=10)
        self._live.start()
        self._live_running = True
