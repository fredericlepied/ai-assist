# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**ai-assist** is an AI assistant for managers that integrates with Claude, MCP (Model Context Protocol) servers, Agent Skills, and a temporal knowledge graph to provide intelligent monitoring, querying, and workflow automation.

### Core Architecture

The system has four major subsystems:

1. **MCP Integration** (`agent.py`): Connects to MCP servers (DCI, Jira, etc.) and routes tool calls
2. **AWL Runtime** (`awl_parser.py`, `awl_runtime.py`, `awl_ast.py`, `awl_expressions.py`): Agent Workflow Language interpreter for multi-step workflows
3. **Knowledge Graph** (`knowledge_graph.py`): Temporal SQLite database with vector embeddings for entity tracking, change detection, and conversation memory
4. **Agent Skills** (`skills_loader.py`, `skills_manager.py`): Loads agentskills.io-compliant skills with optional sandboxed script execution

Key interaction modes:
- **Interactive** (`tui_interactive.py`): Rich TUI with streaming responses, history, tab completion
- **Monitor** (`monitors.py`, `task_runner.py`): Periodic scheduled tasks with hot-reload
- **Query** (`main.py`): One-off queries
- **AWL** (`awl_runtime.py`): Multi-step workflow execution with conditionals and loops

## Development Commands

### Setup
```bash
# Install with dev dependencies
uv sync
# or: pip install -e ".[dev]"

# Setup pre-commit hooks
make pre-commit-install
# or: pre-commit install
```

### Testing
```bash
make test                    # Run all tests (pytest with -n auto for parallelism)
make test-cov                # Run tests with coverage report (≥71% required)
make test-fast               # Skip slow/integration tests
pytest tests/test_file.py    # Run specific test file
pytest -v -s                 # Verbose with print output
```

### Code Quality
```bash
make format                  # Format with black and isort
make lint                    # Lint with ruff
make lint-fix                # Auto-fix linting issues
make pre-commit-run          # Run all pre-commit hooks
make all-checks              # format-check + lint + test (CI mode)
```

### Running the Application
```bash
uv run ai-assist                      # Interactive mode (default)
uv run ai-assist /monitor             # Start monitoring mode
uv run ai-assist /query "..."         # One-off query
uv run ai-assist /run workflow.awl    # Execute AWL workflow
uv run ai-assist --dev /interactive   # Enable code auto-reload (dev mode)
```

### Service Management (Persistent Background Service)
```bash
ai-assist /service install           # Install as persistent service (default: ~/.ai-assist)
ai-assist /service install ~/.iris   # Install additional instance
ai-assist /service start|stop|restart|status <config_dir>
ai-assist /service enable|disable <config_dir>
ai-assist /service logs <config_dir> [-f]  # View logs (-f to follow)
ai-assist /service remove <config_dir>
```

Cross-platform support:
- **Linux**: systemd user services (`~/.config/systemd/user/`)
- **macOS**: launchd user agents (`~/Library/LaunchAgents/`)

Service backend uses abstract `ServiceBackend` class for platform-specific implementations.

## Architecture Details

### MCP Agent Flow
```
User → CLI (main.py) → AiAssistAgent (agent.py) → Claude API
                                ↓
                        MCP Server Sessions
                        (DCI, Jira, GitHub, etc.)
                                ↓
                        Tool Results → Response
```

The agent (`agent.py`) maintains persistent MCP server connections and routes tool calls using the format `server_name__tool_name`.

### AWL (Agent Workflow Language)

AWL scripts define intent-driven workflows where the agent autonomously selects tools to achieve goals. Key constructs:

- `@task <name> @flags`: Defines a goal for the agent to achieve, exposing variables
- `@if <condition>`: Conditional execution with Python-like expressions
- `@loop <var> as <item> limit=N collect=<var>`: Iteration with map-reduce pattern
- `${var}`: Variable interpolation in goals and text
- `@no-kg`, `@no-history`: Flags to suppress knowledge graph context or conversation history

Files: `awl_parser.py` (parser), `awl_runtime.py` (executor), `awl_ast.py` (AST nodes), `awl_expressions.py` (variable interpolation and expression evaluation)

See `docs/AWL_SPECIFICATIONS.md` for complete syntax.

### Knowledge Graph

Temporal database tracking:
- Entities (DCI jobs, Jira tickets, conversations)
- Relationships between entities
- Change history (created_at vs discovered_at for lag detection)
- Vector embeddings for semantic search (`embedding.py`, `context.py`)

**KG Synthesis**: Nightly task extracts structured knowledge (preferences, lessons, context) from conversations and injects relevant context into future queries via semantic similarity.

**Auto Context Injection**: Semantically relevant entities are automatically surfaced in the system prompt based on query similarity.

Files: `knowledge_graph.py`, `kg_queries.py`, `kg_query_tools.py`, `knowledge_tools.py`, `embedding.py`, `context.py`

