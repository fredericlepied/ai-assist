"""Main entry point for ai-assist"""

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from .config import get_config
from .agent import AiAssistAgent
from .monitors import MonitoringScheduler
from .state import StateManager
from .knowledge_graph import KnowledgeGraph
from .kg_queries import KnowledgeGraphQueries
from .identity import Identity, UserIdentity, AssistantIdentity, get_identity
from .commands import is_valid_interactive_command, get_command_suggestion, is_valid_cli_command


async def handle_prompt_command_basic(command: str, agent: AiAssistAgent, conversation_history: list, identity) -> bool:
    """Handle /server/prompt slash commands for basic mode

    Returns True if command was a prompt command (handled or error)
    Returns False if not a prompt command (continue normal processing)
    """
    # Parse /server/prompt pattern
    parts = command.strip("/").split("/")

    if len(parts) != 2:
        return False  # Not a prompt command

    server_name, prompt_name = parts

    # Validate server exists
    if server_name not in agent.sessions:
        print(f"Unknown MCP server: {server_name}")
        print(f"Connected servers: {', '.join(agent.sessions.keys())}")
        return True

    # Validate server has prompts
    if server_name not in agent.available_prompts:
        print(f"Server '{server_name}' has no prompts")
        return True

    # Validate prompt exists
    if prompt_name not in agent.available_prompts[server_name]:
        print(f"Unknown prompt: {prompt_name}")
        prompts = agent.available_prompts[server_name].keys()
        print(f"Available prompts from {server_name}: {', '.join(prompts)}")
        print("\nTip: Use /prompts to see all available prompts")
        return True

    # Get prompt definition to check for arguments
    prompt_def = agent.available_prompts[server_name][prompt_name]

    # Collect arguments if needed
    arguments = None
    if hasattr(prompt_def, 'arguments') and prompt_def.arguments:
        print(f"\nPrompt '{prompt_name}' requires arguments:")
        print("Press Enter without a value to cancel\n")

        arguments = {}
        for arg in prompt_def.arguments:
            arg_desc = arg.description or arg.name
            required_marker = "*" if arg.required else ""

            try:
                value = input(f"{arg.name}{required_marker}> ").strip()

                # If empty and required, cancel
                if not value and arg.required:
                    print(f"\nCancelled: '{arg.name}' is required\n")
                    return True

                # If empty and optional, skip
                if not value:
                    continue

                arguments[arg.name] = value

            except (KeyboardInterrupt, EOFError):
                print("\nCancelled\n")
                return True

        print()  # Blank line after input

    # Execute the prompt
    try:
        session = agent.sessions[server_name]
        result = await session.get_prompt(prompt_name, arguments=arguments)

        # Convert prompt messages to conversation messages
        for msg in result.messages:
            # Extract text content
            if hasattr(msg.content, 'text'):
                content = msg.content.text
            else:
                content = str(msg.content)

            # Add to conversation history
            conversation_history.append({
                "role": msg.role,
                "content": content
            })

        # Display prompt loaded
        print(f"\n✓ Loaded prompt: {prompt_name} from {server_name}")
        print(f"  Messages added: {len(result.messages)}\n")

        # Automatically send the loaded prompt to Claude
        print(f"{identity.assistant.nickname}: ", end="", flush=True)

        # Query with the messages that now include the prompt
        response = await agent.query(messages=conversation_history)
        print(response)
        print()

        # Add assistant response to messages
        conversation_history.append({"role": "assistant", "content": response})

    except Exception as e:
        print(f"Error executing prompt: {e}")

    return True


def should_use_tui():
    """Auto-detect TUI capability"""
    import sys

    # Check if terminal
    if not sys.stdin.isatty():
        return False

    # Check environment variable
    mode = os.getenv("AI_ASSIST_INTERACTIVE_MODE", "tui").lower()
    if mode == "basic":
        return False

    # Check libraries available
    try:
        import prompt_toolkit
        import rich
        return True
    except ImportError:
        return False


async def interactive_mode(agent: AiAssistAgent, state_manager: StateManager, use_tui: bool = None):
    """Run in interactive mode with TUI or basic fallback"""
    if use_tui is None:
        use_tui = should_use_tui()

    if use_tui:
        try:
            from .tui_interactive import tui_interactive_mode
            await tui_interactive_mode(agent, state_manager)
        except ImportError:
            print("TUI libraries not available, using basic mode")
            print("Install with: pip install 'ai-assist[dev]' prompt-toolkit rich")
            await basic_interactive_mode(agent, state_manager)
    else:
        await basic_interactive_mode(agent, state_manager)


