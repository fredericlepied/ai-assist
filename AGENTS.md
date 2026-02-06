# AGENTS.md - Development Guide for AI Agents and Developers

This document provides guidance for AI agents and developers working on the ai-assist project. It outlines the project architecture, development principles, and best practices.

## Project Overview

**ai-assist** (AI Assistant for Managers) is an intelligent assistant that helps managers monitor and analyze Jira projects and DCI (Distributed CI) jobs through natural language interaction.

### Core Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    ai-assist CLI Interface                    │
│         (Interactive / Monitor / Query modes)            │
└───────────────────────┬─────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────┐
│                    AiAssistAgent                             │
│  - Manages conversation with Claude                      │
│  - Routes tool calls to MCP servers                      │
│  - Handles multi-turn interactions                       │
└───────────────────────┬─────────────────────────────────┘
                        │
        ┌───────────────┼───────────────┐
        │               │               │
┌───────▼────────┐ ┌───▼────────┐ ┌───▼────────────┐
│ dci-mcp-server │ │   Future   │ │    Future      │
│                │ │   MCP      │ │     MCP        │
│ - DCI Tools    │ │  Servers   │ │   Servers      │
│ - Jira Tools   │ │            │ │                │
│ - Google Docs  │ │            │ │                │
└────────────────┘ └────────────┘ └────────────────┘
```

### Key Components

1. **ai_assist/main.py**: CLI entry point, handles user interaction modes
2. **ai_assist/agent.py**: MCP agent implementation, manages Claude conversations and tool execution
3. **ai_assist/config.py**: Configuration management using Pydantic models
4. **ai_assist/monitors.py**: Periodic monitoring tasks for Jira and DCI
5. **ai_assist/state.py**: State management, caching, and history tracking

## Documentation

Only create the minimum document for the end user.

No need for implementation docs and comments. The code should be self explanatory.

Use comments only to document something unusual.

## Development Principles

### 1. TDD - Test-Driven Development

**Philosophy**: Write tests before implementation to ensure correctness and maintainability.

#### Testing Strategy for ai-assist

```python
# Example test structure (to be implemented)

# tests/test_agent.py
async def test_agent_connects_to_mcp_servers():
    """Test that agent successfully connects to configured MCP servers"""
    config = AiAssistConfig(
        anthropic_api_key="test-key",
        mcp_servers={"test": MCPServerConfig(command="echo", args=["test"])}
    )
    agent = AiAssistAgent(config)
    await agent.connect_to_servers()
    assert "test" in agent.sessions

async def test_agent_executes_tool_call():
    """Test that agent can execute a tool call and return results"""
    # Mock MCP server response
    # Execute tool
    # Assert correct result format

# tests/test_monitors.py
async def test_jira_monitor_queries_projects():
    """Test that JiraMonitor queries configured projects"""
    # Mock agent
    # Create monitor with test projects
    # Run check
    # Assert correct projects were queried

async def test_dci_monitor_reports_failures():
    """Test that DCIMonitor identifies and reports failures"""
    # Mock agent with failing jobs
    # Run check
    # Assert failures are reported
```

#### TDD Workflow

1. **Red**: Write a failing test that defines desired behavior
2. **Green**: Write minimal code to make the test pass
3. **Refactor**: Clean up code while keeping tests green

#### Testing Guidelines

- **Unit Tests**: Test individual functions and classes in isolation
- **Integration Tests**: Test MCP server connections and tool execution
- **End-to-End Tests**: Test complete workflows (query → response)
- **Mock External Services**: Use pytest-asyncio and mock for external APIs
- **Test Error Handling**: Ensure graceful degradation when services fail

```bash
# Running tests (when implemented)
pytest tests/
pytest tests/test_agent.py -v
pytest tests/ --cov=ai_assist --cov-report=html
```

### 2. DRY - Don't Repeat Yourself

**Philosophy**: Avoid code duplication by creating reusable abstractions.

#### DRY Patterns in ai-assist

**✓ Good: Reusable Configuration**
```python
# ai_assist/config.py - Single source of truth for configuration
class AiAssistConfig(BaseModel):
    @classmethod
    def from_env(cls) -> "AiAssistConfig":
        """Load configuration from environment"""
        # Configuration logic in one place
