# BOSS Command Reference

All BOSS commands start with the `/` prefix, consistent with TUI interfaces like Claude Code.

## Command Line Usage

```bash
# Interactive mode (default)
boss
boss /interactive

# Help
boss /help

# Monitoring
boss /monitor

# One-off queries
boss /query "What are the latest DCI failures?"

# State management
boss /status
boss /clear-cache

# Knowledge graph queries
boss /kg-stats
boss /kg-asof '2026-02-04 14:00'
boss /kg-late 30
boss /kg-changes 1
boss /kg-show <entity-id>
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
Create `~/.boss/tasks.yaml` for custom periodic tasks that run alongside built-in monitors.

**Example:**
```bash
boss /monitor
```

### `/query '<text>'`
Execute a single query and exit.

**Example:**
```bash
boss /query "Find all OCP 4.19 jobs that failed today"
boss /query "What are the critical Jira tickets in CILAB?"
```

### `/interactive`
Start an interactive chat session. This is the default mode if no command is specified.

**Example:**
```bash
boss /interactive
# or simply
boss
```

### `/status`
Show state statistics including number of monitors, cached queries, and history files.

**Example:**
```bash
boss /status
```

### `/clear-cache`
Clear expired cache entries from the state directory.

**Example:**
```bash
boss /clear-cache
```

## Knowledge Graph Commands

These commands query the temporal knowledge graph that tracks entities and their changes over time.

### `/kg-stats`
Show knowledge graph statistics including total entities, relationships, and breakdowns by type.

**Example:**
```bash
boss /kg-stats
```

### `/kg-asof '<time>'`
Show what BOSS knew at a specific point in time.

**Time format:** ISO format like `YYYY-MM-DD HH:MM:SS`

**Example:**
```bash
boss /kg-asof '2026-02-04 14:00'
boss /kg-asof '2026-02-01 09:00:00'
```

### `/kg-late [minutes]`
Show entities that were discovered late (significant lag between when they occurred and when BOSS found out).

**Default:** 30 minutes

**Example:**
```bash
boss /kg-late         # Default 30 minutes
boss /kg-late 60      # Show items discovered >60 minutes late
```

### `/kg-changes [hours]`
Show what changed in the knowledge graph recently.

**Default:** 1 hour

**Example:**
```bash
boss /kg-changes      # Last 1 hour
boss /kg-changes 24   # Last 24 hours
```

### `/kg-show <entity-id>`
Show detailed information about a specific entity with full context.

**Supported entities:**
- `dci_job` - Shows job details, components, related tickets, discovery lag
- `jira_ticket` - Shows ticket details, related jobs
- Any other entity type - Shows basic entity information

**Example:**
```bash
boss /kg-show b43938f7-fa25-4ae5-b5a9-b606eb89477e  # DCI job
boss /kg-show CILAB-1234                             # Jira ticket
```

## Error Handling

If you forget the `/` prefix, BOSS will remind you:

```bash
$ boss status
Error: Commands must start with /
Did you mean: /status?

Run 'boss /help' to see available commands
```

## Environment Setup

See [README.md](README.md) for complete setup instructions.

Quick start:
1. Copy `.env.example` to `.env`
2. Set `ANTHROPIC_VERTEX_PROJECT_ID` or `ANTHROPIC_API_KEY`
3. Configure DCI credentials (if using PyPI version)
4. Run `boss /help` to verify setup