async def basic_interactive_mode(agent: AiAssistAgent, state_manager: StateManager):
    """Original simple interactive mode (fallback)"""
    identity = get_identity()

    print("\n" + "="*60)
    print(f"ai-assist - {identity.get_greeting()}")
    print("="*60)
    print("\nType your questions or commands.")
    print("Commands: /status, /history, /clear-cache, /prompts, /help")
    print("Type /exit or /quit to exit\n")

    conversation_context = []
    messages = []  # For prompt injection

    while True:
        try:
            user_input = input("You: ").strip()

            if not user_input:
                continue

            if user_input.lower() in ["/exit", "/quit"]:
                state_manager.save_conversation_context(
                    "last_interactive_session",
                    {"messages": conversation_context}
                )
                print("Goodbye!")
                break

            # Handle prompt slash commands: /server/prompt
            if user_input.startswith("/"):
                if await handle_prompt_command_basic(user_input, agent, messages, identity):
                    # Prompt was loaded and sent to Claude, continue to next input
                    continue

            # Handle special commands
            if user_input.lower() == "/prompts":
                if not agent.available_prompts:
                    print("No prompts available from MCP servers\n")
                    continue

                print("\nAvailable MCP Prompts:")
                print("="*60)
                for server_name, prompts in agent.available_prompts.items():
                    print(f"\n{server_name}:")
                    for prompt_name, prompt in prompts.items():
                        command = f"/{server_name}/{prompt_name}"
                        description = prompt.description or "(no description)"
                        print(f"  {command:30s} - {description}")
                print()
                continue

            if user_input.lower() == "/status":
                stats = state_manager.get_stats()
                print(f"\nState Statistics:")
                for key, value in stats.items():
                    print(f"  {key}: {value}")
                print()
                continue

            if user_input.lower() == "/history":
                history = state_manager.get_history("jira_monitor", limit=5)
                print(f"\nRecent Jira checks: {len(history)}")
                for entry in history[-3:]:
                    print(f"  {entry.get('timestamp')}")
                print()
                continue

            if user_input.lower() == "/clear-cache":
                removed = state_manager.cleanup_expired_cache()
                print(f"\nCleared {removed} cache entries\n")
                continue

            if user_input.lower() == "/help":
                print("\nai-assist Interactive Mode Help")
                print("="*60)
                print("Commands:")
                print("  /status           - Show state statistics")
                print("  /history          - Show recent monitoring history")
                print("  /clear-cache      - Clear expired cache")
                print("  /prompts          - List available MCP prompts")
                print("  /server/prompt    - Load an MCP prompt (e.g., /dci/rca)")
                print("  /exit, /quit      - Exit interactive mode")
                print("  /help             - Show this help")
                print("\nMCP Prompts:")
                print("  Use /prompts to see all available prompts")
                print("  Execute with /server_name/prompt_name")
                print("  If arguments needed, ai-assist will prompt you interactively")
                print("  Required arguments marked with * - press Enter to cancel")
                print()
                continue

            # Validate command before sending to agent
            if not is_valid_interactive_command(user_input):
                print(f"\n{get_command_suggestion(user_input, is_interactive=True)}\n")
                continue

            print(f"\n{identity.assistant.nickname}: ", end="", flush=True)

            # Add user message to messages list
            messages.append({"role": "user", "content": user_input})

            # Query with full message history (including any injected prompts)
            response = await agent.query(messages=messages)
            print(response)
            print()

            # Add assistant response to messages
            messages.append({"role": "assistant", "content": response})

            # Track conversation
            conversation_context.append({
                "user": user_input,
                "assistant": response,
                "timestamp": str(asyncio.get_event_loop().time())
            })

        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            print(f"\nError: {e}\n")


async def monitoring_mode(
    agent: AiAssistAgent,
    config,
    state_manager: StateManager,
    knowledge_graph: KnowledgeGraph
):
    """Run in monitoring mode"""
    schedule_file = Path.home() / ".ai-assist" / "schedules.json"

    scheduler = MonitoringScheduler(
        agent,
        config,
        state_manager,
        knowledge_graph,
        schedule_file=schedule_file
    )

    try:
        await scheduler.start()
    except KeyboardInterrupt:
        print("\nStopping monitoring...")
        scheduler.stop()


async def run_query(agent: AiAssistAgent, query: str):
    """Run a single query"""
    response = await agent.query(query)
    print(response)


