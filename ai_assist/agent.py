"""MCP Agent for ai-assist"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from anthropic import Anthropic, AnthropicVertex
from mcp import ClientSession, StdioServerParameters

from .audit import AuditLogger
from .config import AiAssistConfig, MCPServerConfig
from .filesystem_tools import FilesystemTools
from .identity import get_identity
from .introspection_tools import IntrospectionTools
from .mcp_stdio_fix import stdio_client_fixed
from .report_tools import ReportTools
from .schedule_tools import ScheduleTools
from .script_execution_tools import ScriptExecutionTools
from .skills_loader import SkillsLoader
from .skills_manager import SkillsManager

if TYPE_CHECKING:
    from .context import ConversationMemory
    from .knowledge_graph import KnowledgeGraph


SYNTHESIS_PROMPT_TEMPLATE = """Review this conversation and identify learnings to save.

Extract:
- **User Preferences**: Stated preferences about code style, workflows, tools
- **Lessons Learned**: Insights about bugs, patterns, best practices, gotchas
- **Project Context**: Background about projects, goals, teams, constraints
- **Decision Rationale**: Why certain implementation choices were made

For each learning:
- Write 1-2 sentence summary
- Suggest unique key (e.g., "python_test_framework", "dci_friday_failures")
- Assign confidence (0.0-1.0 based on how explicit/clear it was)
- Add relevant tags

Focus: {focus}

Conversation:
{history_text}

Output valid JSON only (no markdown):
{{
  "insights": [
    {{
      "category": "user_preference|lesson_learned|project_context|decision_rationale",
      "key": "unique_identifier",
      "content": "1-2 sentence summary",
      "confidence": 0.9,
      "tags": ["tag1", "tag2"]
    }}
  ]
}}