```

**✗ Bad: Repeated Configuration Loading**
```python
# Don't do this in multiple files
api_key = os.getenv("ANTHROPIC_API_KEY")
dci_client = os.getenv("DCI_CLIENT_ID")
```

**✓ Good: Centralized Tool Execution**
```python
# ai_assist/agent.py - Single method for all tool execution
async def _execute_tool(self, tool_name: str, arguments: dict) -> str:
    """Execute any tool on any MCP server"""
    # Parse server and tool
    # Route to correct server
    # Return formatted result
```

**✗ Bad: Repeated Tool Execution Logic**
```python
# Don't implement tool execution separately for each server
async def execute_dci_tool(...):
async def execute_jira_tool(...):
```

#### DRY Checklist

- [ ] Is this logic used in multiple places? → Extract to a function
- [ ] Are these patterns similar? → Create a base class or utility
- [ ] Is this configuration repeated? → Centralize in config.py
- [ ] Are these error messages duplicated? → Use constants or templates
- [ ] Is this query pattern repeated? → Create a query builder

### 3. Tracer Bullet Development

**Philosophy**: Build end-to-end functionality early, then enhance iteratively.

#### Tracer Bullet Approach

A "tracer bullet" is a minimal end-to-end implementation that proves the architecture works. Like tracer ammunition that shows the bullet's path, this approach shows that data flows correctly through the system.

#### ai-assist Tracer Bullets

**Tracer Bullet 1: Basic Query Flow** ✓ Implemented
```
User Input → CLI → Agent → Claude → MCP Tool → Result → User
```

**Tracer Bullet 2: Monitoring Loop** ✓ Implemented
```
Scheduler → Monitor → Agent → Tool Call → Report → Console
```

**Tracer Bullet 3: Multi-Server Integration** (Future)
```
Agent → Server A → Tool 1 → Result
     → Server B → Tool 2 → Result
     → Combine → Response
```

#### Implementing New Features with Tracer Bullets

Example: Adding Slack Notifications

**Phase 1: Tracer Bullet (Minimal End-to-End)**
```python
# ai_assist/notifications.py
class SlackNotifier:
    async def send(self, message: str):
        print(f"[Slack] {message}")  # Console output first

# ai_assist/monitors.py
def _report_results(self, monitor_name: str, results: list[dict]):
    notifier = SlackNotifier()
    await notifier.send(f"{monitor_name}: {len(results)} updates")
```

**Phase 2: Enhancement**
```python
class SlackNotifier:
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    async def send(self, message: str):
        async with httpx.AsyncClient() as client:
            await client.post(self.webhook_url, json={"text": message})
```

**Phase 3: Polish**
```python
class SlackNotifier:
    async def send(self, message: str, attachments: list[dict] = None):
        # Rich formatting
        # Error handling
        # Retry logic
        # Rate limiting
```

#### Tracer Bullet Benefits

1. **Early Validation**: Proves architecture works before investing in details
2. **Continuous Integration**: Always have a working system
3. **Risk Reduction**: Identifies integration issues early
4. **Stakeholder Feedback**: Get feedback on working features, not mockups
5. **Momentum**: Visible progress maintains motivation

### 4. Additional Best Practices

#### Code Organization

```
ai_assist/
├── __init__.py          # Package info only
├── main.py             # CLI and user interaction
├── agent.py            # Core agent logic
├── config.py           # Configuration models
├── state.py            # State management and caching
├── monitors.py         # Monitoring tasks
├── notifications.py    # (Future) Notification handlers
└── utils.py            # (Future) Shared utilities

tests/
├── test_agent.py       # Agent tests
├── test_config.py      # Configuration tests
├── test_monitors.py    # Monitor tests
└── conftest.py         # Shared test fixtures
```

#### Minimize Code Branches

**Philosophy**: Keep code paths simple. Avoid fallbacks and conditional branches unless absolutely necessary.

**Why:**
- Fewer branches = fewer bugs
- Easier to test (no need to test multiple paths)
- Clearer code flow
- Faster debugging

**✓ Good: Fail fast with clear error**
```python
from google.cloud import aiplatform

def discover_models():
    # Initialize Vertex AI
    aiplatform.init(project=project_id, location=region)

    # Query for models
    models = aiplatform.Model.list(filter='...')

    return models
