# ai-assist - AI Assistant for Managers

An intelligent AI assistant powered by Claude, Skills and MCP (Model Context Protocol) that helps managers with periodic automated monitoring and interactive querying.

Works with MCP servers like:
- [DCI MCP Server](https://github.com/redhat-community-ai-tools/dci-mcp-server) for DCI and Jira
- [Second Brain](https://github.com/flepied/second-brain-agent) for personal notes
- Any other MCP-compatible server

Works with skills like:

- [pdf](https://github.com/anthropics/skills/blob/main/skills/pdf/SKILL.md)
- [markdown-converter](https://github.com/intellectronica/agent-skills/blob/main/skills/markdown-converter/SKILL.md)
- Any other [skills](https://skills.sh/)

## Features

- 🤖 **AI-Powered**: Claude Sonnet 4.5 for intelligent analysis
- 🔌 **MCP Integration**: Connect to any MCP server for tools and data
- 📊 **Monitoring**: Automated scheduled checks with smart notifications
- ⏰ **Scheduled Actions**: One-shot future actions with notifications
- 💬 **Interactive Mode**: Rich TUI with streaming responses and history
- 🧠 **Knowledge Graph**: Temporal database tracking entities and changes
- 📝 **Report Generation**: Create and manage markdown reports
- ⚡ **Hot Reload**: Schedule changes take effect immediately
- 🚀 **Agent Skills**: Install specialized skills following [agentskills.io](https://agentskills.io/) specification

## Quick Start

### Prerequisites

Choose ONE authentication method:
- **Vertex AI** (Google Cloud): Enterprise/company Claude access
- **Direct API** (Anthropic): Personal use with free tier

### Installation

First, install [uv](https://docs.astral.sh/uv/getting-started/installation/) if you don't have it:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then install ai-assist:

```bash
git clone https://github.com/fredericlepied/ai-assist
cd ai-assist
uv sync
```

### Configuration

```bash
cp .env.example .env
# Edit .env with your credentials
```

**Vertex AI** (Google Cloud):
```bash
export ANTHROPIC_VERTEX_PROJECT_ID='your-gcp-project-id'
gcloud auth application-default login
```

**Direct API** (Anthropic - free tier available):
```bash
export ANTHROPIC_API_KEY='sk-ant-...'  # Get from console.anthropic.com
```

📖 **Vertex AI setup:** See [VERTEX_AI_SETUP.md](VERTEX_AI_SETUP.md)

**Personalization** (Optional):

Customize the assistant's personality and communication style:

```bash
ai-assist /identity-init  # Create template
ai-assist /identity-show  # View current settings
```

Edit `~/.ai-assist/identity.yaml` to configure:
- Your name, role, and organization
- Assistant nickname and personality
- Communication preferences (formality, verbosity, emoji usage)
- Work context for better assistance

📖 **Full identity guide:** See [docs/IDENTITY.md](docs/IDENTITY.md)

## Usage

### Interactive Mode

Chat with the assistant using a rich terminal interface:

```bash
ai-assist /interactive
# or simply
ai-assist
```

**Features:**
- 🎨 Rich markdown formatting with syntax highlighting
- 📝 Multi-line editing (Esc-Enter for newlines)
- 📚 Command history with search (Ctrl-R)
- ⌨️ Tab completion for commands
- ⚡ Streaming responses in real-time
- 🛑 Cancel streaming with Escape key
- 🧠 Conversation memory with persistent storage in knowledge graph
- 💾 Nightly self-reflection extracts knowledge from conversations

**Built-in Commands:**
- `/status` - Show statistics
- `/history` - Recent monitoring history
- `/clear` - Clear conversation memory
- `/clear-cache` - Clear response cache
- `/kg-save [on|off]` - Toggle knowledge graph auto-save
- `/kg-viz` - Visualize knowledge graph in browser
- `/prompts` - List available MCP prompts with arguments
- `/prompt-info <server/prompt>` - Show detailed prompt info
- `/skill/install <source>@<branch>` - Install an Agent Skill
- `/skill/uninstall <name>` - Uninstall an Agent Skill
- `/skill/list` - List installed Agent Skills
- `/skill/search <query>` - Search ClawHub and skills.sh registries
- `/help` - Show help
- `/exit` or `/quit` - Exit

**Security:**

When a command is not on the allowlist, the assistant prompts for confirmation:

```
Allow? [y/N/a(lways)]
```

- **y** - Allow once
- **N** - Deny (default)
- **a(lways)** - Allow and permanently add to the allowlist

**Example queries:**
```
What are the latest failing DCI jobs?
Show me critical Jira tickets in the CILAB project
Find OpenShift 4.19 jobs that failed in the last week
```

### MCP Prompts

Execute MCP server prompts directly with slash commands:

```bash
# In interactive mode
/dci/rca         # Run RCA prompt from dci server
/prompts         # List all available prompts
```

MCP prompts can request arguments interactively and automatically execute with streaming results.

### Agent Skills

Install specialized skills following the [agentskills.io](https://agentskills.io) specification:

```bash
# In interactive mode
/skill/install anthropics/skills/skills/pdf@main     # Install PDF skill from GitHub
/skill/install /path/to/my-skill@main                # Install local skill
/skill/list                                          # List installed skills
/skill/uninstall pdf                                 # Uninstall skill
/skill/search pdf                                    # Search ClawHub and skills.sh
```

**What are Agent Skills?**
- Specialized instructions for Claude following agentskills.io standard
- Automatically loaded into system prompt (no activation needed)
- Can include scripts, references, and assets

📖 **Creating personal skills:** See [docs/PERSONAL_SKILLS.md](docs/PERSONAL_SKILLS.md)
- Persistent across sessions

**Example skills:**
- PDF processing (extract text, fill forms, merge)
- DOCX manipulation
- Custom workflow automation
- Domain-specific expertise

**Creating your own skills:**
```bash
mkdir -p my-skill
cat > my-skill/SKILL.md << 'EOF'
---
name: my-skill
description: My custom skill
---

# My Skill Instructions

When the user asks for X, do Y...
EOF

ai-assist
You> /skill/install /path/to/my-skill@main
```

📖 **Skill specification:** See [agentskills.io/specification](https://agentskills.io/specification)

#### Script Execution (Advanced)

Skills can include executable scripts in a `scripts/` directory. **Script execution is disabled by default for security.**

**Enable script execution:**
```bash
export AI_ASSIST_ALLOW_SCRIPT_EXECUTION=true
ai-assist
```

**Security requirements:**
- Skills must declare permission in SKILL.md:
  ```yaml
  allowed-tools: "internal__execute_skill_script"
  ```
- Scripts run in a sandboxed environment:
  - No access to API keys or secrets (environment filtered)
  - 30-second timeout limit
  - Output limited to 20KB
  - Directory traversal blocked
  - No shell injection possible

**Example skill with script:**
```markdown
---
name: pdf-tools
description: PDF processing utilities
compatibility: Requires python3, python3-pypdf
allowed-tools: "internal__execute_skill_script"
---

# PDF Tools

Run `scripts/check_fillable_fields.py` to detect form fields.
```

📋 **Security details:** See [SECURITY.md](SECURITY.md) for the complete security model

### Monitoring Mode

Run periodic monitoring with automated checks:

```bash
ai-assist /monitor
```

- Runs monitors and tasks from `~/.ai-assist/schedules.json`
- Auto-saves findings to knowledge graph
- Hot-reloads when schedules or actions change (FileWatchdog)
- Sends notifications on important updates
- Handles laptop suspension gracefully (catches up missed runs)
- **Executes scheduled one-shot actions** (event-driven, no polling)

**Create monitors via interactive mode:**
```bash
ai-assist
You: Create a monitor to check for failed DCI jobs every 5 minutes
```

**Enable notifications for periodic tasks:**

Add `notify` and `notification_channels` to any task or monitor in `schedules.json`:

```json
{
  "monitors": [
    {
      "name": "critical-failures",
      "prompt": "Check for critical DCI failures",
      "interval": "1h",
      "notify": true,
      "notification_channels": ["desktop", "file"]
    }
  ],
  "tasks": [
    {
      "name": "daily-summary",
      "prompt": "Summarize yesterday's DCI jobs",
      "interval": "9:00 on weekdays",
      "notify": true,
      "notification_channels": ["console"]
    }
  ]
}
```

When `notify` is true, you'll receive notifications on task completion via:
- **desktop**: System notifications (notify-send on Linux)
- **file**: Append to `~/.ai-assist/notifications.log`
- **console**: Display in /monitor output
- Interactive mode automatically shows notifications from any channel in the TUI

### Scheduled Actions

Schedule one-time future actions that execute automatically with notifications:

```bash
ai-assist /interactive
You: Remind me in 2 hours to check the DCI job status for job-456
```

The agent will:
- Schedule the action for execution in 2 hours
- Execute it automatically when due (via `/monitor` process)
- Send desktop notification + file log when complete

**Supported Time Formats:**
- `in X hours/minutes/days` - Relative time
- `tomorrow at 9am` - Next day specific time
- `next monday 10:00` - Specific day and time

**Notification Channels:**
- **desktop**: System notifications (notify-send on Linux)
- **file**: Append to `~/.ai-assist/notifications.log`
- **console**: Display in /monitor output
- **TUI**: Automatically displayed in interactive mode (watches notification log)

**Agent Decision Making:**
The agent intelligently decides how to execute scheduled actions:
- "Remind me to watch TV" → Simple notification (no agent query)
- "Tell me what's in my Gmail inbox" → Query via agent, notify with results
- "Check failed jobs and save report" → Query via agent, save to report

**View scheduled actions:**
```bash
cat ~/.ai-assist/scheduled-actions.json
```

**View notification history:**
```bash
tail -f ~/.ai-assist/notifications.log
```

**Managing Scheduled Actions:**

Completed and failed actions older than 7 days are automatically archived to `~/.ai-assist/scheduled-actions-archive.jsonl`.

```bash
# Manual cleanup
ai-assist /cleanup-actions

# View archive
cat ~/.ai-assist/scheduled-actions-archive.jsonl | jq
```

**File Structure:**
- `scheduled-actions.json` - Active and recent (≤7 days) actions
- `scheduled-actions-archive.jsonl` - Historical actions (>7 days old)

**⚠️ Important:** The `/monitor` process must be running for scheduled actions to execute:
```bash
ai-assist /monitor  # Keep running in background
```

#### MCP Prompts in Tasks

Execute MCP prompts directly from periodic tasks for consistent, automated workflows:

**Natural Language (Traditional):**
```json
{
  "tasks": [
    {
      "name": "System Check",
      "prompt": "Find failures in the last 24 hours",
      "interval": "1h"
    }
  ]
}
```

**MCP Prompts (New):**
```json
{
  "tasks": [
    {
      "name": "Daily RCA Report",
      "prompt": "mcp://dci/rca",
      "prompt_arguments": {
        "days": "1",
        "status": "failure"
      },
      "interval": "8:00 on weekdays"
    }
  ]
}
```

**Format:** `mcp://server_name/prompt_name`

**Benefits:**
- Direct execution - no interpretation needed
- Consistent results - same prompt, same output
- Argument support - pass structured data
- Less token usage - no translation layer

**Creating via Interactive Mode:**
```bash
ai-assist /interactive

# Natural language task
You: Create a task to check for failures every hour

# MCP prompt task (be specific about format)
You: Create a task named "Weekly Report" that runs mcp://tpci/weekly_report
     with argument "for" set to "Semih" at 10:45 on monday
```

**Discovery:**
```bash
ai-assist /interactive

# List all prompts with their arguments
/prompts

# See detailed info about a specific prompt (arguments, descriptions, examples)
/prompt-info tpci/weekly_report
```

See `.ai-assist/schedules.json.example` for complete examples.

### One-off Queries

```bash
ai-assist /query "What are the top 5 failing DCI jobs today?"
```

### Knowledge Graph

Query temporal data and track changes:

```bash
ai-assist /kg-stats              # View statistics
ai-assist /kg-changes 24         # Changes in last 24 hours
ai-assist /kg-asof '2026-02-04'  # Historical state
ai-assist /kg-show <id>          # Entity details
ai-assist /kg-viz                # Visualize graph in browser
ai-assist /kg-late 60            # Late discoveries (>60 min lag)
```

The knowledge graph automatically stores:
- DCI jobs and components
- Jira tickets and status history
- Entity relationships
- Temporal changes (when created vs. when discovered)
- Conversation exchanges (user/assistant pairs)

**Nightly Synthesis**: A built-in scheduled task (`nightly-synthesis`) runs at 22:00 on weekdays to review the day's conversations and extract structured knowledge (preferences, lessons, context, rationale). The schedule is configurable in `schedules.json`.

## Available Tools

### Built-in Tools

**Report Management:**
- `write_report` - Create/overwrite markdown report
- `append_to_report` - Add content to report
- `read_report` - Read report content
- `list_reports` - List all reports
- `delete_report` - Delete report

Reports are stored in `~/ai-reports/` (configurable via `AI_ASSIST_REPORTS_DIR`).

**Schedule Management:**
- `create_monitor` - Create monitor with knowledge graph support
- `create_task` - Create periodic task
- `list_schedules` - List all schedules
- `update_schedule` - Update schedule properties
- `delete_schedule` - Remove schedule
- `enable_schedule` - Enable/disable schedule

Schedules stored in `~/.ai-assist/schedules.json` with hot-reload support.

**Filesystem Tools:**
- `read_file` - Read files with line-range support
- `search_in_file` - Regex search in files
- `create_directory` - Create directories
- `list_directory` - List directory contents
- `execute_command` - Execute bash commands
- `get_today_date` - Get today's date (YYYY-MM-DD)
- `get_current_time` - Get current date and time (ISO format)

### MCP Server Tools

All tools from configured MCP servers are automatically available. Configure servers in `~/.ai-assist/mcp_servers.yaml`:

```yaml
servers:
  dci:
    command: "uvx"
    args: ["--from", "dci-mcp-server", "dci-mcp-server"]
    env:
      DCI_CLIENT_ID: "${DCI_CLIENT_ID}"
      DCI_API_SECRET: "${DCI_API_SECRET}"
```

See `.ai-assist/mcp_servers.yaml.example` for templates.

## State Management

Persistent state stored in `~/.ai-assist/`:

```
~/.ai-assist/
├── state/                   # Monitor states and cache
├── knowledge_graph.db       # Temporal database (SQLite)
├── schedules.json          # Monitor/task definitions
├── mcp_servers.yaml        # MCP server configuration
└── interactive_history.txt # Command history
```

## Project Structure

```
ai-assist/
├── ai_assist/              # Main package
│   ├── main.py            # CLI entry point
│   ├── agent.py           # MCP agent with tool execution
│   ├── monitors.py        # Monitoring tasks
│   ├── state.py           # State management and caching
│   ├── knowledge_graph.py # Temporal knowledge graph
│   └── filesystem_tools.py # Filesystem operations
├── tests/                  # Test suite (532 tests)
├── .env.example           # Example environment variables
├── VERTEX_AI_SETUP.md     # Vertex AI troubleshooting
├── SECURITY.md            # Security model
├── CONTRIBUTING.md        # Development setup
└── AGENTS.md              # Development philosophy
```

## Documentation

- **[docs/PERSONAL_SKILLS.md](docs/PERSONAL_SKILLS.md)** - Creating and managing personal Agent Skills
- **[docs/IDENTITY.md](docs/IDENTITY.md)** - Complete guide to identity.yaml configuration
- **[docs/MULTI_INSTANCE.md](docs/MULTI_INSTANCE.md)** - Running multiple ai-assist instances
- **[VERTEX_AI_SETUP.md](VERTEX_AI_SETUP.md)** - Vertex AI configuration and troubleshooting
- **[SECURITY.md](SECURITY.md)** - Security model for skill script execution
- **[CONTRIBUTING.md](CONTRIBUTING.md)** - Development setup with pre-commit hooks
- **[AGENTS.md](AGENTS.md)** - Development philosophy (TDD/DRY/Tracer Bullet)

## Development

### Auto-Reload

Configuration files are automatically watched and reloaded in both monitor and interactive modes:

- **`mcp_servers.yaml`** - Reconnects to changed MCP servers
- **`identity.yaml`** - Updates identity and system prompt
- **`installed-skills.json`** - Reloads Agent Skills
- **`schedules.json`** - Restarts monitors and tasks (monitor mode only)

Changes take effect immediately without manual restart.

### Code Auto-Reload (Dev Mode)

Use the `--dev` flag to enable automatic process restart when Python code changes:

```bash
# Monitor mode with code watching
ai-assist --dev /monitor

# Interactive mode with code watching
ai-assist --dev /interactive
```

This is useful during development to see code changes immediately.

## Requirements

- Python 3.12+
- Anthropic API access (Vertex AI or Direct API)
- MCP servers (optional but recommended)

## License

See LICENSE file for details.
