# BOSS - AI Assistant for Managers

An intelligent AI assistant powered by Claude and MCP (Model Context Protocol) that helps managers monitor Jira projects and DCI (Distributed CI) jobs with periodic automated checks and interactive querying.

## Features

- 🤖 **AI-Powered Assistant**: Uses Claude Sonnet 4.5 for intelligent analysis and responses
- 🔌 **MCP Integration**: Connects to MCP servers for DCI and Jira tools
- 📊 **Periodic Monitoring**: Automated scheduled checks for Jira and DCI updates
- 📝 **User-Defined Tasks**: Create custom periodic tasks via YAML configuration (NEW!)
- 🔄 **Hot Reload**: Update task definitions without restarting
- ⚡ **Conditional Actions**: Trigger notifications and actions based on results
- 💬 **Interactive Mode**: Chat with the assistant to query information
- 🎯 **Targeted Queries**: Run one-off queries for specific information
- 🔔 **Notifications**: Get alerts about important updates (configurable)

## Quick Start

### Prerequisites

**You will need (choose ONE Anthropic method)**:

**Option A: Vertex AI** (Google Cloud - Recommended for enterprise)
1. ✅ **Google Cloud Project with Vertex AI** - Your company likely has this
2. ✅ **DCI Credentials** - From your DCI administrator
3. ⚠️ **Jira Token** - Optional, only if you want Jira monitoring
4. ⚠️ **Google Credentials** - Optional, only if you want Google Docs integration

**Option B: Direct API** (Personal/Free tier)
1. ✅ **Anthropic API Key** - Get from https://console.anthropic.com/ (free tier available)
2. ✅ **DCI Credentials** - From your DCI administrator
3. ⚠️ **Jira Token** - Optional, only if you want Jira monitoring
4. ⚠️ **Google Credentials** - Optional, only if you want Google Docs integration

### Installation

1. Clone the repository:
```bash
git clone <your-repo-url>
cd boss
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
DCI_CLIENT_ID=your_dci_client_id                 # From your DCI admin
DCI_API_SECRET=your_dci_api_secret               # From your DCI admin
```

**Option B - Direct API** (personal/free tier):
```bash
ANTHROPIC_API_KEY=your_anthropic_key_here  # Get from console.anthropic.com
DCI_CLIENT_ID=your_dci_client_id           # From your DCI admin
DCI_API_SECRET=your_dci_api_secret         # From your DCI admin
```

## Configuration

BOSS uses YAML files for configuration, making it easy to customize without editing code.

### Environment Variables (.env)

Create a `.env` file with authentication credentials:

```bash
# Required: Anthropic API access (choose ONE method)
# Method 1: Vertex AI (Google Cloud - enterprise)
ANTHROPIC_VERTEX_PROJECT_ID=your-gcp-project-id
# ANTHROPIC_VERTEX_REGION=us-east5  # Optional

# Method 2: Direct API Key (personal/free tier)
ANTHROPIC_API_KEY=your_api_key_here

# API credentials (used by MCP servers if not in YAML)
DCI_CLIENT_ID=your_dci_client_id
DCI_API_SECRET=your_dci_api_secret
DCI_CS_URL=https://api.distributed-ci.io
JIRA_API_TOKEN=your_jira_token
JIRA_URL=https://issues.redhat.com
GOOGLE_APPLICATION_CREDENTIALS=/path/to/credentials.json
```

### MCP Servers Configuration (~/.boss/mcp_servers.yaml)

Configure MCP servers in `~/.boss/mcp_servers.yaml`:

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

Copy from `.boss/mcp_servers.yaml.example` to get started.

### Monitors Configuration (~/.boss/monitors.yaml)

Configure monitoring tasks in `~/.boss/monitors.yaml`:

```yaml
monitors:
  - name: "Jira Project Monitor"
    interval: 5m
    enabled: true
    prompt: |
      Search Jira tickets in projects: CILAB, CNF
      Query: updated >= -1d ORDER BY updated DESC
    knowledge_graph:
      enabled: true
      mcp_tool: "dci__search_jira_tickets"
      entity_type: "jira_ticket"
      parse_json: true
      tool_args:
        jql: "project in (CILAB, CNF) AND updated >= -1d"
        max_results: 20

  - name: "DCI Failures Monitor"
    interval: 5m
    enabled: true
    prompt: |
      Search DCI jobs with status failure or error in last 24 hours.
      Provide concise summary.
    knowledge_graph:
      enabled: true
      mcp_tool: "dci__search_dci_jobs"
      entity_type: "dci_job"
      parse_json: true
      tool_args:
        query: "((status in ['failure', 'error']) and (created_at >= '2026-02-03'))"
        limit: 20
```

Copy from `.boss/monitors.yaml.example` to get started.

### Getting API Credentials

**Anthropic Authentication (REQUIRED - Choose ONE method):**

BOSS requires Anthropic API access to power the AI assistant. Choose the method that fits your situation:

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

**Jira API Token:**
1. Go to https://issues.redhat.com/secure/ViewProfile.jspa
2. Click "Personal Access Tokens" → "Create token"
3. Copy the token and set it as `JIRA_API_TOKEN`

**DCI Credentials:**
Contact your DCI administrator for `DCI_CLIENT_ID` and `DCI_API_SECRET`.

**Google Docs (optional):**
Follow Google Cloud documentation to create service account credentials.

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
BOSS_MODEL=claude-sonnet-4-5@20250929
```

**Available Models**

To discover which models are available in your project:
```bash
uv run python discover_vertex_models.py
```

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
boss /interactive
# or simply
boss
```

