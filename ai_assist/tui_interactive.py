"""TUI-enhanced interactive mode for ai-assist"""

import asyncio
import json

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table

from .agent import AiAssistAgent
from .commands import get_command_suggestion, is_valid_interactive_command
from .config import get_config_dir
from .config_watcher import ConfigWatcher
from .context import ConversationMemory, KnowledgeGraphContext
from .file_watchdog import FileWatchdog
from .identity import get_identity
from .knowledge_graph import KnowledgeGraph
from .state import StateManager
from .tui import AiAssistCompleter


async def display_notification(console: Console, notification: dict):
    """Display a notification in the TUI"""
    # Icon based on level
    icons = {
        "info": "ℹ️",
        "success": "✅",
        "warning": "⚠️",
        "error": "❌",
    }
    icon = icons.get(notification.get("level", "info"), "🔔")

    # Color based on level
    colors = {
        "info": "cyan",
        "success": "green",
        "warning": "yellow",
        "error": "red",
    }
    color = colors.get(notification.get("level", "info"), "white")

    panel = Panel(
        f"{notification['message']}\n\n[dim]{notification['timestamp']}[/dim]",
        title=f"{icon} {notification['title']}",
        border_style=color,
    )

    console.print("\n")
    console.print(panel)
    console.print("\n")


class NotificationWatcher:
    """Watch notification log and display new notifications in TUI"""

    def __init__(self, console: Console):
        self.console = console
        self.notification_log = get_config_dir() / "notifications.log"
        self.watchdog = None
        self.last_position = 0

        # Initialize last position to end of file
        if self.notification_log.exists():
            with open(self.notification_log) as f:
                f.seek(0, 2)  # Seek to end
                self.last_position = f.tell()

    async def on_file_change(self):
        """Called when notifications.log changes"""
        if not self.notification_log.exists():
            return

        try:
            with open(self.notification_log) as f:
                # Seek to last known position
                f.seek(self.last_position)

                # Read new lines
                new_lines = f.readlines()
                self.last_position = f.tell()

                # Display each new notification
                for line in new_lines:
                    try:
                        notification = json.loads(line.strip())
                        await display_notification(self.console, notification)
                    except json.JSONDecodeError:
                        pass  # Skip malformed lines
        except Exception as e:
            print(f"Error reading notification log: {e}")

    async def start(self):
        """Start watching notification log"""
        self.watchdog = FileWatchdog(self.notification_log, self.on_file_change, debounce_seconds=0.1)
        await self.watchdog.start()

    async def stop(self):
        """Stop watching notification log"""
        if self.watchdog:
            await self.watchdog.stop()


async def query_with_feedback(
    agent: AiAssistAgent,
    prompt: str,
    console: Console,
    conversation_memory: ConversationMemory = None,
    kg_context: KnowledgeGraphContext = None,
) -> str:
    """Query the agent with real-time feedback and streaming display

    Args:
        agent: The AiAssistAgent instance
        prompt: User's current question
        console: Rich console for output
        conversation_memory: Optional conversation history for context
        kg_context: Optional knowledge graph context for prompt enrichment

    Returns:
        The assistant's response text
    """
    identity = get_identity()

    # Enrich prompt with knowledge graph context if available
    context_summary = []
    if kg_context:
        prompt, context_summary = kg_context.enrich_prompt(prompt)
    # State to track progress
    feedback_state = {"status": "Starting...", "turn": 0, "max_turns": 50, "tool": None, "streaming": False}

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
            prompt=prompt if messages is None else None, messages=messages, progress_callback=progress_callback
        ):
            # Handle text chunks
            if isinstance(chunk, str):
                # First text chunk - stop spinner and start showing response
                if not response_started:
                    live.stop()
                    console.print(f"\n[bold cyan]{identity.assistant.nickname}:[/bold cyan] ", end="")
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
                    console.print(f"\n[dim]🔧 {display_name}[/dim]")

                    # Display arguments if present
                    if chunk.get("input"):
                        args_display = []
                        for key, value in chunk["input"].items():
                            # Truncate long values
                            value_str = str(value)
                            if len(value_str) > 100:
                                value_str = value_str[:100] + "..."
                            args_display.append(f"{key}={value_str}")
                        console.print(f"[dim]   {', '.join(args_display)}[/dim]")
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
            console.print(
                f"[dim]💾 Saved {kg_saved_count} entit{'y' if kg_saved_count == 1 else 'ies'} to knowledge graph[/dim]"
            )

        # Clear tool calls for next query
        agent.clear_tool_calls()

    return full_response