### Agent Skills

Skills follow the [agentskills.io](https://agentskills.io) specification:
- SKILL.md with YAML frontmatter (name, description, allowed-tools)
- Optional scripts/ directory for sandboxed execution
- Loaded into system prompt automatically

**Script Execution Security** (disabled by default):
- Requires `AI_ASSIST_ALLOW_SCRIPT_EXECUTION=true`
- Sandboxed environment (no API keys, 30s timeout, 20KB output limit)
- Per-skill env var allowlist via `/skill/add_env` (persisted in `~/.ai-assist/skill_env.json`)

Files: `skills_loader.py`, `skills_manager.py`, `script_execution_tools.py`, `security.py`

### Service Management

Cross-platform background service installation for persistent monitoring:
- **Linux**: systemd user services with `journalctl` logging
- **macOS**: launchd user agents with file-based logging (`~/Library/Logs/`)
- Abstract `ServiceBackend` pattern for platform extensibility
- Preserves user environment (PATH, env vars) in service context
- Multiple instance support via config directory naming

Files: `service.py`

### Configuration & State

**Configuration sources** (precedence order):
1. Environment variables (`.env` file)
2. `~/.ai-assist/mcp_servers.yaml` (MCP server definitions)
3. `~/.ai-assist/identity.yaml` (personalization)
4. `~/.ai-assist/schedules.json` (monitors/tasks)

**Hot-reload** (`config_watcher.py`, `file_watchdog.py`):
- Changes to config files trigger automatic reload without restart
- Monitor mode restarts tasks when `schedules.json` changes

**State persistence** (`~/.ai-assist/`):
- `knowledge_graph.db` - Temporal database
- `state/` - Monitor states and cache
- `allowed_commands.json` - User-approved shell commands
- `skill_env.json` - Per-skill env var allowlists
- `scheduled-actions.json` - One-time future actions
- `interactive_history.txt` - Command history

Files: `config.py`, `state.py`, `config_watcher.py`, `file_watchdog.py`

### Tools Architecture

**Built-in tools** are organized by domain:
- `report_tools.py` - Markdown report management (`~/ai-reports/`)
- `schedule_tools.py` - Create/update/delete monitors and tasks
- `schedule_action_tools.py` - One-time scheduled actions with notifications
- `knowledge_tools.py` - KG synthesis and learning
- `kg_query_tools.py` - KG querying (stats, changes, historical state)
- `filesystem_tools.py` - File operations (read, search, execute)
- `think_tool.py` - Planning/reasoning scratchpad
- `introspection_tools.py` - Context awareness (current date/time, working directory, user info)

**MCP tools** from configured servers are dynamically loaded and prefixed with server name.

**Large tool results**: All tools support `__save_to_file` parameter to save raw results to a file instead of truncating.

## Development Principles

**IMPORTANT: Read `AGENTS.md` before writing any code.** It contains detailed development guidelines, coding patterns, and examples that must be followed.

### TDD - Test-Driven Development
Write tests before implementation. Baseline assumption: all tests are green before any change.

### DRY - Don't Repeat Yourself
Avoid code duplication by creating reusable abstractions. Extract common logic to utilities.

### Tracer Bullet Development
Build end-to-end functionality early with minimal implementation, then enhance iteratively. Always maintain a working system.

### Minimize Code Branches
Keep code paths simple. Fail fast with clear errors instead of fallback branches. Handle missing dependencies at install time, not runtime.

### Error Handling
Graceful degradation for non-critical failures (e.g., one MCP server failing shouldn't crash the agent). Informative error messages for user-facing issues.

### Type Hints & Async
Always use type hints. Use `asyncio.gather()` for parallel operations and async context managers for resources.

## Important Patterns

### Tool Execution
All MCP tools use the format `server_name__tool_name`. The agent parses this and routes to the correct session.

### Monitor Pattern
Monitors (`monitors.py`) run periodic checks, cache results, and track seen items to avoid duplicate notifications. They support:
- Interval schedules (e.g., "5m", "1h", "9:00 on weekdays")
- Knowledge graph auto-save
- Notification channels (desktop, file, console)
- MCP prompts (e.g., `mcp://server/prompt`)

### Scheduled Actions
One-time future actions (`scheduled_actions.py`) execute via the `/monitor` process with notifications. The agent decides whether to send a simple notification or query via the agent based on the prompt.

Actions older than 7 days are archived to `scheduled-actions-archive.jsonl`.

### Configuration Validation
Use Pydantic models (`config.py`) for validation and environment loading with `Field(default_factory=lambda: os.getenv(...))`.

## Testing Strategy

- **Unit tests**: Individual functions/classes in isolation
- **Integration tests**: MCP server connections and tool execution
- **End-to-end tests**: Complete workflows (query → response)
- **Mock external services**: Use `pytest-asyncio` and `pytest-mock`

Run `make test-cov` to verify coverage (≥71% required for build).

## Pre-commit Hooks

Configured in `.pre-commit-config.yaml`:
- black (formatting)
- ruff (linting and import sorting)
- mypy (type checking)
- bandit (security linting)
- pylint (duplicate code detection)
- pytest (test suite with coverage ≥71%)
- YAML/JSON/TOML syntax checks
- Trailing whitespace removal

Run `pre-commit run --all-files` before declaring a feature complete.

## Code Organization

```
ai_assist/
├── main.py                    # CLI entry point
├── agent.py                   # MCP agent with tool execution
├── config.py                  # Pydantic configuration models
├── service.py                 # Cross-platform service management (systemd/launchd)
├── awl_*.py                   # AWL parser, runtime, AST, expressions
├── knowledge_graph.py         # Temporal KG database
├── embedding.py, context.py   # Vector embeddings and semantic search
├── skills_*.py                # Agent Skills loader and manager
├── tui*.py                    # Terminal UI components
├── monitors.py, tasks.py      # Monitoring and task execution
├── *_tools.py                 # Tool implementations (report, schedule, KG, filesystem, etc.)
├── scheduled_actions.py       # One-time future actions
├── notification_*.py          # Notification channels and dispatcher
├── state.py                   # State management and caching
├── *_watcher.py               # File watching and hot-reload
└── security.py                # Sandboxed script execution

tests/                         # Test suite (mirrors ai_assist structure)
docs/                          # Detailed documentation
presentation/                  # LaTeX/Beamer slides (run `make -C presentation`)
emacs/                         # AWL major mode for Emacs
```

## Configuration Files

- `.env` - Environment variables (API keys, model, feature flags)
- `~/.ai-assist/mcp_servers.yaml` - MCP server definitions
- `~/.ai-assist/identity.yaml` - User/assistant personalization
- `~/.ai-assist/schedules.json` - Monitors and periodic tasks
- `.pre-commit-config.yaml` - Git hooks configuration
- `pyproject.toml` - Python package config, tool settings, linting rules

## Documentation

Detailed documentation in `docs/`:
- `AWL_SPECIFICATIONS.md` - Complete AWL syntax and semantics
- `PERSONAL_SKILLS.md` - Creating custom Agent Skills
- `IDENTITY.md` - identity.yaml configuration guide
- `MULTI_INSTANCE.md` - Running multiple ai-assist instances
- `KNOWLEDGE_MANAGEMENT.md` - Knowledge graph usage and synthesis
- `SCHEDULED_ACTIONS.md` - One-time future actions

Also see:
- `AGENTS.md` - Development philosophy (TDD/DRY/Tracer Bullet)
- `CONTRIBUTING.md` - Pre-commit setup and workflow
- `SECURITY.md` - Security model for skill scripts
- `VERTEX_AI_SETUP.md` - Vertex AI configuration

## Common Tasks

### Adding a New Tool
1. Create tool function in appropriate `*_tools.py` file
2. Add to `get_builtin_tools()` in that file
3. Write tests in `tests/test_*_tools.py`
4. Update README.md if user-facing

### Adding a New MCP Server
1. Add server config to `~/.ai-assist/mcp_servers.yaml`
2. Test connection in interactive mode
3. Document available tools in README.md

### Adding a New AWL Feature
1. Update AST nodes in `awl_ast.py` if needed
2. Update parser in `awl_parser.py`
3. Update runtime in `awl_runtime.py`
4. Add tests in `tests/test_awl_*.py`
5. Update `docs/AWL_SPECIFICATIONS.md`

### Adding Platform Support for Service Management
1. Create new class inheriting from `ServiceBackend` in `service.py`
2. Implement all abstract methods: `service_file_path`, `service_content`, `install`, `remove`, `action`, `status`, `logs`
3. Add platform detection in `_get_backend()` factory function
4. Write tests in `tests/test_service.py`
5. Document platform-specific requirements in README.md

### Debugging
- Enable verbose logging: Set `logging.basicConfig(level=logging.DEBUG)` in code
- Test components individually: `python -c "from ai_assist.module import ..."`
- Check state: Inspect `~/.ai-assist/` directory contents
- Monitor mode logs: Check console output or use systemd logs if running as service
- Use `--dev` flag for code auto-reload during development

## Important Notes

- **All tests must be green before any change** (TDD baseline assumption)
- **No automatic truncation** - tools support `__save_to_file` to handle large results
- **Security**: Script execution is disabled by default. Only enable if you trust installed skills.
- **Extended context**: 1M token window is opt-in via `AI_ASSIST_ALLOW_EXTENDED_CONTEXT=true` (2x pricing above 200K)
- **Vertex AI users**: Use `@` format for model names (e.g., `claude-sonnet-4-5@20250929`)