Example queries:
- "What are the latest failing DCI jobs?"
- "Show me critical Jira tickets in the CILAB project"
- "Find OpenShift 4.19 jobs that failed in the last week"

### Monitoring Mode

Run periodic monitoring tasks:

```bash
boss /monitor
```

This will:
- Check configured Jira projects every 5 minutes (default)
- Check DCI jobs every 5 minutes (default)
- **Store all findings in the temporal knowledge graph** (automatic)
- Run user-defined tasks from `~/.boss/tasks.yaml` (if configured)
- Report findings to console or configured notification channel

**Knowledge Graph Integration:**
All DCI jobs and Jira tickets are automatically stored in the temporal knowledge graph, allowing you to:
- Query historical data (`boss /kg-asof '2026-02-04 14:00'`)
- Track changes over time (`boss /kg-changes 24`)
- Find late discoveries (`boss /kg-late 60`)
- View entity details (`boss /kg-show <id>`)

See [KNOWLEDGE_GRAPH_INTEGRATION.md](KNOWLEDGE_GRAPH_INTEGRATION.md) for details.

### User-Defined Tasks

Create custom periodic tasks without writing code! Define tasks in `~/.boss/tasks.yaml`:

```yaml
tasks:
  # Simple interval-based task
  - name: "Critical Failures Monitor"
    interval: 10m
    prompt: |
      Search for DCI jobs with status failure or error in the last hour.
      Provide a summary with job IDs and issues.
    conditions:
      - if: "failures > 0"
        then:
          action: notify
          message: "⚠️ Found {failures} critical failures!"

  # Time-based task (NEW!)
  - name: "Morning Standup"
    interval: "morning on weekdays"  # 9:00 AM Mon-Fri
    prompt: "Check for overnight issues and urgent items"
```

**Features:**
- ✅ Simple YAML configuration
- ✅ Any interval (30s, 5m, 1h, 24h, etc.)
- ✅ Natural language prompts
- ✅ Conditional actions (notify, log, create docs)
- ✅ Hot reload - changes take effect within 5 seconds
- ✅ Automatic metadata extraction from results

See [TASKS.md](TASKS.md) for complete documentation and examples.

### One-off Query

Run a single query and exit:

```bash
boss /query "What are the top 5 failing DCI jobs today?"
```

### State Management

View and manage persistent state:

```bash
# View state statistics
boss /status

# Clear expired cache
boss /clear-cache
```

In interactive mode, you can use special commands:
- `/status` - Show state statistics
- `/history` - Show recent monitoring history
- `/clear-cache` - Clear expired cache entries
- `/exit` or `/quit` - Exit interactive mode

## Available Tools

The assistant has access to tools from the **dci-mcp-server**, which provides:

### DCI Tools
- `search_dci_jobs` - Search DCI jobs with advanced query language
- `query_dci_components` - Lookup DCI components (OpenShift releases, etc.)
- `query_dci_teams` - Query DCI teams
- `query_dci_remotecis` - Query DCI remote CI labs
- `download_dci_file` - Download job artifacts and files
- `today` / `now` - Get current date/time for queries

### Jira Tools (via dci-mcp-server)
- `search_jira_tickets` - Search tickets with JQL queries
- `get_jira_ticket` - Get detailed ticket info with comments and changelog
- `get_jira_project_info` - Get project information

### Google Docs Tools (via dci-mcp-server)
- `create_google_doc_from_markdown` - Create Google Docs from markdown
- `create_google_doc_from_file` - Convert markdown files to Google Docs
- `convert_dci_report_to_google_doc` - Convert DCI reports to Google Docs
- `list_google_docs` - List your Google Docs
- `find_folder_by_name` - Find folders in Google Drive

### Example Queries

```bash
# Find recent OpenShift failures
boss /query "Find all OCP 4.19 jobs that failed in the last 3 days"

# Check Jira status
boss /query "What are the critical bugs in CILAB project?"

# Analyze patterns
boss /query "What are the common failure patterns in daily DCI jobs?"

# Generate reports
boss /query "Create a summary report of this week's DCI failures and save it"
```

## Project Structure

```
boss/
├── boss/
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

BOSS maintains persistent state to avoid redundant queries and track monitoring history:

- **Monitor State**: Tracks last check times and seen items for each monitor
- **Query Cache**: Caches query results with configurable TTL (default: 5 minutes)
- **History**: Maintains JSONL logs of monitoring checks
- **Conversation Context**: Saves interactive session context
- **Knowledge Graph**: Temporal database of all entities and relationships (NEW!)

State is stored in `~/.boss/`:
```
~/.boss/
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
boss /kg-stats              # View statistics
boss /kg-changes 24         # Changes in last 24 hours
boss /kg-asof '2026-02-04'  # Historical state
boss /kg-show <id>          # Entity details
```

## Development

### Adding New MCP Servers

Add servers to `~/.boss/mcp_servers.yaml` - no code changes required:

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

Add monitors to `~/.boss/monitors.yaml` - no code changes required:

```yaml
monitors:
  - name: "My Custom Monitor"
    interval: 10m
    prompt: "Your monitoring query here"
    knowledge_graph:
      enabled: true
      mcp_tool: "server__tool_name"
      entity_type: "my_entity"
```

See example files in `.boss/` directory for templates.

## Requirements

- Python 3.12+
- Anthropic API key
- DCI credentials (optional, for DCI monitoring)
- Jira API token (optional, for Jira monitoring)

## License

[Add your license here]

## Contributing

[Add contributing guidelines here]
