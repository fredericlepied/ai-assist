# ai-assist - AI Assistant for Managers

An intelligent AI assistant powered by Claude and MCP (Model Context Protocol) that helps managers with periodic automated monitoring and interactive querying.

Works with MCP servers like:
- [DCI MCP Server](https://github.com/redhat-community-ai-tools/dci-mcp-server) for DCI and Jira
- [Second Brain](https://github.com/flepied/second-brain-agent) for personal notes
- Any other MCP-compatible server

## Features

- 🤖 **AI-Powered**: Claude Sonnet 4.5 for intelligent analysis
- 🔌 **MCP Integration**: Connect to any MCP server for tools and data
- 📊 **Monitoring**: Automated scheduled checks with smart notifications
- 💬 **Interactive Mode**: Rich TUI with streaming responses and history
- 🧠 **Knowledge Graph**: Temporal database tracking entities and changes
- 📝 **Report Generation**: Create and manage markdown reports
- ⚡ **Hot Reload**: Schedule changes take effect immediately

## Quick Start

### Prerequisites

Choose ONE authentication method:
- **Vertex AI** (Google Cloud): Enterprise/company Claude access
- **Direct API** (Anthropic): Personal use with free tier

### Installation

```bash
git clone https://github.com/fredericlepied/ai-assist
cd ai-assist
pip install -e .
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

📖 **Detailed setup:** See [QUICKSTART.md](QUICKSTART.md) and [VERTEX_AI_SETUP.md](VERTEX_AI_SETUP.md)

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
- 🧠 Conversation memory (up to 10 exchanges)
- 💾 Auto-learning from interactions

**Built-in Commands:**
- `/status` - Show statistics
- `/history` - Recent monitoring history
- `/clear` - Clear conversation memory
- `/kg-save [on|off]` - Toggle knowledge graph auto-save
- `/prompts` - List available MCP prompts
- `/help` - Show help
- `/exit` or `/quit` - Exit

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

### Monitoring Mode

Run periodic monitoring with automated checks:

```bash
ai-assist /monitor
```

- Runs monitors and tasks from `~/.ai-assist/schedules.json`
- Auto-saves findings to knowledge graph
- Hot-reloads when schedules change
- Sends notifications on important updates

**Create monitors via interactive mode:**
```bash
ai-assist
You: Create a monitor to check for failed DCI jobs every 5 minutes
```

📖 **Monitor details:** See [TASKS.md](TASKS.md)

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
ai-assist /kg-late 60            # Late discoveries (>60 min lag)
```

The knowledge graph automatically stores:
- DCI jobs and components
- Jira tickets and status history
- Entity relationships
- Temporal changes (when created vs. when discovered)

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
├── tests/                  # Test suite (265 tests)
├── .env.example           # Example environment variables
└── docs/
    ├── QUICKSTART.md      # Detailed setup guide
    ├── VERTEX_AI_SETUP.md # Vertex AI troubleshooting
    ├── TASKS.md           # Monitor and task details
    ├── COMMANDS.md        # CLI commands reference
    └── CONTRIBUTING.md    # Development guide
```

## Documentation

- **[QUICKSTART.md](QUICKSTART.md)** - Detailed installation and setup
- **[VERTEX_AI_SETUP.md](VERTEX_AI_SETUP.md)** - Vertex AI configuration and troubleshooting
- **[TASKS.md](TASKS.md)** - Creating monitors and tasks
- **[COMMANDS.md](COMMANDS.md)** - CLI commands reference
- **[CONTRIBUTING.md](CONTRIBUTING.md)** - Development setup with pre-commit hooks
- **[AGENTS.md](AGENTS.md)** - Development philosophy (TDD/DRY/Tracer Bullet)

## Requirements

- Python 3.12+
- Anthropic API access (Vertex AI or Direct API)
- MCP servers (optional but recommended)

## License

See LICENSE file for details.