def kg_stats_command(kg: KnowledgeGraph):
    """Show knowledge graph statistics"""
    stats = kg.get_stats()
    print("\nKnowledge Graph Statistics:")
    print("=" * 50)
    print(f"Database: {stats['db_path']}")
    print(f"Total entities: {stats['total_entities']}")
    print(f"Total relationships: {stats['total_relationships']}")
    print("\nEntities by type:")
    for entity_type, count in stats['entities_by_type'].items():
        print(f"  {entity_type:20s}: {count}")
    print("\nRelationships by type:")
    for rel_type, count in stats['relationships_by_type'].items():
        print(f"  {rel_type:20s}: {count}")
    print()


def kg_asof_command(kg: KnowledgeGraph, time_str: str):
    """Show what ai-assist knew at a specific time"""
    try:
        time = datetime.fromisoformat(time_str)
    except ValueError:
        print(f"Error: Invalid time format '{time_str}'. Use ISO format like '2026-02-04 14:00'")
        return

    queries = KnowledgeGraphQueries(kg)
    results = queries.what_did_we_know_at(time)

    print(f"\nWhat ai-assist knew at {time.isoformat()}:")
    print("=" * 50)
    print(f"Total entities: {len(results)}")
    for entity in results[:20]:  # Limit to 20 for display
        print(f"\n{entity['type']}: {entity['id']}")
        print(f"  Valid from: {entity['valid_from']}")
        print(f"  Known since: {entity['known_since']}")
        print(f"  Data: {json.dumps(entity['data'], indent=2)}")

    if len(results) > 20:
        print(f"\n... and {len(results) - 20} more entities")
    print()


def kg_late_command(kg: KnowledgeGraph, min_delay: int = 30):
    """Show entities discovered late"""
    queries = KnowledgeGraphQueries(kg)
    late = queries.find_late_discoveries(min_delay_minutes=min_delay)

    print(f"\nEntities discovered >{min_delay} minutes after they occurred:")
    print("=" * 50)
    print(f"Total: {len(late)}")
    for entity in late[:20]:
        print(f"\n{entity['type']}: {entity['id']}")
        print(f"  Valid from: {entity['valid_from']}")
        print(f"  Discovered: {entity['discovered_at']}")
        print(f"  Lag: {entity['lag_human']} ({entity['lag_minutes']} minutes)")
        print(f"  Data: {json.dumps(entity['data'], indent=2)}")

    if len(late) > 20:
        print(f"\n... and {len(late) - 20} more entities")
    print()


def kg_changes_command(kg: KnowledgeGraph, hours: int = 1):
    """Show recent changes"""
    queries = KnowledgeGraphQueries(kg)
    changes = queries.what_changed_recently(hours=hours)

    print(f"\nChanges in the last {hours} hour(s):")
    print("=" * 50)
    print(f"New entities: {changes['new_count']}")
    print(f"Corrected beliefs: {changes['corrected_count']}")

    if changes['new_entities']:
        print("\nNew entities:")
        for entity in changes['new_entities'][:10]:
            print(f"  {entity['type']}: {entity['id']}")
            print(f"    Discovered: {entity['discovered_at']}")

    if changes['corrected_entities']:
        print("\nCorrected beliefs:")
        for entity in changes['corrected_entities'][:10]:
            print(f"  {entity['type']}: {entity['id']}")
    print()