If no learnings, return {{"insights": []}}
"""


class AiAssistAgent:
    """AI Agent with MCP capabilities"""

    # Model-specific max output tokens
    # Source: https://docs.anthropic.com/en/docs/about-claude/models
    MODEL_MAX_TOKENS = {
        # Claude 4.6 series (Feb 2026)
        "claude-opus-4-6@20260205": 128000,  # 128K output tokens!
        "claude-opus-4-6-20260205": 128000,
        "claude-opus-4-6@default": 128000,  # Vertex AI default version
        # Claude 4.5 series (Nov 2025)
        "claude-opus-4-5@20251101": 64000,  # 64K output tokens
        "claude-opus-4-5-20251101": 64000,
        "claude-opus-4-5@default": 64000,  # Vertex AI default version
        "claude-sonnet-4-5@20250929": 8192,
        "claude-sonnet-4-5-20250929": 8192,
        "claude-sonnet-4-5@default": 8192,  # Vertex AI default version
        # Claude 3.5 series
        "claude-3-5-sonnet-20241022": 8192,
        "claude-3-5-sonnet-20240620": 8192,
        "claude-3-5-haiku-20241022": 8192,
        # Claude 3 series
        "claude-3-opus-20240229": 4096,
        "claude-3-sonnet-20240229": 4096,
        "claude-3-haiku-20240307": 4096,
    }

    # Model-specific context window sizes (input tokens)
    MODEL_CONTEXT_WINDOWS = {
        "claude-opus-4-6": 200000,
        "claude-opus-4-5": 200000,
        "claude-sonnet-4-5": 200000,
        "claude-3-5-sonnet": 200000,
        "claude-3-5-haiku": 200000,
        "claude-3-opus": 200000,
        "claude-3-sonnet": 200000,
        "claude-3-haiku": 200000,
    }

    CONTEXT_BUDGET_WARNING_THRESHOLD = 0.8

    # Extended context window (1M tokens, beta)
    EXTENDED_CONTEXT_MODELS = {"claude-opus-4-6", "claude-sonnet-4-6", "claude-sonnet-4-5", "claude-sonnet-4"}
    EXTENDED_CONTEXT_WINDOW = 1000000
    EXTENDED_CONTEXT_BETA_HEADER = "context-1m-2025-08-07"
    EXTENDED_CONTEXT_ACTIVATION_THRESHOLD = 0.75  # Activate at 75% of 200K (150K tokens)

    def __init__(self, config: AiAssistConfig, knowledge_graph: Optional["KnowledgeGraph"] = None):
        self.config = config
        self.knowledge_graph = knowledge_graph
        self.kg_save_enabled = True  # Can be toggled by user

        # Load identity for personalized interactions
        self.identity = get_identity()

        # Initialize introspection tools for self-awareness
        self.introspection_tools = IntrospectionTools(knowledge_graph=knowledge_graph)

        # Initialize internal report tools
        self.report_tools = ReportTools()

        # Initialize internal schedule management tools
        self.schedule_tools = ScheduleTools()

        # Initialize internal filesystem tools
        self.filesystem_tools = FilesystemTools(config)

        # Initialize audit logger
        self.audit_logger = AuditLogger()

        # Set by TUI to pause spinner/watcher during confirmation prompts
        self._active_live: Any = None
        self._active_escape_watcher: Any = None

        # Initialize schedule action tools (one-shot future actions)
        from ai_assist.schedule_action_tools import ScheduleActionTools

        self.schedule_action_tools = ScheduleActionTools(self)

        # Initialize skills system
        self.skills_loader = SkillsLoader()
        self.skills_manager = SkillsManager(self.skills_loader)

        # Initialize script execution tools for Agent Skills
        self.script_execution_tools = ScriptExecutionTools(self.skills_manager, config)

        self.anthropic: Anthropic | AnthropicVertex
        if config.use_vertex:
            vertex_kwargs: dict[str, Any] = {"project_id": config.vertex_project_id}
            if config.vertex_region:
                vertex_kwargs["region"] = config.vertex_region
                print(f"Using Vertex AI: project={config.vertex_project_id}, region={config.vertex_region}")
            else:
                print(f"Using Vertex AI: project={config.vertex_project_id} (default region)")

            self.anthropic = AnthropicVertex(**vertex_kwargs)
        else:
            self.anthropic = Anthropic(api_key=config.anthropic_api_key)

        # Display model configuration
        max_tokens = self.get_max_tokens()
        print(f"🤖 Model: {config.model} (max output tokens: {max_tokens:,})")
        if self._supports_extended_context():
            print("   Extended context: available (1M, activates on demand)")

        # Track whether extended context is currently active (per-query)
        self._extended_context_active = False
        # Track whether grounding nudge fired during current query
        self._grounding_nudge_fired = False

        self.sessions: dict[str, ClientSession] = {}
        self.available_tools: list[dict] = []
        self.available_prompts: dict[str, dict] = {}  # {server_name: {prompt_name: Prompt}}
        self._server_tasks: list[asyncio.Task] = []

        # Track tool calls for KG storage
        self.last_tool_calls: list[dict] = []

        # Callback for inner execution visibility (e.g., during execute_mcp_prompt)
        self.on_inner_execution: Any = None

        # Active cancel event (set by query_streaming, used by execute_mcp_prompt)
        self._cancel_event: Any = None

        # Update introspection tools with reference to available_prompts and agent
        # (will be populated during server connection)
        self.introspection_tools.available_prompts = self.available_prompts
        self.introspection_tools.agent = self  # Allow introspection tools to execute prompts

        # Initialize knowledge management tools
        self.knowledge_tools: Any = None
        self.kg_query_tools: Any = None
        if self.knowledge_graph:
            from ai_assist.kg_query_tools import KGQueryTools
            from ai_assist.knowledge_tools import KnowledgeTools

            self.knowledge_tools = KnowledgeTools(self.knowledge_graph)
            self.knowledge_tools.agent = self
            self.kg_query_tools = KGQueryTools(self.knowledge_graph)

        # Track synthesis flag
        self._pending_synthesis: Any = None

        # Token usage tracking per query
        self._turn_token_usage: list[dict[str, Any]] = []

    def get_max_tokens(self) -> int:
        """Get max output tokens for the current model

        Returns:
            Maximum output tokens supported by the model
        """
        model = self.config.model
        max_tokens = self.MODEL_MAX_TOKENS.get(model)

        if max_tokens is None:
            # Unknown model - try to infer from name patterns
            if "opus-4-6" in model.lower() or "opus-4.6" in model.lower():
                max_tokens = 128000  # Opus 4.6 and later
            elif "opus-4-5" in model.lower() or "opus-4.5" in model.lower():
                max_tokens = 64000  # Opus 4.5
            elif "opus-4" in model.lower():
                max_tokens = 64000  # Conservative default for Opus 4.x
            elif "sonnet-4" in model.lower() or "3-5-" in model:
                max_tokens = 8192
            else:
                # Conservative default for unknown models
                max_tokens = 4096
                print(f"⚠️  Unknown model '{model}', using conservative max_tokens={max_tokens}")

        return max_tokens

    async def connect_to_servers(self):
        """Connect to all configured MCP servers"""
        for server_name, server_config in self.config.mcp_servers.items():
            try:
                task = asyncio.create_task(self._run_server(server_name, server_config), name=f"mcp_{server_name}")
                self._server_tasks.append(task)

                # Wait for server initialization (up to 5 seconds)
                for _ in range(20):  # Wait up to 10 seconds
                    await asyncio.sleep(0.5)
                    if server_name in self.sessions:
                        print(
                            f"✓ Connected to {server_name} MCP server with {len([t for t in self.available_tools if t['_server'] == server_name])} tools"
                        )
                        break
                # No warning if not connected yet - it may still connect later

            except Exception as e:
                print(f"✗ Failed to connect to {server_name}: {e}")
                import traceback

                traceback.print_exc()

        # Add introspection tools for self-awareness
        introspection_tool_defs = self.introspection_tools.get_tool_definitions()
        if introspection_tool_defs:
            self.available_tools.extend(introspection_tool_defs)
            print(f"✓ Added {len(introspection_tool_defs)} introspection tools (self-awareness)")

        # Add knowledge management tools
        if self.knowledge_tools:
            knowledge_tool_defs = self.knowledge_tools.get_tool_definitions()
            if knowledge_tool_defs:
                self.available_tools.extend(knowledge_tool_defs)
                print(f"✓ Added {len(knowledge_tool_defs)} knowledge management tools")

        # Add KG query tools
        if self.kg_query_tools:
            kg_query_tool_defs = self.kg_query_tools.get_tool_definitions()
            if kg_query_tool_defs:
                self.available_tools.extend(kg_query_tool_defs)
                print(f"✓ Added {len(kg_query_tool_defs)} KG query tools")

        # Add internal report tools
        report_tool_defs = self.report_tools.get_tool_definitions()
        if report_tool_defs:
            self.available_tools.extend(report_tool_defs)
            print(f"✓ Added {len(report_tool_defs)} internal report tools")

        # Add internal schedule management tools
        schedule_tool_defs = self.schedule_tools.get_tool_definitions()
        if schedule_tool_defs:
            self.available_tools.extend(schedule_tool_defs)
            print(f"✓ Added {len(schedule_tool_defs)} schedule management tools")

        # Add internal filesystem tools
        filesystem_tool_defs = self.filesystem_tools.get_tool_definitions()
        if filesystem_tool_defs:
            self.available_tools.extend(filesystem_tool_defs)
            print(f"✓ Added {len(filesystem_tool_defs)} filesystem tools")

        # Add schedule action tools
        schedule_action_tool_defs = self.schedule_action_tools.get_tool_definitions()
        if schedule_action_tool_defs:
            self.available_tools.extend(schedule_action_tool_defs)
            print(f"✓ Added {len(schedule_action_tool_defs)} schedule action tools")

        # Add script execution tools if enabled
        script_tool_defs = self.script_execution_tools.get_tool_definitions()
        if script_tool_defs:
            self.available_tools.extend(script_tool_defs)
            print(f"✓ Added {len(script_tool_defs)} script execution tools (SECURITY: enabled)")

        # Load installed skills
        self.skills_manager.load_installed_skills()
        if self.skills_manager.installed_skills:
            print(f"✓ Loaded {len(self.skills_manager.installed_skills)} installed Agent Skills")
            self._allow_local_skill_paths()

    def _allow_local_skill_paths(self):
        """Auto-allow local skill directories for filesystem access"""
        for skill in self.skills_manager.installed_skills:
            if skill.source_type == "local":
                skill_path = Path(skill.cache_path).resolve()
                if skill_path not in self.filesystem_tools.allowed_paths:
                    self.filesystem_tools.allowed_paths.append(skill_path)

    async def _run_server(self, name: str, config: MCPServerConfig):
        """Run an MCP server connection (as a background task)"""
        try:
            server_params = StdioServerParameters(
                command=config.command,
                args=config.args,
                env=config.env if config.env else None,
            )

            # Use FIXED stdio_client with proper buffering
            async with stdio_client_fixed(server_params) as (read_stream, write_stream):
                # CRITICAL: ClientSession must be used as async context manager
                # to start the _receive_loop task that processes incoming messages!
                async with ClientSession(read_stream, write_stream) as session:
                    try:
                        await asyncio.wait_for(session.initialize(), timeout=10.0)
                    except TimeoutError:
                        print(f"⚠ Warning: {name} timed out during initialization", flush=True)
                        raise
                    except Exception as e:
                        print(f"✗ Error connecting to {name}: {e}", flush=True)
                        raise
                    self.sessions[name] = session

                    tools_list = await session.list_tools()
                    for tool in tools_list.tools:
                        desc = tool.description or ""
                        tool_def = {
                            "name": f"{name}__{tool.name}",
                            "description": desc,
                            "_full_description": desc,
                            "input_schema": tool.inputSchema,
                            "_server": name,
                            "_original_name": tool.name,
                        }
                        self.available_tools.append(tool_def)

                    # Discover prompts from this server
                    try:
                        prompts_result = await session.list_prompts()
                        if prompts_result.prompts:
                            self.available_prompts[name] = {prompt.name: prompt for prompt in prompts_result.prompts}
                    except Exception:
                        # Prompts are optional - silently skip if not supported
                        pass
                    # Keep the connection alive by waiting indefinitely
                    try:
                        await asyncio.Event().wait()
                    except asyncio.CancelledError:
                        print(f"[{name}] Connection cancelled, shutting down", flush=True)
        except Exception as e:
            print(f"[{name}] ERROR in _run_server: {e}", flush=True)
            import traceback

            traceback.print_exc()

    def _disconnect_server(self, name: str):
        """Disconnect a single MCP server, cleaning up session, tools, prompts, and task"""
        if name in self.sessions:
            self.sessions.pop(name)
        self.available_tools = [t for t in self.available_tools if t.get("_server") != name]
        if name in self.available_prompts:
            self.available_prompts.pop(name)
        for task in self._server_tasks:
            if task.get_name() == f"mcp_{name}":
                task.cancel()

    async def _connect_server(self, name: str, config) -> bool:
        """Connect a single MCP server and wait for initialization (up to 5s)"""
        task = asyncio.create_task(self._run_server(name, config), name=f"mcp_{name}")
        self._server_tasks.append(task)
        for _ in range(10):
            await asyncio.sleep(0.5)
            if name in self.sessions:
                return True
        return False

    async def restart_mcp_server(self, name: str):
        """Restart a single MCP server to pick up binary updates"""
        if name not in self.config.mcp_servers:
            raise ValueError(f"Unknown MCP server: {name}. Available: {', '.join(self.config.mcp_servers.keys())}")
        self._disconnect_server(name)
        connected = await self._connect_server(name, self.config.mcp_servers[name])
        if connected:
            tool_count = len([t for t in self.available_tools if t.get("_server") == name])
            print(f"  ✓ Reconnected {name} with {tool_count} tools")
        else:
            print(f"  ⚠ {name} did not initialize within timeout")

    async def reload_mcp_servers(self):
        """Reload MCP server configuration and reconnect changed servers

        This method:
        1. Loads the latest mcp_servers.yaml configuration
        2. Disconnects servers that were removed
        3. Connects new servers
        4. Reconnects servers with modified configuration
        """
        from .config import get_config_dir, load_mcp_servers_from_yaml

        print("\n🔄 Reloading MCP server configuration...")

        # Load new configuration
        mcp_file = get_config_dir() / "mcp_servers.yaml"
        new_servers = load_mcp_servers_from_yaml(mcp_file)

        old_names = set(self.config.mcp_servers.keys())
        new_names = set(new_servers.keys())

        # Remove deleted servers
        removed = old_names - new_names
        for name in removed:
            print(f"  Disconnecting {name}...")
            self._disconnect_server(name)

        # Add new servers
        added = new_names - old_names
        for name in added:
            print(f"  Connecting {name}...")
            connected = await self._connect_server(name, new_servers[name])
            if connected:
                tool_count = len([t for t in self.available_tools if t.get("_server") == name])
                print(f"    ✓ Connected with {tool_count} tools")

        # Reconnect modified servers (simple: disconnect + connect)
        common = old_names & new_names
        for name in common:
            # Compare configurations (convert to dict for comparison)
            old_config = self.config.mcp_servers[name].model_dump()
            new_config = new_servers[name].model_dump()

            if old_config != new_config:
                print(f"  Reconnecting {name} (config changed)...")
                self._disconnect_server(name)
                connected = await self._connect_server(name, new_servers[name])
                if connected:
                    tool_count = len([t for t in self.available_tools if t.get("_server") == name])
                    print(f"    ✓ Reconnected with {tool_count} tools")

        # Update config
        self.config.mcp_servers = new_servers

        print("✅ MCP server reload complete\n")

    @staticmethod
    def _truncate_description(description: str, max_length: int = 200) -> str:
        """Truncate tool description to first sentence for progressive disclosure.

        Args:
            description: Full tool description
            max_length: Maximum length before truncation kicks in

        Returns:
            Truncated description (first sentence or paragraph)
        """
        if not description or len(description) <= max_length:
            return description

        # Try sentence boundaries in order of preference
        for sep in [". ", ".\n", "\n\n", "\n"]:
            idx = description.find(sep)
            if 0 < idx <= max_length:
                # Include the period if boundary is ". " or ".\n"
                end = idx + 1 if sep.startswith(".") else idx
                return description[:end]

        # Fallback: truncate at max_length on word boundary
        truncated = description[:max_length]
        last_space = truncated.rfind(" ")
        if last_space > 0:
            truncated = truncated[:last_space]
        return truncated + "..."

    def _build_api_tools(self) -> list[dict]:
        """Build tool definitions for the Claude API with progressive disclosure.

        Long MCP tool descriptions are truncated to save context tokens.
        The model can call introspection__get_tool_help to get full documentation.

        Returns:
            List of tool dicts with name, description, input_schema
        """
        api_tools = []
        for tool in self.available_tools:
            desc = tool["description"]
            full_desc = tool.get("_full_description")

            # Truncate if tool has a full description and it's long
            if full_desc and len(full_desc) > 200:
                desc = (
                    self._truncate_description(full_desc) + " Use introspection__get_tool_help for full documentation."
                )

            api_tools.append(
                {
                    "name": tool["name"],
                    "description": desc,
                    "input_schema": tool["input_schema"],
                }
            )
        return api_tools

    def get_context_window_size(self) -> int:
        """Get context window size for the current model.

        Returns 1M if extended context is currently active, otherwise the
        standard context window for the model.

        Returns:
            Context window size in tokens
        """
        if self._extended_context_active:
            return self.EXTENDED_CONTEXT_WINDOW
        model = self.config.model
        # Try exact match first, then prefix match
        for key, size in self.MODEL_CONTEXT_WINDOWS.items():
            if key in model:
                return size
        return 200000  # Default for unknown models

    def _supports_extended_context(self) -> bool:
        """Check if extended context is allowed and the model supports it."""
        if not self.config.allow_extended_context:
            return False
        model = self.config.model.lower()
        return any(m in model for m in self.EXTENDED_CONTEXT_MODELS)

    def _needs_extended_context(self) -> bool:
        """Check if token usage warrants activating extended context.

        Returns True when input_tokens in the last turn exceed the activation
        threshold (75% of the standard 200K window).
        """
        if not self._supports_extended_context():
            return False
        if not self._turn_token_usage:
            return False
        last_input = self._turn_token_usage[-1]["input_tokens"]
        standard_window = 200000
        return last_input > standard_window * self.EXTENDED_CONTEXT_ACTIVATION_THRESHOLD

    def _get_extra_headers(self) -> dict[str, str] | None:
        """Get extra headers for API calls, including the 1M beta header if needed."""
        if self._extended_context_active:
            return {"anthropic-beta": self.EXTENDED_CONTEXT_BETA_HEADER}
        return None

    def _track_token_usage(self, response, turn: int):
        """Record token usage from an API response.

        Args:
            response: API response with usage field
            turn: Current turn number (0-indexed)
        """
        import logging

        if not hasattr(response, "usage"):
            return

        usage = response.usage
        entry = {
            "turn": turn,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
        }

        # Track cache metrics if available
        if hasattr(usage, "cache_creation_input_tokens"):
            entry["cache_creation_input_tokens"] = usage.cache_creation_input_tokens
        if hasattr(usage, "cache_read_input_tokens"):
            entry["cache_read_input_tokens"] = usage.cache_read_input_tokens

        self._turn_token_usage.append(entry)

        # Warn if approaching context limit
        context_window = self.get_context_window_size()
        utilization = usage.input_tokens / context_window
        if utilization >= self.CONTEXT_BUDGET_WARNING_THRESHOLD:
            logging.warning(
                "Context budget warning: using %d/%d tokens (%.0f%% of context window)",
                usage.input_tokens,
                context_window,
                utilization * 100,
            )

    def get_token_usage(self) -> list[dict[str, Any]]:
        """Get per-turn token usage from the last query.

        Returns:
            List of dicts with turn, input_tokens, output_tokens, and optional cache fields
        """
        return self._turn_token_usage.copy()

    def capture_trace(
        self,
        query_text: str,
        response_text: str,
        start_time: float,
        turn_count: int | None = None,
    ):
        """Build a QueryTrace from current agent state after a query completes.

        Call this BEFORE clear_tool_calls() so tool call data is still available.

        Args:
            query_text: The original query
            response_text: The agent's response
            start_time: Query start time (from time.time())
            turn_count: Number of turns used. If None, reads from self._last_turn_count.
        """
        if turn_count is None:
            turn_count = getattr(self, "_last_turn_count", 0)
        from .eval import QueryTrace

        # Extract tool names + args (no results) from last_tool_calls
        tool_calls = [{"tool_name": tc["tool_name"], "arguments": tc["arguments"]} for tc in self.last_tool_calls]

        # Get token usage
        token_usage = self.get_token_usage()
        total_input = sum(t.get("input_tokens", 0) for t in token_usage)
        total_output = sum(t.get("output_tokens", 0) for t in token_usage)

        return QueryTrace(
            query_text=query_text,
            timestamp=datetime.fromtimestamp(start_time).isoformat(),
            tool_calls=tool_calls,
            turn_count=turn_count,
            grounding_nudge_fired=self._grounding_nudge_fired,
            response_text=response_text,
            token_usage=token_usage,
            total_input_tokens=total_input,
            total_output_tokens=total_output,
            duration_seconds=round(time.time() - start_time, 2),
            model=self.config.model,
            tools_available_count=len(self.available_tools),
            duplicate_tool_calls=getattr(self, "_duplicate_tool_call_count", 0),
        )

    @staticmethod
    def _truncate_tool_result(result: str, max_size: int = 20000) -> str:
        """Truncate large tool results to prevent context overflow.

        Args:
            result: Tool result string
            max_size: Maximum allowed size in characters (~5K tokens at 4 chars/token)

        Returns:
            Original or truncated result
        """
        if len(result) <= max_size:
            return result
        truncated = result[:max_size]
        truncated += f"\n\n... [Result truncated: {len(result)} chars total, showing first {max_size} chars]"
        return truncated

    @staticmethod
    def _mask_old_observations(messages: list, keep_recent: int = 10) -> None:
        """Replace old tool results with compact placeholders in-place.

        Scans the message list and replaces tool result content from older turns
        with short placeholders. Keeps the most recent `keep_recent` rounds of
        tool results untouched.

        Args:
            messages: Message list (modified in-place)
            keep_recent: Number of recent tool-result rounds to preserve (default: 10)
        """
        # Find all user messages that contain tool results
        tool_result_indices = []
        for i, msg in enumerate(messages):
            if msg.get("role") == "user" and isinstance(msg.get("content"), list):
                # Check if this is a tool results message
                if any(isinstance(item, dict) and item.get("type") == "tool_result" for item in msg["content"]):
                    tool_result_indices.append(i)

        # Keep the most recent `keep_recent` rounds
        indices_to_mask = tool_result_indices[:-keep_recent] if len(tool_result_indices) > keep_recent else []

        for idx in indices_to_mask:
            content = messages[idx]["content"]
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "tool_result":
                        item["content"] = "[Result already retrieved]"

    # Threshold: only start masking when input tokens exceed 50% of context window
    OBSERVATION_MASKING_THRESHOLD = 0.5

    def _should_mask_observations(self) -> bool:
        """Check if context usage is high enough to warrant masking old tool results.

        Returns True when the last turn's input tokens exceed the masking threshold
        of the context window. This avoids premature masking that forces the agent
        to re-call tools it already called.
        """
        if not self._turn_token_usage:
            return False
        last_input = self._turn_token_usage[-1]["input_tokens"]
        context_window = self.get_context_window_size()
        return last_input > context_window * self.OBSERVATION_MASKING_THRESHOLD

    def _build_system_prompt(self) -> str:
        """Build complete system prompt including identity and skills

        Returns:
            Complete system prompt string
        """
        # Start with identity prompt
        identity_prompt = self.identity.get_system_prompt()

        # Add skills section
        skills_section = self.skills_manager.get_system_prompt_section(
            script_execution_enabled=self.script_execution_tools.enabled
        )

        prompt = identity_prompt
        if skills_section:
            prompt += f"\n\n{skills_section}"

        # Add MCP tools guidance
        mcp_servers = list(self.sessions.keys())
        if mcp_servers:
            prompt += "\n\n# Available Data Sources\n\n"
            prompt += "You have access to tools from these MCP servers: " + ", ".join(mcp_servers) + ".\n"
            prompt += "Always use tools to retrieve real data. Never fabricate information that could be obtained through a tool call.\n"
            prompt += "For detailed tool documentation (query syntax, available fields, examples), call introspection__get_tool_help with the tool name.\n"

        # Add Knowledge Graph guidance
        if self.knowledge_graph:
            prompt += "\n\n# Knowledge Graph\n\n"
            prompt += "You have a Knowledge Graph containing lessons learned, user preferences, project context, and decision rationale from previous conversations.\n"
            prompt += "Instead of guessing or making assumptions, search it with internal__search_knowledge.\n"
            prompt += "Use it when:\n"
            prompt += "- You are unsure about user preferences or conventions\n"
            prompt += "- You need context about a project, workflow, or tool\n"
            prompt += "- You want to check if a similar problem was solved before\n"
            prompt += "- You are about to recommend an approach and want to verify past decisions\n"

        # Add honesty directive with source citation requirements
        prompt += "\n\n# Honesty and Clarification\n\n"
        prompt += "Never guess or make assumptions when you are unsure. "
        prompt += "If you do not know the answer after searching available tools and knowledge, "
        prompt += "say so honestly and ask the user for clarification.\n\n"
        prompt += "## Source Citation\n\n"
        prompt += "Every factual claim about specific data (job statuses, ticket details, dates, counts, component versions, test results) "
        prompt += "MUST cite the tool call that provided it. Use inline references like: (source: search_dci_jobs) or (source: get_jira_ticket).\n"
        prompt += "If you are about to state a specific fact but cannot cite a tool that provided it, call the appropriate tool first.\n"
        prompt += "For general knowledge not from tools, prefix with: 'Based on my general knowledge: ...' to distinguish it from tool-sourced data.\n"

        return prompt

    async def query(
        self,
        prompt: str | None = None,
        messages: list[dict] | None = None,
        max_turns: int = 100,
        progress_callback=None,
    ) -> str:
        """Query the agent with a prompt or message history

        Args:
            prompt: The user's question/prompt (if no messages provided)
            messages: Full message history in Claude format (optional).
                     If provided, this is used instead of prompt.
                     Format: [{"role": "user", "content": "..."}, ...]
            max_turns: Maximum number of agentic turns (safety limit, default: 100)
            progress_callback: Optional callback function for progress updates
                              Called with (status: str, turn: int, max_turns: int, tool_name: str | None)

        Returns:
            The assistant's response text
        """
        import hashlib

        # Build messages list
        if messages is None:
            if prompt is None:
                raise ValueError("Either prompt or messages must be provided")
            messages = [{"role": "user", "content": prompt}]
        else:
            # Use provided messages
            messages = messages.copy()  # Don't modify caller's list

        # Build tools with progressive disclosure (truncated descriptions)
        api_tools = self._build_api_tools()

        # Reset token tracking and extended context for this query
        self._turn_token_usage = []
        self._extended_context_active = False

        # Loop detection and dedup tracking
        start_time = time.time()
        max_time_seconds = 600  # 10 minutes max
        recent_tool_calls = []  # Track last 5 tool calls
        max_recent_calls = 5
        loop_detection_threshold = 3  # If same call appears 3 times in recent history, it's a loop
        no_progress_count = 0  # Count turns with no text response
        max_no_progress = 10  # Allow 10 turns without text before declaring stuck
        self._grounding_nudge_fired = False
        self._wrapup_nudge_fired = False
        self._tool_result_cache: dict[str, str] = {}  # Per-query dedup cache
        self._duplicate_tool_call_count = 0
        self._last_turn_count = 0
        any_tools_called = False  # Track if any tools were called during the entire query

        if progress_callback:
            progress_callback("thinking", 0, max_turns, None)

        for turn in range(max_turns):
            # Check time-based timeout
            elapsed = time.time() - start_time
            if elapsed > max_time_seconds:
                self._last_turn_count = turn + 1
                return f"Task timeout after {int(elapsed)} seconds (max: {max_time_seconds}s)"
            if progress_callback:
                progress_callback("calling_claude", turn + 1, max_turns, None)

            # Only mask old tool results when context is getting large
            if self._should_mask_observations():
                self._mask_old_observations(messages)

            # Check if we need to activate extended context
            if not self._extended_context_active and self._needs_extended_context():
                self._extended_context_active = True
                import logging

                last_input = self._turn_token_usage[-1]["input_tokens"]
                logging.info("Activating 1M extended context (input tokens: %d/200000)", last_input)

            extra_headers = self._get_extra_headers()

            max_tokens = self.get_max_tokens()
            # Use streaming for large max_tokens to avoid HTTP timeouts
            if max_tokens > 8192:
                with self.anthropic.messages.stream(
                    model=self.config.model,
                    max_tokens=max_tokens,
                    system=self._build_system_prompt(),
                    tools=api_tools,  # type: ignore[arg-type]
                    messages=messages,  # type: ignore[arg-type]
                    extra_headers=extra_headers,
                ) as stream:
                    response = stream.get_final_message()
            else:
                response = self.anthropic.messages.create(  # type: ignore[assignment]
                    model=self.config.model,
                    max_tokens=max_tokens,
                    system=self._build_system_prompt(),
                    tools=api_tools,  # type: ignore[arg-type]
                    messages=messages,  # type: ignore[arg-type]
                    extra_headers=extra_headers,
                )

            # Track token usage
            self._track_token_usage(response, turn)

            messages.append({"role": "assistant", "content": response.content})

            tool_results: list[dict[str, Any]] = []
            for block in response.content:
                if block.type == "tool_use":
                    if progress_callback:
                        progress_callback("executing_tool", turn + 1, max_turns, block.name)

                    # Compute signature for dedup and loop detection
                    tool_signature = (
                        f"{block.name}:{hashlib.md5(json.dumps(block.input, sort_keys=True).encode()).hexdigest()[:8]}"
                    )

                    # Check per-query cache for duplicate tool call
                    if tool_signature in self._tool_result_cache:
                        result = self._tool_result_cache[tool_signature]
                        self._duplicate_tool_call_count += 1
                    else:
                        result = await self._execute_tool(block.name, block.input)
                        # Truncate large tool results to prevent context overflow
                        result = self._truncate_tool_result(result)
                        self._tool_result_cache[tool_signature] = result

                    # Check if result is an error (starts with "Error:")
                    is_error = isinstance(result, str) and result.startswith("Error:")

                    tool_result: dict[str, Any] = {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    }

                    # Mark as error if it's an error message
                    if is_error:
                        tool_result["is_error"] = True

                    tool_results.append(tool_result)

                    # Track for loop detection
                    recent_tool_calls.append(tool_signature)
                    if len(recent_tool_calls) > max_recent_calls:
                        recent_tool_calls.pop(0)

                    # Check for loops - same tool call repeated multiple times
                    if recent_tool_calls.count(tool_signature) >= loop_detection_threshold:
                        self._last_turn_count = turn + 1
                        return f"Loop detected: {block.name} called repeatedly with same arguments ({recent_tool_calls.count(tool_signature)} times)"

            if not tool_results:
                final_text = ""
                for block in response.content:
                    if hasattr(block, "text"):
                        final_text += block.text

                # Check if we got actual content
                if final_text.strip():
                    # Grounding nudge: if tools are available but none were called
                    # during the entire query, ask the model to verify (once only).
                    # Skip if tools were already used — the answer is already grounded.
                    if api_tools and not any_tools_called and not self._grounding_nudge_fired:
                        self._grounding_nudge_fired = True
                        messages.append(
                            {
                                "role": "user",
                                "content": (
                                    "Before I accept this answer: you have tools available but did not call any. "
                                    "Please verify any specific factual claims (dates, statuses, counts, versions) "
                                    "by calling the appropriate tool. If your answer is based purely on general "
                                    "knowledge and no tool is relevant, confirm that explicitly."
                                ),
                            }
                        )
                        continue

                    if progress_callback:
                        progress_callback("complete", turn + 1, max_turns, None)
                    self._last_turn_count = turn + 1
                    return final_text
                else:
                    # No text and no tool calls - agent gave up
                    no_progress_count += 1
                    if no_progress_count >= max_no_progress:
                        self._last_turn_count = turn + 1
                        return "Agent stopped responding (no progress detected)"
                    # Continue to next turn
                    continue

            # We have tool results - reset no-progress counter (agent is actively working)
            no_progress_count = 0
            any_tools_called = True

            messages.append({"role": "user", "content": tool_results})

            # Wrap-up nudge: when approaching the turn limit, ask the agent to synthesize
            if not self._wrapup_nudge_fired and turn >= int(max_turns * 0.8):
                self._wrapup_nudge_fired = True
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "You are approaching the maximum number of tool calls allowed. "
                            "Please synthesize the information you have gathered so far into "
                            "a final answer. Do not make additional tool calls unless absolutely "
                            "necessary to complete the answer."
                        ),
                    }
                )

        self._last_turn_count = max_turns
        return "Maximum turns reached without final answer"

    async def query_streaming(
        self,
        prompt: str | None = None,
        messages: list[dict] | None = None,
        max_turns: int = 100,
        progress_callback=None,
        cancel_event=None,
    ):
        """Query the agent with streaming response

        Args:
            prompt: The user's question/prompt (if no messages provided)
            messages: Full message history in Claude format (optional).
                     If provided, this is used instead of prompt.
            max_turns: Maximum number of agentic turns (safety limit, default: 100)
            progress_callback: Optional callback for progress updates
            cancel_event: Optional threading.Event; when set, streaming is cancelled

        Yields:
            str: Text chunks as they arrive
            dict: Tool call information {"type": "tool_use", "name": str, "id": str, "input": dict}
            dict: Final result {"type": "done", "turns": int}
            dict: Cancellation signal {"type": "cancelled"}
        """
        import hashlib
        import json

        # Build messages list
        if messages is None:
            if prompt is None:
                raise ValueError("Either prompt or messages must be provided")
            messages = [{"role": "user", "content": prompt}]
        else:
            # Use provided messages
            messages = messages.copy()  # Don't modify caller's list

        # Store cancel_event on instance so execute_mcp_prompt can forward it
        if cancel_event is not None:
            self._cancel_event = cancel_event

        # Loop detection and dedup tracking (same as query())
        recent_tool_calls = []
        max_recent_calls = 5
        loop_detection_threshold = 3
        self._tool_result_cache = {}
        self._duplicate_tool_call_count = 0
        self._last_turn_count = 0
        any_tools_called = False

        # Build tools with progressive disclosure (truncated descriptions)
        api_tools = self._build_api_tools()

        # Reset token tracking and extended context for this query
        self._turn_token_usage = []
        self._extended_context_active = False
        self._grounding_nudge_fired = False
        self._wrapup_nudge_fired = False

        if progress_callback:
            progress_callback("thinking", 0, max_turns, None)

        for turn in range(max_turns):
            # Check cancellation before each turn
            if cancel_event and cancel_event.is_set():
                self._last_turn_count = turn
                yield {"type": "cancelled"}
                return

            if progress_callback:
                progress_callback("calling_claude", turn + 1, max_turns, None)

            # Only mask old tool results when context is getting large
            if self._should_mask_observations():
                self._mask_old_observations(messages)

            # Check if we need to activate extended context
            if not self._extended_context_active and self._needs_extended_context():
                self._extended_context_active = True
                import logging

                last_input = self._turn_token_usage[-1]["input_tokens"]
                logging.info("Activating 1M extended context (input tokens: %d/200000)", last_input)

            extra_headers = self._get_extra_headers()

            # Use streaming API
            with self.anthropic.messages.stream(
                model=self.config.model,
                max_tokens=self.get_max_tokens(),
                system=self._build_system_prompt(),
                tools=api_tools,  # type: ignore[arg-type]
                messages=messages,  # type: ignore[arg-type]
                extra_headers=extra_headers,
            ) as stream:
                # Track content blocks
                current_text = ""

                for event in stream:
                    # Check cancellation during streaming
                    if cancel_event and cancel_event.is_set():
                        self._last_turn_count = turn + 1
                        yield {"type": "cancelled"}
                        return

                    # Content block delta - streaming text
                    if event.type == "content_block_delta":
                        if hasattr(event.delta, "text"):
                            chunk = event.delta.text
                            current_text += chunk
                            yield chunk  # Stream text to user

                    # Content block start - tool use
                    elif event.type == "content_block_start":
                        if hasattr(event.content_block, "type") and event.content_block.type == "tool_use":
                            # Just track that we're starting a tool use
                            # We'll yield the notification with full input later
                            pass

                    # Input JSON delta for tool
                    elif event.type == "content_block_delta":
                        if hasattr(event.delta, "partial_json"):
                            # Tool input is being streamed
                            pass  # We'll get the full input later

                # Get final message from stream
                final_message = stream.get_final_message()

                # Track token usage
                self._track_token_usage(final_message, turn)

                messages.append({"role": "assistant", "content": final_message.content})

                # Yield tool use notifications with complete inputs
                for block in final_message.content:
                    if block.type == "tool_use":
                        yield {"type": "tool_use", "name": block.name, "id": block.id, "input": block.input}

                # Execute any tools
                tool_results: list[dict[str, Any]] = []
                for block in final_message.content:
                    if block.type == "tool_use":
                        # Check cancellation before each tool execution
                        if cancel_event and cancel_event.is_set():
                            self._last_turn_count = turn + 1
                            yield {"type": "cancelled"}
                            return

                        if progress_callback:
                            progress_callback("executing_tool", turn + 1, max_turns, block.name)

                        # Compute signature for dedup and loop detection
                        tool_signature = f"{block.name}:{hashlib.md5(json.dumps(block.input, sort_keys=True).encode()).hexdigest()[:8]}"

                        # Check per-query cache for duplicate tool call
                        if tool_signature in self._tool_result_cache:
                            result = self._tool_result_cache[tool_signature]
                            self._duplicate_tool_call_count += 1
                        else:
                            result = await self._execute_tool(block.name, block.input)
                            # Truncate large tool results to prevent context overflow
                            result = self._truncate_tool_result(result)
                            self._tool_result_cache[tool_signature] = result

                        # Check if result is an error
                        is_error = isinstance(result, str) and result.startswith("Error:")

                        tool_result: dict[str, Any] = {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        }

                        # Mark as error if it's an error message
                        if is_error:
                            tool_result["is_error"] = True

                        tool_results.append(tool_result)

                        # Track for loop detection
                        recent_tool_calls.append(tool_signature)
                        if len(recent_tool_calls) > max_recent_calls:
                            recent_tool_calls.pop(0)

                        # Check for loops
                        if recent_tool_calls.count(tool_signature) >= loop_detection_threshold:
                            self._last_turn_count = turn + 1
                            yield {
                                "type": "error",
                                "message": f"Loop detected: {block.name} called repeatedly with same arguments ({recent_tool_calls.count(tool_signature)} times)",
                            }
                            return

                # If no tool calls, check for grounding nudge
                if not tool_results:
                    # Grounding nudge: if tools are available but none were called
                    # during the entire query, ask the model to verify (once only).
                    # Skip if tools were already used — the answer is already grounded.
                    if api_tools and not any_tools_called and not self._grounding_nudge_fired and current_text.strip():
                        self._grounding_nudge_fired = True
                        messages.append(
                            {
                                "role": "user",
                                "content": (
                                    "Before I accept this answer: you have tools available but did not call any. "
                                    "Please verify any specific factual claims (dates, statuses, counts, versions) "
                                    "by calling the appropriate tool. If your answer is based purely on general "
                                    "knowledge and no tool is relevant, confirm that explicitly."
                                ),
                            }
                        )
                        continue

                    if progress_callback:
                        progress_callback("complete", turn + 1, max_turns, None)

                    self._last_turn_count = turn + 1
                    yield {"type": "done", "turns": turn + 1}
                    return

                # Continue with tool results
                any_tools_called = True
                messages.append({"role": "user", "content": tool_results})

                # Wrap-up nudge: when approaching the turn limit, ask the agent to synthesize
                if not self._wrapup_nudge_fired and turn >= int(max_turns * 0.8):
                    self._wrapup_nudge_fired = True
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "You are approaching the maximum number of tool calls allowed. "
                                "Please synthesize the information you have gathered so far into "
                                "a final answer. Do not make additional tool calls unless absolutely "
                                "necessary to complete the answer."
                            ),
                        }
                    )

        # Max turns reached
        self._last_turn_count = max_turns
        yield {"type": "error", "message": "Maximum turns reached without final answer"}

    async def execute_mcp_prompt(
        self, server_name: str, prompt_name: str, arguments: dict[str, Any] | None = None, max_turns: int = 100
    ) -> str:
        """Execute an MCP prompt by retrieving it from the server and feeding it to Claude

        Args:
            server_name: MCP server name
            prompt_name: Name of prompt to execute
            arguments: Arguments to pass to prompt
            max_turns: Maximum agentic turns

        Returns:
            Claude's response after executing the prompt instructions

        Raises:
            ValueError: If server/prompt not found or arguments invalid
        """
        # Validate server exists
        if server_name not in self.sessions:
            available = ", ".join(self.sessions.keys())
            raise ValueError(f"MCP server '{server_name}' not connected. " f"Available servers: {available}")

        # Validate server has prompts
        if server_name not in self.available_prompts:
            raise ValueError(f"Server '{server_name}' has no prompts")

        # Validate prompt exists
        if prompt_name not in self.available_prompts[server_name]:
            available = ", ".join(self.available_prompts[server_name].keys())
            raise ValueError(
                f"Prompt '{prompt_name}' not found in server '{server_name}'. " f"Available prompts: {available}"
            )

        # Get prompt definition
        prompt_def = self.available_prompts[server_name][prompt_name]

        # Validate arguments
        if hasattr(prompt_def, "arguments") and prompt_def.arguments:
            self._validate_prompt_arguments(prompt_def, arguments or {})

        # Retrieve prompt from MCP server
        session = self.sessions[server_name]
        result = await session.get_prompt(prompt_name, arguments=arguments)

        # Convert MCP prompt messages to Claude API format
        messages = []
        for msg in result.messages:
            if hasattr(msg.content, "text"):
                content = msg.content.text
            else:
                content = str(msg.content)
            messages.append({"role": msg.role, "content": content})

        # Feed the prompt to Claude for execution (with tools available)
        # Use streaming to allow inner execution visibility via callback
        # Forward active cancel_event so Escape works during inner execution
        full_response = ""
        async for chunk in self.query_streaming(
            messages=messages, max_turns=max_turns, cancel_event=self._cancel_event
        ):
            if isinstance(chunk, str):
                full_response += chunk
                if self.on_inner_execution:
                    self.on_inner_execution(chunk)
            elif isinstance(chunk, dict):
                if chunk.get("type") == "tool_use" and self.on_inner_execution:
                    self.on_inner_execution(chunk)
                elif chunk.get("type") in ("error", "cancelled"):
                    if self.on_inner_execution:
                        self.on_inner_execution(chunk)
                    break
                elif chunk.get("type") == "done":
                    break
        return full_response

    def _validate_prompt_arguments(self, prompt_def, arguments: dict):
        """Validate arguments against prompt definition

        Raises:
            ValueError: If required arguments missing
        """
        provided_args = set(arguments.keys())

        for arg in prompt_def.arguments:
            if arg.required and arg.name not in provided_args:
                raise ValueError(f"Required argument '{arg.name}' missing. " f"Description: {arg.description}")

    def _validate_tool_arguments(self, tool_name: str, arguments: dict) -> str | None:
        """Validate tool arguments against the tool's schema

        Args:
            tool_name: Full tool name (e.g., "internal__write_report")
            arguments: Arguments provided by the agent

        Returns:
            Error message if validation fails, None if validation passes
        """
        # Find the tool definition
        tool_def = None
        for tool in self.available_tools:
            if tool["name"] == tool_name:
                tool_def = tool
                break

        if not tool_def:
            return None  # Tool not found, will be handled later

        # Get the input schema
        schema = tool_def.get("input_schema", {})
        required_params = schema.get("required", [])
        properties = schema.get("properties", {})

        # Check for missing required parameters
        missing_params = [param for param in required_params if param not in arguments]

        if missing_params:
            # Build simple, direct error message
            error_lines = [f"Error: Missing required parameter(s): {', '.join(missing_params)}"]
            error_lines.append("")
            error_lines.append("Required parameters:")
            for param in required_params:
                param_info = properties.get(param, {})
                param_desc = param_info.get("description", "No description")
                param_type = param_info.get("type", "unknown")
                error_lines.append(f"  - {param} ({param_type}): {param_desc}")

            error_lines.append("")
            error_lines.append("You provided:")
            if arguments:
                for key, value in arguments.items():
                    value_preview = str(value)[:100]
                    if len(str(value)) > 100:
                        value_preview += "..."
                    error_lines.append(f"  - {key}: {value_preview}")
            else:
                error_lines.append("  (no arguments)")

            return "\n".join(error_lines)

        # Check for empty required string parameters
        for param in required_params:
            if param in arguments:
                value = arguments[param]
                param_type = properties.get(param, {}).get("type")
                if param_type == "string" and (not value or not str(value).strip()):
                    param_desc = properties.get(param, {}).get("description", "")
                    return (
                        f"Error: Required parameter '{param}' cannot be empty.\n\n"
                        f"Description: {param_desc}\n\n"
                        f"Please provide a non-empty value for '{param}'."
                    )

        return None  # Validation passed

    async def _execute_tool(self, tool_name: str, arguments: dict) -> str:
        """Execute a tool call on the appropriate MCP server, introspection, or internal tool"""

        # Validate arguments against tool schema before execution
        validation_error = self._validate_tool_arguments(tool_name, arguments)
        if validation_error:
            print(f"⚠️  VALIDATION ERROR for {tool_name}: {validation_error[:150]}...")
            return validation_error

        parts = tool_name.split("__", 1)
        if len(parts) != 2:
            return f"Error: Invalid tool name format: {tool_name}"

        server_name, original_tool_name = parts

        # Handle introspection tools (self-awareness)
        if server_name == "introspection":
            try:
                result_text = await self.introspection_tools.execute_tool(original_tool_name, arguments)

                # Track introspection tool call
                self.last_tool_calls.append(
                    {
                        "tool_name": tool_name,
                        "server_name": server_name,
                        "original_tool_name": original_tool_name,
                        "arguments": arguments,
                        "result": result_text,
                        "timestamp": datetime.now(),
                    }
                )

                self.audit_logger.log_tool_call(tool_name, arguments, result_text, success=True)

                return result_text
            except Exception as e:
                error_msg = f"Error executing introspection tool {original_tool_name}: {str(e)}"
                self.audit_logger.log_tool_call(tool_name, arguments, error_msg, success=False)
                return error_msg

        # Handle internal tools (report management, schedule management, filesystem, etc.)
        if server_name == "internal":
            try:
                # Route to appropriate internal tool handler
                schedule_tools = [
                    "create_monitor",
                    "create_task",
                    "list_schedules",
                    "update_schedule",
                    "delete_schedule",
                    "enable_schedule",
                    "get_schedule_status",
                ]

                filesystem_tools = [
                    "read_file",
                    "search_in_file",
                    "create_directory",
                    "list_directory",
                    "execute_command",
                    "get_today_date",
                    "get_current_time",
                ]

                script_tools = ["execute_skill_script"]
                schedule_action_tools = ["schedule_action"]
                knowledge_tools = ["save_knowledge", "search_knowledge", "trigger_synthesis"]
                kg_query_tool_names = [
                    "kg_recent_changes",
                    "kg_late_discoveries",
                    "kg_discovery_lag_stats",
                    "kg_entity_context",
                    "kg_stats",
                ]

                if original_tool_name in schedule_tools:
                    result_text = await self.schedule_tools.execute_tool(original_tool_name, arguments)
                elif original_tool_name in filesystem_tools:
                    result_text = await self.filesystem_tools.execute_tool(original_tool_name, arguments)
                elif original_tool_name in script_tools:
                    result_text = await self.script_execution_tools.execute_tool(original_tool_name, arguments)
                elif original_tool_name in schedule_action_tools:
                    result_text = await self.schedule_action_tools.execute_tool(
                        f"internal__{original_tool_name}", arguments
                    )
                elif original_tool_name in knowledge_tools:
                    if self.knowledge_tools:
                        result_text = await self.knowledge_tools.execute_tool(original_tool_name, arguments)
                    else:
                        result_text = "Error: Knowledge tools not available (knowledge graph disabled)"
                elif original_tool_name in kg_query_tool_names:
                    if self.kg_query_tools:
                        result_text = await self.kg_query_tools.execute_tool(original_tool_name, arguments)
                    else:
                        result_text = "Error: KG query tools not available (knowledge graph disabled)"
                else:
                    # Default to report tools
                    result_text = await self.report_tools.execute_tool(original_tool_name, arguments)

                # Track internal tool call
                self.last_tool_calls.append(
                    {
                        "tool_name": tool_name,
                        "server_name": server_name,
                        "original_tool_name": original_tool_name,
                        "arguments": arguments,
                        "result": result_text,
                        "timestamp": datetime.now(),
                    }
                )

                is_success = not (isinstance(result_text, str) and result_text.startswith("Error:"))
                self.audit_logger.log_tool_call(tool_name, arguments, result_text, success=is_success)

                return result_text
            except Exception as e:
                error_msg = f"Error executing internal tool {original_tool_name}: {str(e)}"
                self.audit_logger.log_tool_call(tool_name, arguments, error_msg, success=False)
                return error_msg

        # Handle regular MCP server tools
        if server_name not in self.sessions:
            return f"Error: Server {server_name} not connected"

        session = self.sessions[server_name]

        try:
            result = await session.call_tool(original_tool_name, arguments)

            result_text = ""
            if result.content:
                result_text = "\n".join([item.text if hasattr(item, "text") else str(item) for item in result.content])
            else:
                result_text = "Tool executed successfully with no output"

            # Store tool call for potential KG storage
            self.last_tool_calls.append(
                {
                    "tool_name": tool_name,
                    "server_name": server_name,
                    "original_tool_name": original_tool_name,
                    "arguments": arguments,
                    "result": result_text,
                    "timestamp": datetime.now(),
                }
            )

            # Optionally save to knowledge graph
            if self.knowledge_graph and self.kg_save_enabled:
                await self._save_tool_result_to_kg(tool_name, original_tool_name, arguments, result_text)

            self.audit_logger.log_tool_call(tool_name, arguments, result_text, success=True)

            return result_text
        except Exception as e:
            error_msg = f"Error executing tool {original_tool_name}: {str(e)}"
            self.audit_logger.log_tool_call(tool_name, arguments, error_msg, success=False)
            return error_msg

    async def _save_tool_result_to_kg(self, tool_name: str, original_tool_name: str, arguments: dict, result_text: str):
        """Save tool result to knowledge graph as a generic tool_result entity.

        Stores the tool name (without MCP prefix), arguments, and parsed JSON result.
        Large results (>10000 chars) are stored without the result blob to keep the KG manageable.
        """
        if not self.kg_save_enabled or not self.knowledge_graph:
            return

        if not result_text or result_text.startswith("Error:"):
            return

        try:
            data = json.loads(result_text)
        except json.JSONDecodeError:
            return

        try:
            import hashlib

            entity_id = (
                f"{original_tool_name}:"
                f"{hashlib.md5(json.dumps(arguments, sort_keys=True).encode()).hexdigest()[:8]}"
            )
            stored_data = {
                "tool_name": original_tool_name,
                "arguments": arguments,
                "result": data if len(result_text) <= 10000 else None,
            }
            tx_time = datetime.now()
            kg = self.knowledge_graph

            def _do_write():
                try:
                    kg.upsert_entity(
                        entity_type="tool_result",
                        entity_id=entity_id,
                        data=stored_data,
                        valid_from=tx_time,
                        tx_from=tx_time,
                    )
                    return 1
                except Exception:
                    return 0

            saved = await asyncio.to_thread(_do_write)
            if saved and self.last_tool_calls:
                self.last_tool_calls[-1]["kg_saved_count"] = self.last_tool_calls[-1].get("kg_saved_count", 0) + saved
        except Exception:
            pass  # Best-effort

    def get_last_kg_saved_count(self) -> int:
        """Get the number of entities saved to KG in the last tool calls"""
        total = 0
        for call in self.last_tool_calls:
            total += call.get("kg_saved_count", 0)
        return total

    def clear_tool_calls(self):
        """Clear tracked tool calls"""
        self.last_tool_calls = []

    async def _run_synthesis(self, conversation_memory: "ConversationMemory", focus: str = "all"):
        """Agent reflects on conversation and extracts learnings

        Args:
            conversation_memory: Conversation to analyze
            focus: What to focus on (all, preferences, lessons, context)
        """
        if not self.knowledge_graph or not self.knowledge_tools:
            return

        history_parts = []
        for ex in conversation_memory.exchanges:
            history_parts.append(f"User: {ex['user']}")
            history_parts.append(f"Assistant: {ex['assistant']}")
        history_text = "\n\n".join(history_parts)

        synthesis_prompt = SYNTHESIS_PROMPT_TEMPLATE.format(
            focus=focus if focus != "all" else "everything",
            history_text=history_text,
        )

        try:
            response = self.anthropic.messages.create(
                model=self.config.model,
                max_tokens=2000,
                messages=[{"role": "user", "content": synthesis_prompt}],
            )

            first_block = response.content[0]
            response_text = first_block.text.strip() if hasattr(first_block, "text") else ""

            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]

            insights_data = json.loads(response_text)
            insights = insights_data.get("insights", [])

            if not insights:
                print("💭 Synthesis complete - no new learnings to save")
                return

            saved_count = 0
            for insight in insights:
                try:
                    self.knowledge_graph.insert_knowledge(
                        entity_type=insight["category"],
                        key=insight["key"],
                        content=insight["content"],
                        metadata={
                            "tags": insight.get("tags", []),
                            "source": "auto_synthesis",
                            "synthesized_at": datetime.now().isoformat(),
                        },
                        confidence=insight.get("confidence", 1.0),
                    )
                    saved_count += 1

                    print(f"💡 Learned: {insight['category']}:{insight['key']}")

                except Exception as e:
                    print(f"⚠️  Failed to save insight {insight.get('key')}: {e}")

            print(f"✓ Saved {saved_count} new learnings to knowledge base")

        except json.JSONDecodeError as e:
            print(f"⚠️  Synthesis failed - invalid JSON: {e}")
        except Exception as e:
            print(f"⚠️  Synthesis failed: {e}")

    async def _run_synthesis_from_kg(self, hours: int = 24) -> str:
        """Review recent conversation entities from KG and extract knowledge

        Args:
            hours: How many hours back to look for conversations

        Returns:
            Summary of synthesis results
        """
        if not self.knowledge_graph or not self.knowledge_tools:
            return "Knowledge graph not available"

        now = datetime.now()
        cutoff = now - timedelta(hours=hours)

        # Check for synthesis marker to avoid re-processing
        markers = self.knowledge_graph.query_as_of(now, entity_type="synthesis_marker", limit=1)
        if markers:
            last_synthesis = markers[0].valid_from
            if last_synthesis > cutoff:
                cutoff = last_synthesis

        # Get conversation entities since cutoff
        conversations = self.knowledge_graph.query_as_of(now, entity_type="conversation", valid_from_after=cutoff)

        if not conversations:
            print("💭 No new conversations to synthesize")
            return "No new conversations to synthesize"

        # Build conversation text
        history_parts = []
        for conv in conversations:
            data = conv.data
            history_parts.append(f"User: {data.get('user', '')}")
            history_parts.append(f"Assistant: {data.get('assistant', '')}")
        history_text = "\n\n".join(history_parts)

        synthesis_prompt = SYNTHESIS_PROMPT_TEMPLATE.format(
            focus="everything",
            history_text=history_text,
        )

        try:
            response = self.anthropic.messages.create(
                model=self.config.model,
                max_tokens=2000,
                messages=[{"role": "user", "content": synthesis_prompt}],
            )

            first_block = response.content[0]
            response_text = first_block.text.strip() if hasattr(first_block, "text") else ""

            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]

            insights_data = json.loads(response_text)
            insights = insights_data.get("insights", [])

            if not insights:
                print("💭 Synthesis complete - no new learnings to save")
                # Still record the marker so we don't re-process
                self.knowledge_graph.insert_entity(
                    entity_type="synthesis_marker",
                    data={"synthesized_conversations": len(conversations)},
                    valid_from=now,
                )
                return "Synthesis complete - no new learnings"

            saved_count = 0
            for insight in insights:
                try:
                    self.knowledge_graph.insert_knowledge(
                        entity_type=insight["category"],
                        key=insight["key"],
                        content=insight["content"],
                        metadata={
                            "tags": insight.get("tags", []),
                            "source": "auto_synthesis",
                            "synthesized_at": now.isoformat(),
                        },
                        confidence=insight.get("confidence", 1.0),
                    )
                    saved_count += 1
                    print(f"💡 Learned: {insight['category']}:{insight['key']}")
                except Exception as e:
                    print(f"⚠️  Failed to save insight {insight.get('key')}: {e}")

            # Record synthesis marker
            self.knowledge_graph.insert_entity(
                entity_type="synthesis_marker",
                data={"synthesized_conversations": len(conversations), "insights_saved": saved_count},
                valid_from=now,
            )

            summary = f"Saved {saved_count} new learnings from {len(conversations)} conversations"
            print(f"✓ {summary}")
            return summary

        except json.JSONDecodeError as e:
            print(f"⚠️  Synthesis failed - invalid JSON: {e}")
            return f"Synthesis failed - invalid JSON: {e}"
        except Exception as e:
            print(f"⚠️  Synthesis failed: {e}")
            return f"Synthesis failed: {e}"

    async def check_and_run_synthesis(self, conversation_memory: "ConversationMemory"):
        """Check if synthesis was triggered and run it

        Args:
            conversation_memory: Current conversation
        """
        if self._pending_synthesis:
            focus = self._pending_synthesis.get("focus", "all")
            self._pending_synthesis = None

            await self._run_synthesis(conversation_memory, focus)

    def set_conversation_memory(self, conversation_memory: Optional["ConversationMemory"]):
        """Set conversation memory for introspection tools

        Args:
            conversation_memory: ConversationMemory instance to enable conversation search
        """
        self.introspection_tools.conversation_memory = conversation_memory

    async def close(self):
        """Close all MCP server connections"""
        for task in self._server_tasks:
            task.cancel()

        if self._server_tasks:
            await asyncio.gather(*self._server_tasks, return_exceptions=True)

        self._server_tasks.clear()
        self.sessions.clear()
        print("Closed all connections")
