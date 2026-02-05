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
from .context import ConversationMemory, KnowledgeGraphContext
from .knowledge_graph import KnowledgeGraph


async def query_with_feedback(
    agent: BossAgent,
    prompt: str,
    console: Console,
    conversation_memory: ConversationMemory = None,
    kg_context: KnowledgeGraphContext = None
) -> str:
    """Query the agent with real-time feedback and streaming display

    Args:
        agent: The BossAgent instance
        prompt: User's current question
        console: Rich console for output
        conversation_memory: Optional conversation history for context
        kg_context: Optional knowledge graph context for prompt enrichment

    Returns:
        The assistant's response text
    """
    # Enrich prompt with knowledge graph context if available
    original_prompt = prompt
    context_summary = []
    if kg_context:
        prompt, context_summary = kg_context.enrich_prompt(prompt)
    # State to track progress
    feedback_state = {
        "status": "Starting...",
        "turn": 0,
        "max_turns": 10,
        "tool": None,
        "streaming": False
    }

    def progress_callback(status: str, turn: int, max_turns: int, tool_name: str | None):
        """Update feedback state"""
        feedback_state["turn"] = turn
        feedback_state["max_turns"] = max_turns
        feedback_state["tool"] = tool_name

        if status == "thinking":
            feedback_state["status"] = "🤔 Analyzing your question..."
            feedback_state["streaming"] = False
        elif status == "calling_claude":
            feedback_state["status"] = f"💭 Thinking... (Turn {turn}/{max_turns})"
            feedback_state["streaming"] = False
        elif status == "executing_tool":
            # Simplify tool names for display
            display_name = tool_name.replace("mcp__", "").replace("__", " → ").replace("_", " ")
            feedback_state["status"] = f"🔧 Using tool: {display_name}"
            feedback_state["streaming"] = False
        elif status == "complete":
            feedback_state["status"] = "✨ Complete!"
            feedback_state["streaming"] = False

    def create_feedback_display():
        """Create the feedback display"""
        spinner = Spinner("dots", text=feedback_state["status"], style="cyan")
        return spinner

    # Show spinner initially
    live = Live(create_feedback_display(), console=console, refresh_per_second=10)
    live.start()

    full_response = ""
    response_started = False

    try:
        # Show knowledge graph context if any was added
        if context_summary:
            context_text = ", ".join(context_summary)
            console.print(f"[dim]🔍 Knowledge graph context: {context_text}[/dim]")

        # Build messages list with conversation history
        if conversation_memory:
            # Get conversation history and add current prompt
            messages = conversation_memory.to_messages()
            messages.append({"role": "user", "content": prompt})

            # Show context indicator if we have history
            if len(conversation_memory) > 0:
                console.print(f"[dim]💬 Using context from {len(conversation_memory)} previous exchange(s)[/dim]")
        else:
            # No conversation memory - just use prompt
            messages = None

        # Use streaming query with conversation context
        async for chunk in agent.query_streaming(
            prompt=prompt if messages is None else None,
            messages=messages,
            progress_callback=progress_callback
        ):
            # Handle text chunks
            if isinstance(chunk, str):
                # First text chunk - stop spinner and start showing response
                if not response_started:
                    live.stop()
                    console.print("\n[bold cyan]BOSS:[/bold cyan] ", end="")
                    response_started = True

                # Print chunk immediately
                console.print(chunk, end="")
                full_response += chunk

            # Handle tool use notifications
            elif isinstance(chunk, dict):
                if chunk.get("type") == "tool_use":
                    # Show tool call inline
                    if response_started:
                        console.print()  # New line before tool notification
                    tool_name = chunk["name"]
                    display_name = tool_name.replace("mcp__", "").replace("__", " → ").replace("_", " ")
                    console.print(f"\n[dim]🔧 {display_name}[/dim]", end="")
                    if not response_started:
                        live.update(create_feedback_display())  # Keep spinner going

                elif chunk.get("type") == "done":
                    # Query complete
                    if response_started:
                        console.print()  # Final newline
                    break

                elif chunk.get("type") == "error":
                    if response_started:
                        console.print()
                    console.print(f"\n[red]{chunk.get('message')}[/red]")
                    break

    except Exception as e:
        # Handle any streaming errors
        if response_started:
            console.print()
        console.print(f"\n[red]Error: {e}[/red]")

    finally:
        # Ensure spinner is stopped
        if live._started:
            live.stop()

        # If we never started response (no text chunks), stop the spinner
        if not response_started:
            pass  # Already stopped above or never started

        # Show KG save feedback if entities were saved
        kg_saved_count = agent.get_last_kg_saved_count()
        if kg_saved_count > 0:
            console.print(f"[dim]💾 Saved {kg_saved_count} entit{'y' if kg_saved_count == 1 else 'ies'} to knowledge graph[/dim]")

        # Clear tool calls for next query
        agent.clear_tool_calls()

    return full_response


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
        "[yellow]/clear-cache[/yellow], [yellow]/kg-save[/yellow], [yellow]/help[/yellow]\n"
        "Type [yellow]/exit[/yellow] or [yellow]/quit[/yellow] to exit\n\n"
        "[dim]🧠 Auto-learning enabled - Tool results saved to knowledge graph[/dim]\n"
        "[dim]Press Enter to submit • Esc-Enter or Ctrl-J for multi-line input • Tab for completion[/dim]",
        border_style="cyan"
    ))

    # Initialize conversation memory for context-aware responses
    conversation_memory = ConversationMemory(max_exchanges=10)
    conversation_context = []  # For state manager persistence

    # Enable agent introspection of conversation memory
    agent.set_conversation_memory(conversation_memory)

    # Initialize knowledge graph context for prompt enrichment
    try:
        kg = KnowledgeGraph()
        kg_context = KnowledgeGraphContext(kg)
    except Exception:
        # If KG fails to load, disable enrichment
        kg_context = KnowledgeGraphContext(None)

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

            if user_input.lower() == "/clear":
                conversation_memory.clear()
                console.print("\n[green]✓ Conversation memory cleared[/green]\n")
                continue

            if user_input.lower().startswith("/kg-save"):
                parts = user_input.split()
                if len(parts) > 1:
                    if parts[1].lower() in ["on", "true", "1", "yes"]:
                        agent.kg_save_enabled = True
                        console.print("\n[green]✓ Knowledge graph auto-save enabled[/green]\n")
                    elif parts[1].lower() in ["off", "false", "0", "no"]:
                        agent.kg_save_enabled = False
                        console.print("\n[yellow]Knowledge graph auto-save disabled[/yellow]\n")
                    else:
                        console.print("\n[red]Usage: /kg-save [on|off][/red]\n")
                else:
                    status = "enabled" if agent.kg_save_enabled else "disabled"
                    console.print(f"\n[cyan]Knowledge graph auto-save is currently {status}[/cyan]\n")
                continue

            # Regular query
            try:
                # Show feedback while processing and stream response
                response = await query_with_feedback(
                    agent,
                    user_input,
                    console,
                    conversation_memory=conversation_memory,
                    kg_context=kg_context
                )

                # Response is already printed via streaming
                # Just add final newline if not already there
                if response and not response.endswith('\n'):
                    console.print()

                # Add to conversation memory for context
                conversation_memory.add_exchange(user_input, response)

                # Track conversation in context list for state manager
                conversation_context.append({
                    "user": user_input,
                    "assistant": response,
                    "timestamp": str(asyncio.get_event_loop().time())
                })

            except Exception as e:
                console.print(f"\n[red]Error: {e}[/red]\n")

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
- `/clear` - Clear conversation memory (start fresh)
- `/kg-save [on|off]` - Toggle knowledge graph auto-save (NEW!)
- `/exit` or `/quit` - Exit interactive mode
- `/help` - Show this help

## Conversation Memory 💬
BOSS now remembers your conversation! Follow-up questions work naturally:
- "What are the latest DCI failures?" → BOSS answers
- "Why did they fail?" → BOSS knows what "they" refers to!
- Use `/clear` to start a fresh conversation

## Knowledge Graph Learning 🧠
BOSS automatically saves tool results to the knowledge graph:
- When you query Jira or DCI, entities are saved
- Future queries can use cached data (faster!)
- See feedback: "💾 Saved 5 entities to knowledge graph"
- Toggle with `/kg-save on` or `/kg-save off`

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
- BOSS remembers up to 10 recent exchanges for context
"""
    console.print(Markdown(help_text))
    console.print()
