"""Main entry point for BOSS"""

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from .config import get_config
from .agent import BossAgent
from .monitors import MonitoringScheduler
from .state import StateManager
from .knowledge_graph import KnowledgeGraph
from .kg_queries import KnowledgeGraphQueries


def should_use_tui():
    """Auto-detect TUI capability"""
    import sys

    # Check if terminal
    if not sys.stdin.isatty():
        return False

    # Check environment variable
    mode = os.getenv("BOSS_INTERACTIVE_MODE", "tui").lower()
    if mode == "basic":
        return False

    # Check libraries available
    try:
        import prompt_toolkit
        import rich
        return True
    except ImportError:
        return False


async def interactive_mode(agent: BossAgent, state_manager: StateManager, use_tui: bool = None):
    """Run in interactive mode with TUI or basic fallback"""
    if use_tui is None:
        use_tui = should_use_tui()

    if use_tui:
        try:
            from .tui_interactive import tui_interactive_mode
            await tui_interactive_mode(agent, state_manager)
        except ImportError:
            print("TUI libraries not available, using basic mode")
            print("Install with: pip install 'boss[dev]' prompt-toolkit rich")
            await basic_interactive_mode(agent, state_manager)
    else:
        await basic_interactive_mode(agent, state_manager)


async def basic_interactive_mode(agent: BossAgent, state_manager: StateManager):
    """Original simple interactive mode (fallback)"""
    print("\n" + "="*60)
    print("BOSS - AI Assistant for Managers")
    print("="*60)
    print("\nType your questions or commands.")
    print("Commands: /status, /history, /clear-cache, /help")
    print("Type /exit or /quit to exit\n")

    conversation_context = []

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

            # Handle special commands
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
                print("\nBOSS Interactive Mode Help")
                print("="*60)
                print("Commands:")
                print("  /status      - Show state statistics")
                print("  /history     - Show recent monitoring history")
                print("  /clear-cache - Clear expired cache")
                print("  /exit, /quit - Exit interactive mode")
                print("  /help        - Show this help")
                print()
                continue

            print("\nBOSS: ", end="", flush=True)
            response = await agent.query(user_input)
            print(response)
            print()

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
    agent: BossAgent,
    config,
    state_manager: StateManager,
    knowledge_graph: KnowledgeGraph
):
    """Run in monitoring mode"""
    monitor_file = Path.home() / ".boss" / "monitors.yaml"
    task_file = Path.home() / ".boss" / "tasks.yaml"

    scheduler = MonitoringScheduler(
        agent,
        config,
        state_manager,
        knowledge_graph,
        monitor_file=monitor_file if monitor_file.exists() else None,
        task_file=task_file if task_file.exists() else None
    )

    try:
        await scheduler.start()
    except KeyboardInterrupt:
        print("\nStopping monitoring...")
        scheduler.stop()


async def run_query(agent: BossAgent, query: str):
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
    """Show what BOSS knew at a specific time"""
    try:
        time = datetime.fromisoformat(time_str)
    except ValueError:
        print(f"Error: Invalid time format '{time_str}'. Use ISO format like '2026-02-04 14:00'")
        return

    queries = KnowledgeGraphQueries(kg)
    results = queries.what_did_we_know_at(time)

    print(f"\nWhat BOSS knew at {time.isoformat()}:")
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


async def main_async():
    """Async main function"""
    config = get_config()

    # Parse command - must start with /
    command = sys.argv[1] if len(sys.argv) > 1 else None

    if command and not command.startswith('/'):
        print(f"Error: Commands must start with /")
        print(f"Did you mean: /{command}?")
        print("\nRun 'boss /help' to see available commands")
        sys.exit(1)

    if command:
        command = command[1:]  # Remove leading /

    kg_commands = ["kg-stats", "kg-asof", "kg-late", "kg-changes", "kg-show"]
    no_agent_commands = kg_commands + ["help"]
    needs_agent = command not in no_agent_commands

    if needs_agent and not config.anthropic_api_key and not config.vertex_project_id:
        print("\n" + "="*60)
        print("ERROR: No Anthropic credentials configured")
        print("="*60)
        print("\nBOSS requires Anthropic API access to function.")
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

    # Only initialize agent if needed
    agent = BossAgent(config) if needs_agent else None

    try:
        if agent:
            await agent.connect_to_servers()

        # Parse command line arguments
        if command:

            if command == "help":
                print("\nBOSS - AI Assistant for Managers")
                print("="*60)
                print("\nAvailable commands:")
                print("  /monitor           - Start monitoring DCI and Jira")
                print("  /query '<text>'    - Run a one-time query")
                print("  /interactive       - Interactive mode")
                print("  /status            - Show state statistics")
                print("  /clear-cache       - Clear expired cache")
                print("  /kg-stats          - Show knowledge graph statistics")
                print("  /kg-asof '<time>'  - What BOSS knew at a specific time")
                print("  /kg-late [min]     - Show late discoveries (default: 30 min)")
                print("  /kg-changes [hrs]  - Show recent changes (default: 1 hour)")
                print("  /kg-show <id>      - Show entity details with context")
                print("\nRun without arguments for interactive mode\n")
                sys.exit(0)

            elif command == "monitor":
                await monitoring_mode(agent, config, state_manager, knowledge_graph)
            elif command == "query":
                if len(sys.argv) < 3:
                    print("Usage: boss /query 'your question here'")
                    sys.exit(1)
                query = " ".join(sys.argv[2:])
                await run_query(agent, query)
            elif command == "interactive":
                await interactive_mode(agent, state_manager)
            elif command == "status":
                stats = state_manager.get_stats()
                print("\nBOSS State Statistics:")
                print("=" * 40)
                for key, value in stats.items():
                    print(f"{key:20s}: {value}")
                print()
            elif command == "clear-cache":
                removed = state_manager.cleanup_expired_cache()
                print(f"Cleared {removed} expired cache entries")
            # Knowledge graph commands
            elif command == "kg-stats":
                kg_stats_command(knowledge_graph)
            elif command == "kg-asof":
                if len(sys.argv) < 3:
                    print("Usage: boss /kg-asof '2026-02-04 14:00'")
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
                    print("Usage: boss /kg-show <entity-id>")
                    sys.exit(1)
                entity_id = sys.argv[2]
                kg_show_command(knowledge_graph, entity_id)
            else:
                print(f"Unknown command: /{command}")
                print("\nRun 'boss /help' to see available commands")
                sys.exit(1)
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