def kg_show_command(kg: KnowledgeGraph, entity_id: str):
    """Show entity details with context"""
    queries = KnowledgeGraphQueries(kg)

    # Check entity type first
    entity = kg.get_entity(entity_id)
    if not entity:
        print(f"Entity not found: {entity_id}")
        return

    # Handle based on type
    if entity.entity_type == "jira_ticket":
        context = queries.get_ticket_with_context(entity_id)
        print(f"\nTicket: {context['id']}")
        print("=" * 50)
        print(f"Key: {context['data'].get('key', 'N/A')}")
        print(f"Summary: {context['data'].get('summary', 'N/A')}")
        print(f"Status: {context['data'].get('status', 'N/A')}")
        print(f"Valid from: {context['valid_from']}")
        print(f"Discovered: {context['discovered_at']}")
        print(f"\nRelated jobs ({len(context['related_jobs'])}):")
        for job in context['related_jobs']:
            print(f"  - {job['job_id']}: {job['data'].get('status', 'unknown')}")
        print()
        return

    if entity.entity_type == "dci_job":
        context = queries.get_job_with_context(entity_id)
        print(f"\nJob: {context['id']}")
        print("=" * 50)
        print(f"Status: {context['data'].get('status', 'unknown')}")
        print(f"Valid from: {context['valid_from']}")
        if context['valid_to']:
            print(f"Valid to: {context['valid_to']}")
        print(f"Discovered: {context['discovered_at']}")
        print(f"Discovery lag: {context['discovery_lag']}")
        print(f"\nComponents ({len(context['components'])}):")
        for comp in context['components']:
            print(f"  - {comp['data']['type']} {comp['data'].get('version', '')}")
        print(f"\nTickets ({len(context['tickets'])}):")
        for ticket in context['tickets']:
            print(f"  - {ticket['data'].get('key', ticket['entity_id'])}")
        print()
        return

    # Fallback to basic entity lookup
    print(f"\nEntity: {entity.id}")
    print("=" * 50)
    print(f"Type: {entity.entity_type}")
    print(f"Valid from: {entity.valid_from.isoformat()}")
    if entity.valid_to:
        print(f"Valid to: {entity.valid_to.isoformat()}")
    print(f"Discovered: {entity.tx_from.isoformat()}")
    print(f"Data: {json.dumps(entity.data, indent=2)}")
    print()


def identity_show_command():
    """Show current identity configuration"""
    identity = get_identity()

    print("\nCurrent Identity:")
    print("=" * 50)
    print(f"User: {identity.user.name}")
    print(f"Role: {identity.user.role}")
    if identity.user.organization:
        print(f"Organization: {identity.user.organization}")
    if identity.user.timezone:
        print(f"Timezone: {identity.user.timezone}")
    if identity.user.context:
        print(f"\nUser Context:")
        print(f"  {identity.user.context[:200]}..." if len(identity.user.context) > 200 else f"  {identity.user.context}")

    print(f"\nAssistant:")
    print(f"  Nickname: {identity.assistant.nickname}")
    if identity.assistant.personality:
        print(f"  Custom Personality: Yes")

    print(f"\nPreferences:")
    print(f"  Formality: {identity.preferences.formality}")
    print(f"  Verbosity: {identity.preferences.verbosity}")
    print(f"  Emoji Usage: {identity.preferences.emoji_usage}")

    print("\nSystem Prompt Preview:")
    print("-" * 50)
    prompt = identity.get_system_prompt()
    # Truncate if too long for display
    if len(prompt) > 500:
        print(prompt[:500] + "...")
    else:
        print(prompt)
    print()


def identity_init_command():
    """Initialize identity interactively"""
    print("\nInitialize ai-assist Identity")
    print("=" * 50)

    # Gather information
    name = input("Your name: ").strip() or "there"
    role = input("Your role/title [Manager]: ").strip() or "Manager"
    organization = input("Organization (optional): ").strip() or None
    nickname = input("Assistant nickname [Nexus]: ").strip() or "Nexus"

    # Create identity
    identity = Identity(
        user=UserIdentity(
            name=name,
            role=role,
            organization=organization
        ),
        assistant=AssistantIdentity(nickname=nickname)
    )

    # Save
    identity.save_to_file()
    print(f"\n✓ Identity saved to {Path.home() / '.ai-assist' / 'identity.yaml'}")
    print(f"\n{identity.get_greeting()}")
    print()