async def handle_skill_management_command(command: str, agent: AiAssistAgent, console: Console) -> bool:
    """Handle /skill/* management commands

    Returns True if command was handled
    """
    if not command.startswith("/skill/"):
        return False

    parts = command[7:].split(maxsplit=1)  # Remove '/skill/' prefix
    if not parts:
        console.print("[yellow]Usage: /skill/install <source>@<branch> or /skill/uninstall <name>[/yellow]")
        return True

    subcommand = parts[0]

    if subcommand == "install":
        if len(parts) < 2:
            console.print("[yellow]Usage: /skill/install <source>@<branch>[/yellow]")
            console.print("Examples:")
            console.print("  /skill/install anthropics/skills/skills/pdf@main")
            console.print("  /skill/install /home/user/skills/perso@main")
            return True

        source_spec = parts[1]
        with console.status(f"Installing skill from {source_spec}..."):
            result = agent.skills_manager.install_skill(source_spec)

        if result.startswith("Error"):
            console.print(f"[red]{result}[/red]")
        else:
            console.print(f"[green]{result}[/green]")
        return True

    elif subcommand == "uninstall":
        if len(parts) < 2:
            console.print("[yellow]Usage: /skill/uninstall <skill-name>[/yellow]")
            return True

        skill_name = parts[1]
        result = agent.skills_manager.uninstall_skill(skill_name)

        if result.startswith("Error"):
            console.print(f"[red]{result}[/red]")
        else:
            console.print(f"[green]{result}[/green]")
        return True

    elif subcommand == "list":
        result = agent.skills_manager.list_installed()
        console.print(result)
        return True

    else:
        console.print(f"[yellow]Unknown skill command: {subcommand}[/yellow]")
        console.print("Available: /skill/install, /skill/uninstall, /skill/list")
        return True