```

**✗ Bad: Fallback branches**
```python
def discover_models():
    try:
        from google.cloud import aiplatform
        # Try API approach
        models = aiplatform.Model.list(...)
        return models
    except ImportError:
        # Fallback to hardcoded list
        return test_known_models()
    except Exception:
        # Another fallback
        return default_models()
```

**When to have branches:**
- User-facing choices (interactive prompts, command flags)
- Data-driven logic (different entity types, different formats)
- NOT for: missing dependencies, API failures, "just in case" scenarios

**Handle missing dependencies at install time:**
```python
# In pyproject.toml
dependencies = [
    "anthropic",
    "google-cloud-aiplatform",  # Required, not optional
]
```

**Handle errors clearly:**
```python
try:
    models = aiplatform.Model.list(...)
except Exception as e:
    print(f"Error: Failed to discover models: {e}")
    print("Make sure google-cloud-aiplatform is installed:")
    print("  pip install google-cloud-aiplatform")
    sys.exit(1)
```

#### Error Handling

**Graceful Degradation**
```python
async def connect_to_servers(self):
    """Connect to all configured MCP servers"""
    for server_name, server_config in self.config.mcp_servers.items():
        try:
            await self._connect_server(server_name, server_config)
            print(f"✓ Connected to {server_name} MCP server")
        except Exception as e:
            # Don't fail completely - log and continue
            print(f"✗ Failed to connect to {server_name}: {e}")
```

**Informative Error Messages**
```python
if not config.anthropic_api_key:
    print("Error: ANTHROPIC_API_KEY not set in environment")
    print("Please add it to your .env file or export it:")
    print("  export ANTHROPIC_API_KEY='your-key-here'")
    sys.exit(1)
```

#### Async/Await Patterns

```python
# Use asyncio.gather() for parallel operations
async def check_all_projects(self):
    tasks = [self.check_project(p) for p in self.projects]
    results = await asyncio.gather(*tasks, return_exceptions=True)

# Use async context managers for resources
async def _connect_server(self, name: str, config: MCPServerConfig):
    async with stdio_client(server_params) as (stdio, write):
        session = ClientSession(stdio, write)
        await session.initialize()
```

#### Type Hints

```python
# Always use type hints for better IDE support and documentation
from typing import Optional, List, Dict

async def query(self, prompt: str, max_turns: int = 10) -> str:
    messages: List[Dict[str, str]] = [{"role": "user", "content": prompt}]
    tool_results: List[Dict] = []
```

## Development Workflow

### Adding a New Feature

1. **Define**: Write a clear specification in an issue or comment
2. **Test First**: Write failing tests that define the behavior (TDD)
3. **Tracer Bullet**: Implement minimal end-to-end functionality
4. **Iterate**: Enhance incrementally while keeping tests green
5. **Refactor**: Apply DRY principle to eliminate duplication
6. **Document**: Update README.md and AGENTS.md

### Adding a New MCP Server

1. **Configure**: Add server to `config.py`
2. **Test Connection**: Verify connection in `agent.py`
3. **Document Tools**: List available tools in README.md
4. **Create Monitor**: If needed, add monitor in `monitors.py`
5. **Test Integration**: Write tests for the new server

### Example: Adding GitHub MCP Server

```python
# 1. Add to config.py
mcp_servers={
    "dci": MCPServerConfig(...),
    "github": MCPServerConfig(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-github"],
        env={"GITHUB_TOKEN": os.getenv("GITHUB_TOKEN", "")}
    ),
}

# 2. Test (tests/test_github_integration.py)
async def test_github_server_connection():
    config = get_test_config_with_github()
    agent = AiAssistAgent(config)
    await agent.connect_to_servers()
    assert "github" in agent.sessions

# 3. Add monitor (ai_assist/monitors.py)
class GitHubMonitor:
    async def check(self):
        """Check for PR updates"""
        prompt = "List open PRs that need review"
        return await self.agent.query(prompt)

# 4. Document (README.md)
### GitHub Tools
- Search repositories
- List pull requests
- Get issue details
```

## Debugging Tips

### Enable Verbose Logging

```python
# ai_assist/agent.py
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

logger.debug(f"Executing tool: {tool_name} with args: {arguments}")
```

### Test Individual Components

```python
# Test config loading
python -c "from ai_assist.config import get_config; print(get_config())"

