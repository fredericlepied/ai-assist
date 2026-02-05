# ai-assist Command Reference

All ai-assist commands start with the `/` prefix, consistent with TUI interfaces like Claude Code.

## Command Line Usage

```bash
# Interactive mode (default)
ai-assist
ai-assist /interactive

# Help
ai-assist /help

# Monitoring
ai-assist /monitor

# One-off queries
ai-assist /query "What are the latest DCI failures?"

# State management
ai-assist /status
ai-assist /clear-cache

# Knowledge graph queries
ai-assist /kg-stats
ai-assist /kg-asof '2026-02-04 14:00'
ai-assist /kg-late 30
ai-assist /kg-changes 1
ai-assist /kg-show <entity-id>
```

## Interactive Mode Commands

When in interactive mode, use these special commands:

```
/status       - Show state statistics
/history      - Show recent monitoring history
/clear-cache  - Clear expired cache entries
/exit         - Exit interactive mode
/quit         - Exit interactive mode
```

## Command Details

### `/monitor`
Start continuous monitoring of DCI and Jira based on configuration in `.env`.

**Configuration:**
- `JIRA_CHECK_INTERVAL` - Seconds between Jira checks (default: 300)
- `DCI_CHECK_INTERVAL` - Seconds between DCI checks (default: 300)
- `JIRA_PROJECTS` - Comma-separated list of projects to monitor
- `DCI_QUERIES` - Pipe-separated list of DCI query strings

**User Tasks:**
Create `~/.ai-assist/tasks.yaml` for custom periodic tasks that run alongside built-in monitors.

**Example:**
```bash
ai-assist /monitor
```

### `/query '<text>'`
Execute a single query and exit.

**Example:**
```bash
ai-assist /query "Find all OCP 4.19 jobs that failed today"
ai-assist /query "What are the critical Jira tickets in CILAB?"
```

### `/interactive`
Start an interactive chat session. This is the default mode if no command is specified.

**Example:**
```bash
ai-assist /interactive
# or simply
ai-assist
```

### `/status`
Show state statistics including number of monitors, cached queries, and history files.

**Example:**
```bash
ai-assist /status
```

### `/clear-cache`
Clear expired cache entries from the state directory.

**Example:**
```bash
ai-assist /clear-cache
```

## Knowledge Graph Commands

These commands query the temporal knowledge graph that tracks entities and their changes over time.

### `/kg-stats`
Show knowledge graph statistics including total entities, relationships, and breakdowns by type.

**Example:**
```bash
ai-assist /kg-stats
```

### `/kg-asof '<time>'`
Show what ai-assist knew at a specific point in time.

**Time format:** ISO format like `YYYY-MM-DD HH:MM:SS`

**Example:**
```bash
ai-assist /kg-asof '2026-02-04 14:00'
ai-assist /kg-asof '2026-02-01 09:00:00'
```

### `/kg-late [minutes]`
Show entities that were discovered late (significant lag between when they occurred and when ai-assist found out).

**Default:** 30 minutes

**Example:**
```bash
ai-assist /kg-late         # Default 30 minutes
ai-assist /kg-late 60      # Show items discovered >60 minutes late
```

### `/kg-changes [hours]`
Show what changed in the knowledge graph recently.

**Default:** 1 hour

**Example:**
```bash
ai-assist /kg-changes      # Last 1 hour
ai-assist /kg-changes 24   # Last 24 hours
```

### `/kg-show <entity-id>`
Show detailed information about a specific entity with full context.

**Supported entities:**
- `dci_job` - Shows job details, components, related tickets, discovery lag
- `jira_ticket` - Shows ticket details, related jobs
- Any other entity type - Shows basic entity information

**Example:**
```bash
ai-assist /kg-show b43938f7-fa25-4ae5-b5a9-b606eb89477e  # DCI job
ai-assist /kg-show CILAB-1234                             # Jira ticket
```

## Error Handling

If you forget the `/` prefix, ai-assist will remind you:

```bash
$ ai-assist status
Error: Commands must start with /
Did you mean: /status?

Run 'ai-assist /help' to see available commands
```

## Environment Setup

See [README.md](README.md) for complete setup instructions.

Quick start:
1. Copy `.env.example` to `.env`
2. Set `ANTHROPIC_VERTEX_PROJECT_ID` or `ANTHROPIC_API_KEY`
3. Configure DCI credentials (if using PyPI version)
4. Run `ai-assist /help` to verify setup