async def handle_prompt_command(
    command: str, agent: AiAssistAgent, conversation_history: list, console: Console, prompt_session: PromptSession
) -> bool:
    """Handle /server/prompt slash commands

    Returns True if command was a prompt command (handled or error)
    Returns False if not a prompt command (continue normal processing)
    """
    # Parse /server/prompt pattern
    # Must be exactly 2 parts to avoid conflicts with built-in commands
    parts = command.strip("/").split("/")

    if len(parts) != 2:
        return False  # Not a prompt command (could be /status, /help, etc.)

    server_name, prompt_name = parts

    # Validate server exists (connected MCP server)
    if server_name not in agent.sessions:
        console.print(f"[yellow]Unknown MCP server: {server_name}[/yellow]")
        console.print(f"Connected servers: {', '.join(agent.sessions.keys())}")
        return True

    # Validate server has prompts
    if server_name not in agent.available_prompts:
        console.print(f"[yellow]Server '{server_name}' has no prompts[/yellow]")
        return True

    # Validate prompt exists in this server
    if prompt_name not in agent.available_prompts[server_name]:
        console.print(f"[yellow]Unknown prompt: {prompt_name}[/yellow]")
        prompts = agent.available_prompts[server_name].keys()
        console.print(f"Available prompts from {server_name}: {', '.join(prompts)}")
        console.print("\nTip: Use /prompts to see all available prompts")
        return True

    # Get prompt definition to check for arguments
    prompt_def = agent.available_prompts[server_name][prompt_name]

    # Collect arguments if needed
    arguments = None
    if hasattr(prompt_def, "arguments") and prompt_def.arguments:
        console.print(f"\n[cyan]Prompt '{prompt_name}' requires arguments:[/cyan]")
        console.print("[dim]Press Enter without a value to cancel[/dim]\n")

        arguments = {}

        # Create a separate session for argument collection to avoid state pollution
        from prompt_toolkit import PromptSession as ArgPromptSession

        arg_session = ArgPromptSession()

        for arg in prompt_def.arguments:
            # Use plain text for prompt_toolkit (no Rich markup)
            required_marker = "*" if arg.required else ""

            try:
                value = await arg_session.prompt_async(f"{arg.name}{required_marker}> ")
                value = value.strip()

                # If empty and required, cancel
                if not value and arg.required:
                    console.print(f"\n[yellow]Cancelled: '{arg.name}' is required[/yellow]\n")
                    return True

                # If empty and optional, skip
                if not value:
                    continue

                arguments[arg.name] = value

            except (KeyboardInterrupt, EOFError):
                console.print("\n[yellow]Cancelled[/yellow]\n")
                return True

        console.print()  # Blank line after input

    # Execute the prompt
    try:
        session = agent.sessions[server_name]
        result = await session.get_prompt(prompt_name, arguments=arguments)

        # Convert prompt messages to conversation messages
        prompt_content = []
        for msg in result.messages:
            # Extract text content
            if hasattr(msg.content, "text"):
                content = msg.content.text
            else:
                content = str(msg.content)

            # Add to conversation history
            conversation_history.append({"role": msg.role, "content": content})
            prompt_content.append(content)

        # Display prompt content to user
        console.print(
            Panel(
                (
                    f"[green]Injected prompt: {prompt_name}[/green]\n"
                    f"From: {server_name}\n"
                    f"Messages added: {len(result.messages)}\n\n"
                    f"[dim]{prompt_content[0][:200]}...[/dim]"
                    if prompt_content
                    else ""
                ),
                title="Prompt Loaded",
            )
        )

    except Exception as e:
        console.print(f"[red]Error executing prompt: {e}[/red]")

    return True