# Test agent connection
python -c "import asyncio; from ai_assist.agent import AiAssistAgent; from ai_assist.config import get_config; asyncio.run(AiAssistAgent(get_config()).connect_to_servers())"
```

### Mock MCP Servers for Testing

```python
# tests/conftest.py
import pytest
from unittest.mock import AsyncMock, MagicMock

@pytest.fixture
def mock_mcp_session():
    session = AsyncMock()
    session.list_tools.return_value = MagicMock(tools=[])
    session.call_tool.return_value = MagicMock(content=[MagicMock(text="test result")])
    return session
```

## State Management Pattern

ai-assist uses persistent state to avoid redundant queries and maintain context:

```python
# Check cache before querying
cache_key = f"query_{unique_identifier}"
cached = state_manager.get_cached_query(cache_key)

if cached:
    return cached

# Perform query
result = await agent.query(prompt)

# Cache the result with TTL
state_manager.cache_query_result(cache_key, result, ttl_seconds=300)

# Track seen items
state_manager.update_monitor(
    monitor_name,
    results,
    seen_items=set(item_ids)
)

# Append to history
state_manager.append_history(monitor_name, result)
```

### Benefits of State Management

1. **Reduced API Calls**: Cache prevents redundant queries within TTL window
2. **Change Detection**: Track what's new vs. what was already seen
3. **Historical Context**: Maintain logs for trend analysis
4. **Offline Capability**: Use cached data when services are unavailable
5. **Cost Efficiency**: Fewer Claude API calls and MCP tool executions

## Common Patterns

### Query Pattern for Monitors

```python
async def check(self) -> list[dict]:
    """Standard monitor check pattern"""
    results = []

    for query_item in self.query_items:
        prompt = self._build_prompt(query_item)

        try:
            result = await self.agent.query(prompt)
            results.append({
                "item": query_item,
                "summary": result,
                "timestamp": datetime.now().isoformat(),
            })
        except Exception as e:
            logger.error(f"Error checking {query_item}: {e}")

    self.last_check = datetime.now()
    return results
```

### Configuration Pattern

```python
# Use Pydantic for validation and environment loading
class MyConfig(BaseModel):
    setting: str = Field(default_factory=lambda: os.getenv("MY_SETTING", "default"))
    number: int = Field(default=42, ge=0, le=100)

    @validator("setting")
    def validate_setting(cls, v):
        if not v:
            raise ValueError("Setting cannot be empty")
        return v
```

## Future Enhancements

### Potential Features (Apply Tracer Bullet Approach)

1. **Multi-Channel Notifications**
   - Tracer: Console output
   - Enhance: Email support
   - Polish: Slack, Teams, webhooks

2. **Report Generation**
   - Tracer: Print to console
   - Enhance: Save to markdown file
   - Polish: Generate Google Docs, PDFs

3. **Intelligent Alerting**
   - Tracer: Alert on any failure
   - Enhance: Alert on patterns (3+ failures)
   - Polish: ML-based anomaly detection

4. **Dashboard**
   - Tracer: CLI status command
   - Enhance: Static HTML page
   - Polish: Live web dashboard

## Resources

- **MCP Documentation**: https://modelcontextprotocol.io/
- **mcp-agent**: https://github.com/anthropics/mcp-agent-python
- **Anthropic API**: https://docs.anthropic.com/
- **DCI Documentation**: https://docs.distributed-ci.io/

## Contributing

When contributing to ai-assist:

1. Follow TDD: Write tests first
2. Apply DRY: Avoid duplication
3. Use Tracer Bullets: Start simple, enhance iteratively
4. Document: Update AGENTS.md and README.md
5. Type Hints: Always use type annotations
6. Error Handling: Graceful degradation, informative messages

## Questions for AI Agents

When working on ai-assist, ask yourself:

- [ ] Does this change have tests? (TDD)
- [ ] Am I repeating existing code? (DRY)
- [ ] Can I implement this in phases? (Tracer Bullet)
- [ ] Is the error handling graceful?
- [ ] Are types properly annotated?
- [ ] Is the configuration centralized?
- [ ] Does it follow existing patterns?
- [ ] Is it documented?

---

**Remember**: The goal is to build a reliable, maintainable AI assistant. Take the time to do it right, and the system will be easier to enhance and debug over time.
