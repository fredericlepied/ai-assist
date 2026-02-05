"""TUI-enhanced interactive mode for BOSS"""

import asyncio
import os
from pathlib import Path
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from rich.live import Live
from rich.spinner import Spinner
from rich.table import Table

from .agent import BossAgent
from .state import StateManager
from .tui import BossCompleter


async def query_with_feedback(agent: BossAgent, prompt: str, console: Console) -> str:
    """Query the agent with real-time feedback display"""
    # State to track progress
    feedback_state = {
        "status": "Starting...",
        "turn": 0,
        "max_turns": 10,
        "tool": None
    }

    def progress_callback(status: str, turn: int, max_turns: int, tool_name: str | None):
        """Update feedback state"""
        feedback_state["turn"] = turn
        feedback_state["max_turns"] = max_turns
        feedback_state["tool"] = tool_name

        if status == "thinking":
            feedback_state["status"] = "🤔 Analyzing your question..."
        elif status == "calling_claude":
            feedback_state["status"] = f"💭 Thinking... (Turn {turn}/{max_turns})"
        elif status == "executing_tool":
            # Simplify tool names for display
            display_name = tool_name.replace("mcp__", "").replace("__", " → ").replace("_", " ")
            feedback_state["status"] = f"🔧 Using tool: {display_name}"
        elif status == "complete":
            feedback_state["status"] = "✨ Complete!"

    def create_feedback_display():
        """Create the feedback display"""
        spinner = Spinner("dots", text=feedback_state["status"], style="cyan")
        return spinner

    # Use Live to show real-time feedback
    with Live(create_feedback_display(), console=console, refresh_per_second=10) as live:
        response = await agent.query(prompt, progress_callback=progress_callback)
        # Update one last time
        live.update(Text("✨ Complete!", style="green"))

    return response


async def tui_interactive_mode(agent: BossAgent, state_manager: StateManager):
    """Run interactive mode with TUI enhancements"""
    console = Console()

    # Setup history file
    history_file = Path.home() / ".boss" / "interactive_history.txt"
    history_file.parent.mkdir(parents=True, exist_ok=True)

    # Create key bindings for better UX
    # - Enter submits the input (normal behavior)
    # - Meta-Enter (Alt-Enter) adds a newline for multi-line input
    kb = KeyBindings()

    @kb.add('escape', 'enter')  # Esc-Enter adds newline
    @kb.add('c-j')  # Ctrl-J also adds newline (alternative)
    def _(event):
        event.current_buffer.insert_text('\n')

    session = PromptSession(
        message="You> ",
        multiline=False,  # Enter submits by default
        completer=BossCompleter(),
        history=FileHistory(str(history_file)),
        key_bindings=kb
    )

    # Display welcome banner
    console.print(Panel.fit(
        "[bold cyan]BOSS - AI Assistant for Managers[/bold cyan]\n\n"
        "Type your questions or commands.\n"
        "Commands: [yellow]/status[/yellow], [yellow]/history[/yellow], "
        "[yellow]/clear-cache[/yellow], [yellow]/help[/yellow]\n"
        "Type [yellow]/exit[/yellow] or [yellow]/quit[/yellow] to exit\n\n"
        "[dim]Press Enter to submit • Esc-Enter or Ctrl-J for multi-line input • Tab for completion[/dim]",
        border_style="cyan"
    ))

    conversation_context = []

    while True:
        try:
            user_input = await session.prompt_async()
            user_input = user_input.strip()

            if not user_input:
                continue

            if user_input.lower() in ["/exit", "/quit"]:
                state_manager.save_conversation_context(
                    "last_interactive_session",
                    {"messages": conversation_context}
                )
                console.print("\n[cyan]Goodbye![/cyan]")
                break

            # Handle commands
            if user_input.lower() == "/status":
                await handle_status_command(state_manager, console)
                continue

            if user_input.lower() == "/history":
                await handle_history_command(state_manager, console)
                continue

            if user_input.lower() == "/clear-cache":
                await handle_clear_cache_command(state_manager, console)
                continue

            if user_input.lower() == "/help":
                await handle_help_command(console)
                continue

            # Regular query
            try:
                # Show feedback while processing
                response = await query_with_feedback(agent, user_input, console)

                # Render response
                console.print("\n[bold cyan]BOSS:[/bold cyan] ", end="")
                if any(marker in response for marker in ["```", "##", "**", "- ", "1. "]):
                    console.print(Markdown(response))
                else:
                    console.print(response)

                console.print()

                # Track conversation
                conversation_context.append({
                    "user": user_input,
                    "assistant": response,
                    "timestamp": str(asyncio.get_event_loop().time())
                })

            except Exception as e:
                console.print(f"[red]Error: {e}[/red]\n")

        except (EOFError, KeyboardInterrupt):
            state_manager.save_conversation_context(
                "last_interactive_session",
                {"messages": conversation_context}
            )
            console.print("\n[cyan]Goodbye![/cyan]")
            break
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]\n")


async def handle_status_command(state_manager: StateManager, console: Console):
    """Handle /status command"""
    stats = state_manager.get_stats()

    console.print("\n[bold]State Statistics:[/bold]")
    for key, value in stats.items():
        console.print(f"  [cyan]{key}:[/cyan] {value}")
    console.print()


async def handle_history_command(state_manager: StateManager, console: Console):
    """Handle /history command"""
    history = state_manager.get_history("jira_monitor", limit=5)

    console.print(f"\n[bold]Recent Jira checks:[/bold] {len(history)}")
    for entry in history[-3:]:
        console.print(f"  {entry.get('timestamp')}")
    console.print()


async def handle_clear_cache_command(state_manager: StateManager, console: Console):
    """Handle /clear-cache command"""
    removed = state_manager.cleanup_expired_cache()
    console.print(f"\n[green]Cleared {removed} cache entries[/green]\n")


async def handle_help_command(console: Console):
    """Handle /help command"""
    help_text = """
# BOSS Interactive Mode Help

## Commands
- `/status` - Show state statistics
- `/history` - Show recent monitoring history
- `/clear-cache` - Clear expired cache
- `/exit` or `/quit` - Exit interactive mode
- `/help` - Show this help

## Keyboard Shortcuts
- `Enter` - Submit your input
- `Esc-Enter` or `Ctrl-J` - Add newline for multi-line input
- `Tab` - Auto-complete slash commands
- `Up/Down` - Navigate command history
- `Ctrl-R` - Search history (reverse search)
- `Ctrl-C` - Cancel current input
- `Ctrl-D` - Exit

## Tips
- Just press Enter to submit single-line queries
- For multi-line input (paste code, etc.), use Esc-Enter to add newlines
- Tab completion works for all `/` commands
- History is saved across sessions at `~/.boss/interactive_history.txt`
- Responses are formatted as Markdown when possible
"""
    console.print(Markdown(help_text))
    console.print()