async def tui_interactive_mode(agent: AiAssistAgent, state_manager: StateManager):
    """Run interactive mode with TUI enhancements"""
    console = Console()
    identity = get_identity()

    # Setup history file
    history_file = get_config_dir() / "interactive_history.txt"
    history_file.parent.mkdir(parents=True, exist_ok=True)

    # Create key bindings for better UX
    # - Enter submits the input (normal behavior)
    # - Meta-Enter (Alt-Enter) adds a newline for multi-line input
    kb = KeyBindings()

    @kb.add("escape", "enter")  # Esc-Enter adds newline
    @kb.add("c-j")  # Ctrl-J also adds newline (alternative)
    def _(event):
        event.current_buffer.insert_text("\n")

    session = PromptSession(
        message="You> ",
        multiline=False,  # Enter submits by default
        completer=AiAssistCompleter(agent=agent),
        history=FileHistory(str(history_file)),
        key_bindings=kb,
    )

    # Display welcome banner
    skills_status = (
        f"[dim]🚀 {len(agent.skills_manager.installed_skills)} Agent Skills loaded[/dim]\n"
        if agent.skills_manager.installed_skills
        else "[dim]💡 Install Agent Skills with /skill/install[/dim]\n"
    )

    console.print(
        Panel.fit(
            f"[bold cyan]ai-assist - {identity.get_greeting()}[/bold cyan]\n\n"
            "Type your questions or commands.\n"
            "Commands: [yellow]/status[/yellow], [yellow]/history[/yellow], "
            "[yellow]/clear-cache[/yellow], [yellow]/kg-save[/yellow], [yellow]/prompts[/yellow], "
            "[yellow]/skill/list[/yellow], [yellow]/help[/yellow]\n"
            "Type [yellow]/exit[/yellow] or [yellow]/quit[/yellow] to exit\n\n"
            "[dim]🧠 Auto-learning enabled - Tool results saved to knowledge graph[/dim]\n"
            "[dim]🎯 MCP prompts available - Use /prompts to see them[/dim]\n"
            f"{skills_status}"
            "[dim]Press Enter to submit • Esc-Enter or Ctrl-J for multi-line input • Tab for completion[/dim]",
            border_style="cyan",
        )
    )

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

    # Start config watching (mcp_servers.yaml, identity.yaml, installed-skills.json)
    config_watcher = ConfigWatcher(agent)
    await config_watcher.start()

    # Start notification watching for cross-process notifications
    notification_watcher = NotificationWatcher(console)
    await notification_watcher.start()

    try:
        while True:
            try:
                user_input = await session.prompt_async()
                user_input = user_input.strip()

                if not user_input:
                    continue

                if user_input.lower() in ["/exit", "/quit"]:
                    state_manager.save_conversation_context(
                        "last_interactive_session", {"messages": conversation_context}
                    )
                    console.print("\n[cyan]Goodbye![/cyan]")
                    break

                # Handle slash commands
                if user_input.startswith("/"):
                    # Try skill management commands: /skill/install, /skill/uninstall, /skill/list
                    if await handle_skill_management_command(user_input, agent, console):
                        continue

                    # Convert conversation_memory to messages for prompt injection
                    messages = conversation_memory.to_messages()
                    if await handle_prompt_command(user_input, agent, messages, console, session):
                        # Automatically send the loaded prompt to Claude
                        # The prompt has been injected into 'messages' and is the last user message
                        try:
                            console.print()  # Blank line before response

                            # Use streaming query with the messages that now include the prompt
                            full_response = ""
                            response_started = False
                            identity = get_identity()

                            async for chunk in agent.query_streaming(messages=messages, progress_callback=None):
                                # Handle text chunks
                                if isinstance(chunk, str):
                                    if not response_started:
                                        console.print()  # Blank line before agent message
                                        console.print(f"[bold cyan]{identity.assistant.nickname}:[/bold cyan] ", end="")
                                        response_started = True
                                    console.print(chunk, end="")
                                    full_response += chunk

                                # Handle tool use notifications
                                elif isinstance(chunk, dict):
                                    if chunk.get("type") == "tool_use":
                                        if response_started:
                                            console.print()
                                        tool_name = chunk["name"]
                                        display_name = (
                                            tool_name.replace("mcp__", "").replace("__", " → ").replace("_", " ")
                                        )

                                        # Show tool call with arguments
                                        console.print(f"\n[dim]🔧 {display_name}[/dim]")

                                        # Display arguments if present
                                        if chunk.get("input"):
                                            args_display = []
                                            for key, value in chunk["input"].items():
                                                # Truncate long values
                                                value_str = str(value)
                                                if len(value_str) > 100:
                                                    value_str = value_str[:100] + "..."
                                                args_display.append(f"{key}={value_str}")
                                            console.print(f"[dim]   {', '.join(args_display)}[/dim]")
                                    elif chunk.get("type") == "done":
                                        if response_started:
                                            console.print()
                                        break
                                    elif chunk.get("type") == "error":
                                        if response_started:
                                            console.print()
                                        console.print(f"\n[red]{chunk.get('message')}[/red]")
                                        break

                            # Show KG save feedback if entities were saved
                            kg_saved_count = agent.get_last_kg_saved_count()
                            if kg_saved_count > 0:
                                console.print(
                                    f"[dim]💾 Saved {kg_saved_count} entit{'y' if kg_saved_count == 1 else 'ies'} to knowledge graph[/dim]"
                                )
                            agent.clear_tool_calls()

                            # Extract the prompt content (last user message) for conversation tracking
                            prompt_content = (
                                messages[-1]["content"] if messages and messages[-1]["role"] == "user" else user_input
                            )

                            # Add the exchange to conversation memory
                            conversation_memory.add_exchange(prompt_content, full_response)

                            # Track for state manager
                            conversation_context.append(
                                {
                                    "user": user_input,  # Original /dci/rca command
                                    "assistant": full_response,
                                    "timestamp": str(asyncio.get_event_loop().time()),
                                }
                            )

                        except Exception as e:
                            console.print(f"\n[red]Error: {e}[/red]\n")

                        continue

                # Handle commands
                if user_input.lower() == "/prompts":
                    await handle_prompts_command(agent, console)
                    continue

                if user_input.lower().startswith("/prompt-info "):
                    prompt_ref = user_input[13:].strip()  # Remove "/prompt-info "
                    await handle_prompt_info_command(agent, console, prompt_ref)
                    continue

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

                # Validate command before sending to agent
                if not is_valid_interactive_command(user_input):
                    error_msg = get_command_suggestion(user_input, is_interactive=True)
                    console.print(f"\n[red]{error_msg}[/red]\n")
                    continue

                # Regular query
                try:
                    # Show feedback while processing and stream response
                    response = await query_with_feedback(
                        agent, user_input, console, conversation_memory=conversation_memory, kg_context=kg_context
                    )

                    # Response is already printed via streaming
                    # Just add final newline if not already there
                    if response and not response.endswith("\n"):
                        console.print()

                    # Add to conversation memory for context
                    conversation_memory.add_exchange(user_input, response)

                    # Track conversation in context list for state manager
                    conversation_context.append(
                        {"user": user_input, "assistant": response, "timestamp": str(asyncio.get_event_loop().time())}
                    )

                except (EOFError, KeyboardInterrupt):
                    # Re-raise to be caught by outer handler which breaks the loop
                    raise
                except Exception as e:
                    console.print(f"\n[red]Error: {e}[/red]\n")

            except (EOFError, KeyboardInterrupt):
                state_manager.save_conversation_context("last_interactive_session", {"messages": conversation_context})
                console.print("\n[cyan]Goodbye![/cyan]")
                break
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]\n")
    finally:
        # Stop watchers on exit
        await config_watcher.stop()
        await notification_watcher.stop()


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


