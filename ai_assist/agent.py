"""MCP Agent for ai-assist"""

import asyncio
import json
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from anthropic import Anthropic, AnthropicVertex
from mcp import ClientSession, StdioServerParameters

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


class AiAssistAgent:
    """AI Agent with MCP capabilities"""

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
        self.filesystem_tools = FilesystemTools()

        # Initialize schedule action tools (one-shot future actions)
        from ai_assist.schedule_action_tools import ScheduleActionTools

        self.schedule_action_tools = ScheduleActionTools(self)

        # Initialize skills system
        self.skills_loader = SkillsLoader()
        self.skills_manager = SkillsManager(self.skills_loader)

        # Initialize script execution tools for Agent Skills
        self.script_execution_tools = ScriptExecutionTools(self.skills_manager, config)

        if config.use_vertex:
            vertex_kwargs = {"project_id": config.vertex_project_id}
            if config.vertex_region:
                vertex_kwargs["region"] = config.vertex_region
                print(f"Using Vertex AI: project={config.vertex_project_id}, region={config.vertex_region}")
            else:
                print(f"Using Vertex AI: project={config.vertex_project_id} (default region)")

            self.anthropic = AnthropicVertex(**vertex_kwargs)
        else:
            self.anthropic = Anthropic(api_key=config.anthropic_api_key)

        self.sessions: dict[str, ClientSession] = {}
        self.available_tools: list[dict] = []
        self.available_prompts: dict[str, dict] = {}  # {server_name: {prompt_name: Prompt}}
        self._server_tasks: list[asyncio.Task] = []

        # Track tool calls for KG storage
        self.last_tool_calls: list[dict] = []

        # Update introspection tools with reference to available_prompts and agent
        # (will be populated during server connection)
        self.introspection_tools.available_prompts = self.available_prompts
        self.introspection_tools.agent = self  # Allow introspection tools to execute prompts

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
                        tool_def = {
                            "name": f"{name}__{tool.name}",
                            "description": tool.description or "",
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

            # Remove session
            if name in self.sessions:
                self.sessions.pop(name)

            # Remove tools from this server
            self.available_tools = [t for t in self.available_tools if t.get("_server") != name]

            # Remove prompts from this server
            if name in self.available_prompts:
                self.available_prompts.pop(name)

            # Cancel server task
            for task in self._server_tasks:
                if task.get_name() == f"mcp_{name}":
                    task.cancel()

        # Add new servers
        added = new_names - old_names
        for name in added:
            print(f"  Connecting {name}...")
            task = asyncio.create_task(self._run_server(name, new_servers[name]), name=f"mcp_{name}")
            self._server_tasks.append(task)

            # Wait briefly for server initialization
            for _ in range(10):
                await asyncio.sleep(0.5)
                if name in self.sessions:
                    tool_count = len([t for t in self.available_tools if t.get("_server") == name])
                    print(f"    ✓ Connected with {tool_count} tools")
                    break

        # Reconnect modified servers (simple: disconnect + connect)
        common = old_names & new_names
        for name in common:
            # Compare configurations (convert to dict for comparison)
            old_config = self.config.mcp_servers[name].model_dump()
            new_config = new_servers[name].model_dump()

            if old_config != new_config:
                print(f"  Reconnecting {name} (config changed)...")

                # Disconnect
                if name in self.sessions:
                    self.sessions.pop(name)
                self.available_tools = [t for t in self.available_tools if t.get("_server") != name]
                if name in self.available_prompts:
                    self.available_prompts.pop(name)

                # Cancel task
                for task in self._server_tasks:
                    if task.get_name() == f"mcp_{name}":
                        task.cancel()

                # Reconnect
                task = asyncio.create_task(self._run_server(name, new_servers[name]), name=f"mcp_{name}")
                self._server_tasks.append(task)

                # Wait briefly for server initialization
                for _ in range(10):
                    await asyncio.sleep(0.5)
                    if name in self.sessions:
                        tool_count = len([t for t in self.available_tools if t.get("_server") == name])
                        print(f"    ✓ Reconnected with {tool_count} tools")
                        break

        # Update config
        self.config.mcp_servers = new_servers

        print("✅ MCP server reload complete\n")

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

        if skills_section:
            return f"{identity_prompt}\n\n{skills_section}"
        else:
            return identity_prompt

    async def query(
        self, prompt: str = None, messages: list[dict] = None, max_turns: int = 50, progress_callback=None
    ) -> str:
        """Query the agent with a prompt or message history

        Args:
            prompt: The user's question/prompt (if no messages provided)
            messages: Full message history in Claude format (optional).
                     If provided, this is used instead of prompt.
                     Format: [{"role": "user", "content": "..."}, ...]
            max_turns: Maximum number of agentic turns
            progress_callback: Optional callback function for progress updates
                              Called with (status: str, turn: int, max_turns: int, tool_name: str | None)

        Returns:
            The assistant's response text
        """
        # Build messages list
        if messages is None:
            if prompt is None:
                raise ValueError("Either prompt or messages must be provided")
            messages = [{"role": "user", "content": prompt}]
        else:
            # Use provided messages
            messages = messages.copy()  # Don't modify caller's list

        # Filter out custom internal fields from tools before sending to API
        api_tools = [
            {
                "name": tool["name"],
                "description": tool["description"],
                "input_schema": tool["input_schema"],
            }
            for tool in self.available_tools
        ]

        if progress_callback:
            progress_callback("thinking", 0, max_turns, None)

        for turn in range(max_turns):
            if progress_callback:
                progress_callback("calling_claude", turn + 1, max_turns, None)

            response = self.anthropic.messages.create(
                model=self.config.model,
                max_tokens=4096,
                system=self._build_system_prompt(),
                tools=api_tools,
                messages=messages,
            )

            messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    if progress_callback:
                        progress_callback("executing_tool", turn + 1, max_turns, block.name)

                    result = await self._execute_tool(block.name, block.input)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        }
                    )

            if not tool_results:
                if progress_callback:
                    progress_callback("complete", turn + 1, max_turns, None)

                final_text = ""
                for block in response.content:
                    if hasattr(block, "text"):
                        final_text += block.text
                return final_text

            messages.append({"role": "user", "content": tool_results})

        return "Maximum turns reached without final answer"

    async def query_streaming(
        self, prompt: str = None, messages: list[dict] = None, max_turns: int = 50, progress_callback=None
    ):
        """Query the agent with streaming response

        Args:
            prompt: The user's question/prompt (if no messages provided)
            messages: Full message history in Claude format (optional).
                     If provided, this is used instead of prompt.
            max_turns: Maximum number of agentic turns
            progress_callback: Optional callback for progress updates

        Yields:
            str: Text chunks as they arrive
            dict: Tool call information {"type": "tool_use", "name": str, "id": str, "input": dict}
            dict: Final result {"type": "done", "turns": int}
        """
        # Build messages list
        if messages is None:
            if prompt is None:
                raise ValueError("Either prompt or messages must be provided")
            messages = [{"role": "user", "content": prompt}]
        else:
            # Use provided messages
            messages = messages.copy()  # Don't modify caller's list

        # Filter out custom internal fields from tools before sending to API
        api_tools = [
            {
                "name": tool["name"],
                "description": tool["description"],
                "input_schema": tool["input_schema"],
            }
            for tool in self.available_tools
        ]

        if progress_callback:
            progress_callback("thinking", 0, max_turns, None)

        for turn in range(max_turns):
            if progress_callback:
                progress_callback("calling_claude", turn + 1, max_turns, None)

            # Use streaming API
            with self.anthropic.messages.stream(
                model=self.config.model,
                max_tokens=4096,
                system=self._build_system_prompt(),
                tools=api_tools,
                messages=messages,
            ) as stream:
                # Track content blocks
                current_text = ""

                for event in stream:
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
                messages.append({"role": "assistant", "content": final_message.content})

                # Yield tool use notifications with complete inputs
                for block in final_message.content:
                    if block.type == "tool_use":
                        yield {"type": "tool_use", "name": block.name, "id": block.id, "input": block.input}

                # Execute any tools
                tool_results = []
                for block in final_message.content:
                    if block.type == "tool_use":
                        if progress_callback:
                            progress_callback("executing_tool", turn + 1, max_turns, block.name)

                        result = await self._execute_tool(block.name, block.input)

                        # Truncate large tool results to prevent context overflow
                        # Estimate ~4 chars per token, so 20K chars ≈ 5K tokens
                        max_result_size = 20000  # 20KB
                        if len(result) > max_result_size:
                            truncated_result = result[:max_result_size]
                            truncated_result += f"\n\n... [Result truncated: {len(result)} chars total, showing first {max_result_size} chars]"
                            result = truncated_result

                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": result,
                            }
                        )

                # If no tool calls, we're done
                if not tool_results:
                    if progress_callback:
                        progress_callback("complete", turn + 1, max_turns, None)

                    yield {"type": "done", "turns": turn + 1}
                    return

                # Continue with tool results
                messages.append({"role": "user", "content": tool_results})

        # Max turns reached
        yield {"type": "error", "message": "Maximum turns reached without final answer"}

    async def execute_mcp_prompt(
        self, server_name: str, prompt_name: str, arguments: dict[str, Any] | None = None
    ) -> str:
        """Execute an MCP prompt directly

        Args:
            server_name: MCP server name
            prompt_name: Name of prompt to execute
            arguments: Arguments to pass to prompt

        Returns:
            Combined content from prompt messages

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

        # Execute prompt
        session = self.sessions[server_name]
        result = await session.get_prompt(prompt_name, arguments=arguments)

        # Convert messages to text
        content_parts = []
        for msg in result.messages:
            if hasattr(msg.content, "text"):
                content_parts.append(msg.content.text)
            else:
                content_parts.append(str(msg.content))

        return "\n\n".join(content_parts)

    def _validate_prompt_arguments(self, prompt_def, arguments: dict):
        """Validate arguments against prompt definition

        Raises:
            ValueError: If required arguments missing
        """
        provided_args = set(arguments.keys())

        for arg in prompt_def.arguments:
            if arg.required and arg.name not in provided_args:
                raise ValueError(f"Required argument '{arg.name}' missing. " f"Description: {arg.description}")

    async def _execute_tool(self, tool_name: str, arguments: dict) -> str:
        """Execute a tool call on the appropriate MCP server, introspection, or internal tool"""
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

                return result_text
            except Exception as e:
                return f"Error executing introspection tool {original_tool_name}: {str(e)}"

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
                ]

                script_tools = ["execute_skill_script"]
                schedule_action_tools = ["schedule_action"]

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

                return result_text
            except Exception as e:
                return f"Error executing internal tool {original_tool_name}: {str(e)}"

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

            return result_text
        except Exception as e:
            return f"Error executing tool {original_tool_name}: {str(e)}"

    async def _save_tool_result_to_kg(self, tool_name: str, original_tool_name: str, arguments: dict, result_text: str):
        """Save tool result to knowledge graph if it contains entities

        Supports:
        - search_dci_jobs -> dci_job entities
        - search_jira_tickets -> jira_ticket entities
        - get_jira_ticket -> jira_ticket entity
        """
        # Double-check kg_save_enabled (defensive programming)
        if not self.kg_save_enabled:
            return

        if not result_text or "Error" in result_text:
            return

        try:
            # Parse JSON result
            try:
                data = json.loads(result_text)
            except json.JSONDecodeError:
                # Not JSON, skip
                return

            tx_time = datetime.now()

            # Determine entity type from tool name
            entity_type = None
            entities = []

            if "jira" in original_tool_name.lower():
                entity_type = "jira_ticket"
                # Handle different response formats
                if isinstance(data, list):
                    entities = data
                elif isinstance(data, dict):
                    if "issues" in data:
                        entities = data["issues"]
                    elif "key" in data:
                        # Single ticket
                        entities = [data]

            elif "dci" in original_tool_name.lower() and "job" in original_tool_name.lower():
                entity_type = "dci_job"
                # Handle different response formats
                if isinstance(data, list):
                    entities = data
                elif isinstance(data, dict):
                    if "hits" in data:
                        entities = data["hits"]
                    elif "jobs" in data:
                        entities = data["jobs"]
                    elif "id" in data:
                        # Single job
                        entities = [data]

            if not entity_type or not entities:
                return

            # Store entities
            saved_count = 0
            for entity_data in entities[:20]:  # Limit to 20 entities per call
                entity_id = entity_data.get("id") or entity_data.get("key")
                if not entity_id:
                    continue

                # Parse valid_from timestamp
                created_str = entity_data.get("created_at") or entity_data.get("fields", {}).get("created", "")
                try:
                    valid_from = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    valid_from = tx_time

                # Prepare entity data based on type
                if entity_type == "jira_ticket":
                    stored_data = {
                        "key": entity_data.get("key"),
                        "project": entity_data.get("fields", {}).get("project", {}).get("key"),
                        "summary": entity_data.get("fields", {}).get("summary"),
                        "status": entity_data.get("fields", {}).get("status", {}).get("name"),
                        "priority": entity_data.get("fields", {}).get("priority", {}).get("name"),
                        "assignee": (
                            entity_data.get("fields", {}).get("assignee", {}).get("displayName")
                            if entity_data.get("fields", {}).get("assignee")
                            else None
                        ),
                    }
                elif entity_type == "dci_job":
                    stored_data = {
                        "job_id": entity_id,
                        "status": entity_data.get("status", "unknown"),
                        "remoteci_id": entity_data.get("remoteci_id"),
                        "topic_id": entity_data.get("topic_id"),
                        "state": entity_data.get("state"),
                    }

                    # Store components as separate entities
                    for component in entity_data.get("components", []):
                        comp_id = component.get("id")
                        if comp_id:
                            try:
                                self.knowledge_graph.insert_entity(
                                    entity_type="dci_component",
                                    entity_id=comp_id,
                                    valid_from=valid_from,
                                    tx_from=tx_time,
                                    data={
                                        "type": component.get("type"),
                                        "version": component.get("version"),
                                        "name": component.get("name"),
                                    },
                                )
                            except Exception:
                                pass  # Entity might already exist

                            # Create relationship
                            self.knowledge_graph.insert_relationship(
                                rel_type="job_uses_component",
                                source_id=entity_id,
                                target_id=comp_id,
                                valid_from=valid_from,
                                tx_from=tx_time,
                                properties={},
                            )
                else:
                    stored_data = entity_data

                # Insert entity
                try:
                    self.knowledge_graph.insert_entity(
                        entity_type=entity_type,
                        entity_id=entity_id,
                        valid_from=valid_from,
                        tx_from=tx_time,
                        data=stored_data,
                    )
                    saved_count += 1
                except Exception:
                    # Entity might already exist, that's ok
                    pass

            # Track how many we saved
            if saved_count > 0:
                self.last_tool_calls[-1]["kg_saved_count"] = saved_count

        except Exception:
            # Silently fail - KG storage is best-effort
            pass

    def get_last_kg_saved_count(self) -> int:
        """Get the number of entities saved to KG in the last tool calls"""
        total = 0
        for call in self.last_tool_calls:
            total += call.get("kg_saved_count", 0)
        return total

    def clear_tool_calls(self):
        """Clear tracked tool calls"""
        self.last_tool_calls = []

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