async def main_async():
    """Async main function"""
    config = get_config()

    # Parse command - must start with /
    command = sys.argv[1] if len(sys.argv) > 1 else None

    if command and not command.startswith('/'):
        print(f"Error: Commands must start with /")
        print(f"Did you mean: /{command}?")
        print("\nRun 'ai-assist /help' to see available commands")
        sys.exit(1)

    if command:
        command = command[1:]  # Remove leading /

    # Validate command early - before initializing agent
    if command and not is_valid_cli_command(command):
        print(get_command_suggestion(f"/{command}", is_interactive=False))
        sys.exit(1)

    # Define which commands need the agent
    kg_commands = ["kg-stats", "kg-asof", "kg-late", "kg-changes", "kg-show"]
    identity_commands = ["identity-show", "identity-init"]
    state_commands = ["status", "clear-cache"]
    no_agent_commands = kg_commands + identity_commands + state_commands + ["help"]

    needs_agent = command not in no_agent_commands

    if needs_agent and not config.anthropic_api_key and not config.vertex_project_id:
        print("\n" + "="*60)
        print("ERROR: No Anthropic credentials configured")
        print("="*60)
        print("\nai-assist requires Anthropic API access to function.")
        print("\nYou have TWO options:")
        print("\n1. VERTEX AI (Google Cloud) - Recommended for enterprise:")
        print("   • Set environment variables:")
        print("     export ANTHROPIC_VERTEX_PROJECT_ID='your-gcp-project-id'")
        print("     # ANTHROPIC_VERTEX_REGION='us-east5'  # optional, usually not needed")
        print("   • Requires Google Cloud authentication (gcloud auth)")
        print("   • Used by Claude Code and enterprise deployments")
        print("\n2. DIRECT API KEY (Personal/Free tier):")
        print("   • Visit: https://console.anthropic.com/")
        print("   • Create an account and get your API key")
        print("   • Add to .env file: ANTHROPIC_API_KEY=your-key-here")
        print("   • Free tier: $5 credit for new accounts")
        print("\nFor more info, see: https://docs.anthropic.com/")
        print("="*60 + "\n")
        sys.exit(1)

    # Initialize state manager and knowledge graph
    state_manager = StateManager()
    knowledge_graph = KnowledgeGraph()

    # Only initialize agent if needed (with knowledge graph for interactive learning)
    agent = AiAssistAgent(config, knowledge_graph=knowledge_graph) if needs_agent else None

    try:
        if agent:
            await agent.connect_to_servers()

        # Parse command line arguments
        if command:

            if command == "help":
                print("\nai-assist - AI Assistant for Managers")
                print("="*60)
                print("\nAvailable commands:")
                print("  /monitor           - Start monitoring DCI and Jira")
                print("  /query '<text>'    - Run a one-time query")
                print("  /interactive       - Interactive mode")
                print("  /status            - Show state statistics")
                print("  /clear-cache       - Clear expired cache")
                print("  /identity-show     - Show current identity configuration")
                print("  /identity-init     - Initialize identity interactively")
                print("  /kg-stats          - Show knowledge graph statistics")
                print("  /kg-asof '<time>'  - What ai-assist knew at a specific time")
                print("  /kg-late [min]     - Show late discoveries (default: 30 min)")
                print("  /kg-changes [hrs]  - Show recent changes (default: 1 hour)")
                print("  /kg-show <id>      - Show entity details with context")
                print("\nRun without arguments for interactive mode\n")
                sys.exit(0)

            elif command == "monitor":
                await monitoring_mode(agent, config, state_manager, knowledge_graph)
            elif command == "query":
                if len(sys.argv) < 3:
                    print("Usage: ai-assist /query 'your question here'")
                    sys.exit(1)
                query = " ".join(sys.argv[2:])
                await run_query(agent, query)
            elif command == "interactive":
                await interactive_mode(agent, state_manager)
            elif command == "status":
                stats = state_manager.get_stats()
                print("\nai-assist State Statistics:")
                print("=" * 40)
                for key, value in stats.items():
                    print(f"{key:20s}: {value}")
                print()
            elif command == "clear-cache":
                removed = state_manager.cleanup_expired_cache()
                print(f"Cleared {removed} expired cache entries")
            # Identity commands
            elif command == "identity-show":
                identity_show_command()
            elif command == "identity-init":
                identity_init_command()
            # Knowledge graph commands
            elif command == "kg-stats":
                kg_stats_command(knowledge_graph)
            elif command == "kg-asof":
                if len(sys.argv) < 3:
                    print("Usage: ai-assist /kg-asof '2026-02-04 14:00'")
                    sys.exit(1)
                time_str = sys.argv[2]
                kg_asof_command(knowledge_graph, time_str)
            elif command == "kg-late":
                min_delay = int(sys.argv[2]) if len(sys.argv) > 2 else 30
                kg_late_command(knowledge_graph, min_delay)
            elif command == "kg-changes":
                hours = int(sys.argv[2]) if len(sys.argv) > 2 else 1
                kg_changes_command(knowledge_graph, hours)
            elif command == "kg-show":
                if len(sys.argv) < 3:
                    print("Usage: ai-assist /kg-show <entity-id>")
                    sys.exit(1)
                entity_id = sys.argv[2]
                kg_show_command(knowledge_graph, entity_id)
            # Note: Unknown commands are caught earlier, before agent initialization
        else:
            # Default to interactive mode
            await interactive_mode(agent, state_manager)

    finally:
        knowledge_graph.close()
        if agent:
            await agent.close()


def main():
    """Main entry point"""
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        print("\nShutting down...")


if __name__ == "__main__":
    main()