async def handle_prompts_command(agent: AiAssistAgent, console: Console):
    """Handle /prompts command - list available MCP prompts"""
    if not agent.available_prompts:
        console.print("[yellow]No prompts available from MCP servers[/yellow]\n")
        return

    table = Table(title="Available MCP Prompts")
    table.add_column("Command", style="cyan")
    table.add_column("Server", style="green")
    table.add_column("Description", style="white")
    table.add_column("Arguments", style="yellow")

    for server_name, prompts in agent.available_prompts.items():
        for prompt_name, prompt in prompts.items():
            command = f"/{server_name}/{prompt_name}"
            description = prompt.description or "(no description)"

            # Format arguments
            args_list = []
            if hasattr(prompt, "arguments") and prompt.arguments:
                for arg in prompt.arguments:
                    arg_name = arg.name
                    if arg.required:
                        args_list.append(f"{arg_name}* (required)")
                    else:
                        args_list.append(f"{arg_name} (optional)")

            args_display = "\n".join(args_list) if args_list else "-"
            table.add_row(command, server_name, description, args_display)

    console.print(table)
    console.print("\n[dim]* = required argument[/dim]")
    console.print("[dim]Use /server/prompt to execute (e.g., /dci/rca)[/dim]\n")


async def handle_prompt_info_command(agent: AiAssistAgent, console: Console, prompt_ref: str):
    """Handle /prompt-info <server/prompt> command - show detailed prompt information"""
    # Parse server/prompt
    parts = prompt_ref.strip("/").split("/")
    if len(parts) != 2:
        console.print("[yellow]Usage: /prompt-info <server>/<prompt>[/yellow]")
        console.print("[dim]Example: /prompt-info dci/rca[/dim]\n")
        return

    server_name, prompt_name = parts

    # Validate server and prompt exist
    if server_name not in agent.available_prompts:
        console.print(f"[yellow]Unknown server: {server_name}[/yellow]")
        console.print(f"Available servers: {', '.join(agent.available_prompts.keys())}\n")
        return

    if prompt_name not in agent.available_prompts[server_name]:
        console.print(f"[yellow]Unknown prompt: {prompt_name}[/yellow]")
        prompts = agent.available_prompts[server_name].keys()
        console.print(f"Available prompts: {', '.join(prompts)}\n")
        return

    # Get prompt definition
    prompt_def = agent.available_prompts[server_name][prompt_name]

    # Display prompt information
    console.print(f"\n[bold cyan]Prompt: {server_name}/{prompt_name}[/bold cyan]")
    console.print(f"[dim]MCP format: mcp://{server_name}/{prompt_name}[/dim]\n")

    if prompt_def.description:
        console.print(f"[white]{prompt_def.description}[/white]\n")

    # Display arguments
    if hasattr(prompt_def, "arguments") and prompt_def.arguments:
        console.print("[bold yellow]Arguments:[/bold yellow]")
        for arg in prompt_def.arguments:
            required = "[red]REQUIRED[/red]" if arg.required else "[dim]optional[/dim]"
            console.print(f"  • [cyan]{arg.name}[/cyan] ({required})")
            if arg.description:
                console.print(f"    [dim]{arg.description}[/dim]")
        console.print()
    else:
        console.print("[dim]No arguments required[/dim]\n")

    # Show example usage
    console.print("[bold]Example Usage:[/bold]")
    console.print(f"[dim]Interactive:[/dim] /{server_name}/{prompt_name}")
    if hasattr(prompt_def, "arguments") and prompt_def.arguments:
        example_args = {arg.name: f"<{arg.name}>" for arg in prompt_def.arguments if arg.required}
        console.print(f"[dim]In task:[/dim] mcp://{server_name}/{prompt_name}")
        console.print(f"[dim]Arguments:[/dim] {example_args}")
    console.print()


