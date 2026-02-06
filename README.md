# ai-assist - AI Assistant for Managers

An intelligent AI assistant powered by Claude and MCP (Model Context Protocol) that helps managers with periodic automated checks and interactive querying.

I use it personally with the following MCP servers:

- ![DCI MCP Server](https://github.com/redhat-community-ai-tools/dci-mcp-server) for DCI and Jira
- [Second Brain](https://github.com/flepied/second-brain-agent) to access my personal notes

## Features

- 🤖 **AI-Powered Assistant**: Uses Claude Sonnet 4.5 for intelligent analysis and responses
- 🔌 **MCP Integration**: Connects to MCP servers for DCI and Jira tools
- 📊 **Periodic Monitoring**: Automated scheduled checks for Jira and DCI updates
- 📝 **Schedule Management**: Create and manage monitors/tasks via AI interaction
- 🔄 **Hot Reload**: Schedule changes take effect immediately without restarting
- ⚡ **Conditional Actions**: Trigger notifications and actions based on results
- 💬 **Interactive Mode**: Chat with the assistant to query information
- 🎯 **Targeted Queries**: Run one-off queries for specific information
- 🔔 **Notifications**: Get alerts about important updates (configurable)

## Quick Start

### Prerequisites

**You will need (choose ONE Anthropic method)**:

**Option A: Vertex AI** (Google Cloud - Recommended for enterprise)
1. ✅ **Google Cloud Project with Vertex AI** - Your company likely has this

**Option B: Direct API** (Personal/Free tier)
1. ✅ **Anthropic API Key** - Get from https://console.anthropic.com/ (free tier available)

### Installation

1. Clone the repository:
```bash
git clone https://github.com/fredericlepied/ai-assist
cd ai-assist
```

2. Install dependencies using uv (recommended) or pip:
```bash
# Using uv
uv sync

# Or using pip
pip install -e .
```

3. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your API keys and configuration
```

**Minimum .env setup** (choose ONE authentication method):

**Option A - Vertex AI** (if using company Claude via Google Cloud):
```bash
ANTHROPIC_VERTEX_PROJECT_ID=your-gcp-project-id  # Your GCP project ID
# ANTHROPIC_VERTEX_REGION=us-east5               # Optional - usually not needed
```

**Option B - Direct API** (personal/free tier):
```bash
ANTHROPIC_API_KEY=your_anthropic_key_here  # Get from console.anthropic.com
```

## Configuration

ai-assist uses YAML files for configuration, making it easy to customize without editing code.

### Environment Variables (.env)

Create a `.env` file with authentication credentials:

```bash
# Required: Anthropic API access (choose ONE method)
# Method 1: Vertex AI (Google Cloud - enterprise)
ANTHROPIC_VERTEX_PROJECT_ID=your-gcp-project-id
# ANTHROPIC_VERTEX_REGION=us-east5  # Optional

# Method 2: Direct API Key (personal/free tier)
ANTHROPIC_API_KEY=your_api_key_here
```

### MCP Servers Configuration (~/.ai-assist/mcp_servers.yaml)

Configure MCP servers in `~/.ai-assist/mcp_servers.yaml`:

```yaml
servers:
  # DCI MCP Server
  dci:
    command: "uvx"
    args: ["--from", "dci-mcp-server", "dci-mcp-server"]
    env:
      DCI_CLIENT_ID: "${DCI_CLIENT_ID}"
      DCI_API_SECRET: "${DCI_API_SECRET}"
      DCI_CS_URL: "${DCI_CS_URL}"
      JIRA_API_TOKEN: "${JIRA_API_TOKEN}"
      JIRA_URL: "${JIRA_URL}"
      MCP_SHOW_BANNER: "false"

  # Add custom servers
  # my-server:
  #   command: "node"
  #   args: ["./server.js"]
  #   env:
  #     API_KEY: "${MY_API_KEY}"
```

Copy from `.ai-assist/mcp_servers.yaml.example` to get started.

### Creating Schedules

Use schedule management tools in interactive mode to create monitors and tasks. See "Schedule Management Tools" section below for details.

### Getting API Credentials

**Anthropic Authentication (REQUIRED - Choose ONE method):**

ai-assist requires Anthropic API access to power the AI assistant. Choose the method that fits your situation:

**Method 1: Vertex AI (Google Cloud)** - Recommended for enterprise/company use

If your company uses Claude via Google Cloud (like Claude Code), use this method:

1. Get your GCP project ID from your admin or check your Claude Code settings
2. Authenticate with Google Cloud:
   ```bash
   gcloud auth application-default login
   ```
3. Set environment variables:
   ```bash
   export ANTHROPIC_VERTEX_PROJECT_ID='your-gcp-project-id'
   # ANTHROPIC_VERTEX_REGION='us-east5'  # Optional - usually not needed, SDK will choose best region
   ```
4. Add these to your `.env` file

**Method 2: Direct API Key** - For personal use or free tier

1. Visit https://console.anthropic.com/
2. Sign up or log in with your account
3. Go to "API Keys" section
4. Create a new API key
5. Copy the key and set it as `ANTHROPIC_API_KEY` in `.env`
6. New accounts get $5 in free credits

### Troubleshooting Vertex AI

**Model Not Found (404 Error)**

If you get a 404 error like:
```
Publisher Model `projects/.../models/claude-sonnet-4-5-20250929` was not found
```

The issue is likely the model name format. Vertex AI uses **@ symbol** for model versions:

✅ Correct: `claude-sonnet-4-5@20250929`
❌ Wrong: `claude-sonnet-4-5-20250929`

Update your `.env` file:
```bash
AI_ASSIST_MODEL=claude-sonnet-4-5@20250929
```

**Available Models**

To test which Claude models are accessible in your project:
```bash
uv run python discover_vertex_models.py
```

This will test all known Claude models (Opus 4.6, Sonnet 4.5, Haiku 4.5, etc.) and show which ones you have access to.

**Vertex AI API Not Enabled**

If you get "API not enabled" errors:
```bash
gcloud services enable aiplatform.googleapis.com --project=your-project-id
```

Contact your GCP administrator if you don't have permissions.

## Usage

### Interactive Mode

Start an interactive chat session with the assistant:

```bash
ai-assist /interactive
# or simply
ai-assist
```

**Modern TUI Features**:
- 🎨 **Rich Formatting**: Beautiful markdown rendering with syntax highlighting
- 📝 **Multi-line Editing**: Press Enter to submit, Esc-Enter or Ctrl-J for multi-line input
- 📚 **Command History**: Navigate with Up/Down arrows, persistent across sessions
- ⌨️ **Tab Completion**: Auto-complete slash commands (try typing `/st` and press Tab)
- 🔍 **History Search**: Ctrl-R for reverse search through your conversation history
- 🧠 **Conversation Memory**: ai-assist remembers your conversation! (NEW!)
  - Natural follow-up questions work perfectly
  - "What are the latest DCI failures?" → "Why did they fail?" ← ai-assist knows what "they" refers to!
  - Remembers up to 10 recent exchanges for context
  - Use `/clear` to start a fresh conversation
- 🔍 **Knowledge Graph Context**: Automatic prompt enrichment with historical data! (NEW!)
  - Auto-detects Jira ticket references (CILAB-123) and adds ticket context
  - Recognizes time references ("yesterday", "last week") and includes recent failures
  - Shows what context was added: "🔍 Knowledge graph context: Jira ticket CILAB-123, 5 recent failures"
  - Zero configuration - works automatically with data from monitors
- 💾 **Auto-Learning from Interactions**: ai-assist learns from every query! (NEW!)
  - Tool results automatically saved to knowledge graph
  - Future queries can use cached data (faster, fewer API calls)
  - See feedback: "💾 Saved 5 entities to knowledge graph"
  - Toggle with `/kg-save on` or `/kg-save off`
  - Enabled by default for seamless experience
- 💬 **Real-time Feedback**: Live spinner showing what ai-assist is doing:
  - 🤔 Analyzing your question
  - 💭 Thinking (with turn counter)
  - 🔧 Using tools (shows which tool is executing)
  - ✨ Complete!
- ⚡ **Streaming Responses**: Text appears word-by-word as Claude generates it
  - No more waiting for the full response
  - See progress in real-time
  - Tool calls shown inline during generation

**Built-in Commands**:
- `/status` - Show state statistics
- `/history` - Show recent monitoring history
- `/clear-cache` - Clear expired cache
- `/clear` - Clear conversation memory (start fresh conversation)
- `/kg-save [on|off]` - Toggle knowledge graph auto-save (NEW!)
- `/help` - Show help message
- `/exit` or `/quit` - Exit interactive mode

**Tips**:
- Press **Enter** to submit your input (normal behavior)
- Press **Esc-Enter** or **Ctrl-J** to add newlines for multi-line input
- Press **Tab** to auto-complete slash commands
- Use **Up/Down** arrows to navigate command history
- Press **Ctrl-R** to search through your history
- History is saved at `~/.ai-assist/interactive_history.txt`
- Responses are automatically formatted as Markdown

**Fallback Mode**:
If TUI libraries are not available, ai-assist will automatically fall back to basic mode. You can also force basic mode with:
```bash
export AI_ASSIST_INTERACTIVE_MODE=basic
ai-assist /interactive
```

Example queries:
- "What are the latest failing DCI jobs?"
- "Show me critical Jira tickets in the CILAB project"
- "Find OpenShift 4.19 jobs that failed in the last week"

### Monitoring Mode

Run periodic monitoring tasks:

```bash
ai-assist /monitor
```

This will:
- Run all monitors and tasks from `~/.ai-assist/schedules.json`
- **Store all findings in the temporal knowledge graph** (automatic)
- Report findings to console or configured notification channel
- Hot-reload when schedules.json changes

**Knowledge Graph Integration:**
All DCI jobs and Jira tickets are automatically stored in the temporal knowledge graph, allowing you to:
- Query historical data (`ai-assist /kg-asof '2026-02-04 14:00'`)
- Track changes over time (`ai-assist /kg-changes 24`)
- Find late discoveries (`ai-assist /kg-late 60`)
- View entity details (`ai-assist /kg-show <id>`)

See [KNOWLEDGE_GRAPH_INTEGRATION.md](KNOWLEDGE_GRAPH_INTEGRATION.md) for details.


### One-off Query

Run a single query and exit:

```bash
ai-assist /query "What are the top 5 failing DCI jobs today?"
```

### State Management

View and manage persistent state:

```bash
# View state statistics
ai-assist /status

# Clear expired cache
ai-assist /clear-cache
```

In interactive mode, you can use special commands:
- `/status` - Show state statistics
- `/history` - Show recent monitoring history
- `/clear-cache` - Clear expired cache entries
- `/exit` or `/quit` - Exit interactive mode

## Available Tools

The assistant has access to these tools:

### Report Management Tools (built-in internal tools)
- `write_report` - Create or overwrite a markdown report file
- `append_to_report` - Add content to existing report (creates if doesn't exist)
- `read_report` - Read a report's current content
- `list_reports` - List all available reports with metadata
- `delete_report` - Delete a report file

**Report Storage:**
Reports are stored as markdown files in `~/ai-assist/reports/` by default (configurable via `AI_ASSIST_REPORTS_DIR` environment variable).

### Schedule Management Tools (built-in internal tools)

Manage monitors and tasks dynamically via AI interaction:

- `create_monitor` - Create new monitor with knowledge graph support
- `create_task` - Create new periodic task
- `list_schedules` - List all monitors and tasks
- `update_schedule` - Update existing schedule properties
- `delete_schedule` - Remove a schedule
- `enable_schedule` - Enable/disable a schedule
- `get_schedule_status` - View schedule details

**Schedule Storage:**
Schedules are stored in `~/.ai-assist/schedules.json` and hot-reload automatically when `/monitor` is running.

**Example Usage:**
```bash
# Interactive mode
ai-assist /interactive
You: Create a monitor to check for failed DCI jobs every 5 minutes
ai-assist: *creates monitor* → Saved to schedules.json

You: List my schedules
ai-assist: *shows all monitors and tasks*

# Start monitoring
ai-assist /monitor
# Your new schedule runs automatically
```

**Example Monitoring Prompts:**

Good prompts are specific and actionable. The AI has access to all MCP tools, so you can:
- Query specific data (DCI jobs, Jira tickets)
- Analyze patterns and trends
- Generate and save reports
- Combine multiple data sources

```
DCI Failure Monitor (every 5 minutes):
"Check for DCI jobs with status 'failure' or 'error' created in the last 5 minutes.
Summarize the job IDs, failure reasons, and affected components."

Jira Blocker Tickets (every 10 minutes):
"Find JIRA tickets in projects CILAB, CNF with priority 'Blocker' and status 'Open'.
List ticket keys, summaries, and how long they've been open."

Daily Summary Task (9am weekdays):
"Generate a daily summary including:
1. DCI job statistics from yesterday (total, failed, success rate)
2. New critical Jira tickets created yesterday
3. Any recurring failure patterns in the last 24 hours
Save the report as 'daily-{date}' using the write_report tool"

Weekly Trends (9am Monday):
"Analyze DCI failures from the past 7 days.
Identify top 3 most common failure types and affected components.
Create a report with trends and recommendations.
Save to 'weekly-analysis' report."

Custom Integration:
"Check DCI jobs tagged 'nightly' that failed in the last 12 hours.
For each failure, check if there's a related JIRA ticket.
If no ticket exists, list the job ID and suggest creating one."
```

**Tips for good prompts:**
- Be specific about time ranges ("last 5 minutes", "yesterday", "last 7 days")
- Specify what data to include (job IDs, ticket keys, summaries)
- For tasks, mention if you want reports saved
- You can reference MCP tools by name if needed

**Example Report Usage:**
```bash
# Interactive mode
ai-assist /interactive
You: Generate a DCI failures summary and save to 'dci-summary' report
ai-assist: *analyzes* → *calls write_report* → Report saved!

# Tasks
tasks:
  - name: "Weekly Report"
    interval: "9:00 on monday"
    prompt: |
      Generate weekly DCI summary with failure trends.
      Save to report named 'weekly-summary'.
```

### Example Queries

```bash
# Find recent OpenShift failures
ai-assist /query "Find all OCP 4.19 jobs that failed in the last 3 days"

# Check Jira status
ai-assist /query "What are the critical bugs in CILAB project?"

# Analyze patterns
ai-assist /query "What are the common failure patterns in daily DCI jobs?"

# Generate reports
ai-assist /query "Create a summary report of this week's DCI failures and save it"
```

## Project Structure

```
ai_assist/
├── ai_assist/
│   ├── __init__.py
│   ├── main.py          # Entry point and CLI
│   ├── config.py        # Configuration management
│   ├── agent.py         # MCP agent implementation
│   ├── monitors.py      # Monitoring tasks
│   └── state.py         # State management and caching
├── pyproject.toml       # Project dependencies
├── .env.example         # Example environment variables
├── README.md           # This file
└── AGENTS.md           # Development guide (TDD/DRY/Tracer Bullet)
```

## State Management

ai-assist maintains persistent state to avoid redundant queries and track monitoring history:

- **Monitor State**: Tracks last check times and seen items for each monitor
- **Query Cache**: Caches query results with configurable TTL (default: 5 minutes)
- **History**: Maintains JSONL logs of monitoring checks
- **Conversation Context**: Saves interactive session context
- **Knowledge Graph**: Temporal database of all entities and relationships (NEW!)

State is stored in `~/.ai-assist/`:
```
~/.ai-assist/
├── state/
│   ├── jira_monitor.json        # Jira monitor state
│   ├── dci_monitor.json         # DCI monitor state
│   ├── cache/                   # Cached query results
│   ├── history/                 # Historical logs (JSONL)
│   └── context/                 # Saved conversation contexts
└── knowledge_graph.db           # Temporal knowledge graph (SQLite)
```

### Knowledge Graph
The knowledge graph stores:
- All DCI jobs and components with temporal tracking
- All Jira tickets with status history
- Relationships between entities
- Discovery lag (when created vs. when discovered)

Query the knowledge graph:
```bash
ai-assist /kg-stats              # View statistics
ai-assist /kg-changes 24         # Changes in last 24 hours
ai-assist /kg-asof '2026-02-04'  # Historical state
ai-assist /kg-show <id>          # Entity details
```

## Development

### Adding New MCP Servers

Add servers to `~/.ai-assist/mcp_servers.yaml` - no code changes required:

```yaml
servers:
  my-custom-server:
    command: "uvx"
    args: ["--from", "my-mcp-server", "my-mcp-server"]
    env:
      API_KEY: "${MY_API_KEY}"
```

All tools from the new server will automatically be available to the AI assistant.

### Custom Monitoring Tasks

Create monitors via interactive mode using schedule management tools:

```bash
ai-assist /interactive
You: Create a monitor called "My Custom Monitor" that checks every 10 minutes
ai-assist: *creates monitor* → Monitor 'My Custom Monitor' created successfully
      entity_type: "my_entity"
```

See example files in `.ai-assist/` directory for templates.

## Requirements

- Python 3.12+
- Anthropic API key