async def handle_help_command(console: Console):
    """Handle /help command"""
    help_text = """
# ai-assist Interactive Mode Help

## Commands
- `/status` - Show state statistics
- `/history` - Show recent monitoring history
- `/clear-cache` - Clear expired cache
- `/clear` - Clear conversation memory (start fresh)
- `/kg-save [on|off]` - Toggle knowledge graph auto-save
- `/prompts` - List available MCP prompts
- `/prompt-info <server/prompt>` - Show detailed prompt info
- `/server/prompt` - Load an MCP prompt (e.g., `/dci/rca`)
- `/skill/install <source>@<branch>` - Install an Agent Skill
- `/skill/uninstall <name>` - Uninstall an Agent Skill
- `/skill/list` - List installed Agent Skills
- `/exit` or `/quit` - Exit interactive mode
- `/help` - Show this help

## Agent Skills 🚀
Install specialized skills from git repositories or local paths:
- Use `/skill/list` to see installed skills
- Install with `/skill/install <source>@<branch>`
  - Git: `/skill/install anthropics/skills/skills/pdf@main`
  - Local: `/skill/install /path/to/skill@main`
- Uninstall with `/skill/uninstall <skill-name>`
- Skills are automatically loaded into system prompt
- Follows agentskills.io specification

## MCP Prompts 🎯
Load specialized prompts from MCP servers:
- Use `/prompts` to see all available prompts
- Execute with `/server_name/prompt_name` (e.g., `/dci/weekly`)
- If arguments needed, ai-assist will prompt you interactively
- Required arguments marked with `*` - press Enter to cancel
- Prompts inject expert context into the conversation
- Great for specialized workflows and analysis

## Conversation Memory 💬
ai-assist now remembers your conversation! Follow-up questions work naturally:
- "What are the latest DCI failures?" → ai-assist answers
- "Why did they fail?" → ai-assist knows what "they" refers to!
- Use `/clear` to start a fresh conversation

## Knowledge Graph Learning 🧠
ai-assist automatically saves tool results to the knowledge graph:
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
- History is saved across sessions at `~/.ai-assist/interactive_history.txt`
- Responses are formatted as Markdown when possible
- ai-assist remembers up to 10 recent exchanges for context
"""
    console.print(Markdown(help_text))
    console.print()
