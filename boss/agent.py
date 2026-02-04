"""MCP Agent for BOSS"""

import asyncio
from typing import Optional
from mcp import ClientSession, StdioServerParameters
from anthropic import Anthropic, AnthropicVertex
from .config import BossConfig, MCPServerConfig
from .mcp_stdio_fix import stdio_client_fixed


class BossAgent:
    """AI Agent with MCP capabilities"""

    def __init__(self, config: BossConfig):
        self.config = config

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
        self._server_tasks: list[asyncio.Task] = []

        # Track tool calls for KG storage
        self.last_tool_calls: list[dict] = []

    async def connect_to_servers(self):
        """Connect to all configured MCP servers"""
        for server_name, server_config in self.config.mcp_servers.items():
            try:
                task = asyncio.create_task(
                    self._run_server(server_name, server_config),
                    name=f"mcp_{server_name}"
                )
                self._server_tasks.append(task)

                # Wait for server initialization (up to 5 seconds)
                for i in range(10):
                    await asyncio.sleep(0.5)
                    if server_name in self.sessions:
                        print(f"✓ Connected to {server_name} MCP server with {len([t for t in self.available_tools if t['_server'] == server_name])} tools")
                        break
                else:
                    print(f"⚠ Warning: {server_name} did not initialize within 5 seconds")

            except Exception as e:
                print(f"✗ Failed to connect to {server_name}: {e}")
                import traceback
                traceback.print_exc()

    async def _run_server(self, name: str, config: MCPServerConfig):
        """Run an MCP server connection (as a background task)"""
        try:
            print(f"[{name}] Creating server parameters...", flush=True)
            server_params = StdioServerParameters(
                command=config.command,
                args=config.args,
                env=config.env if config.env else None,
            )

            print(f"[{name}] Starting FIXED stdio_client...", flush=True)
            # Use FIXED stdio_client with proper buffering
            async with stdio_client_fixed(server_params) as (read_stream, write_stream):
                print(f"[{name}] Got streams, creating session...", flush=True)

                # CRITICAL: ClientSession must be used as async context manager
                # to start the _receive_loop task that processes incoming messages!
                async with ClientSession(read_stream, write_stream) as session:
                    print(f"[{name}] Initializing session...", flush=True)
                    try:
                        result = await asyncio.wait_for(session.initialize(), timeout=10.0)
                        print(f"[{name}] Session initialized! Result: {result}", flush=True)
                    except asyncio.TimeoutError:
                        print(f"[{name}] TIMEOUT waiting for initialize response!", flush=True)
                        raise
                    except Exception as e:
                        print(f"[{name}] ERROR during initialize: {e}", flush=True)
                        raise
                    self.sessions[name] = session

                    print(f"[{name}] Listing tools...", flush=True)
                    tools_list = await session.list_tools()
                    print(f"[{name}] Got {len(tools_list.tools)} tools", flush=True)
                    for tool in tools_list.tools:
                        tool_def = {
                            "name": f"{name}__{tool.name}",
                            "description": tool.description or "",
                            "input_schema": tool.inputSchema,
                            "_server": name,
                            "_original_name": tool.name,
                        }
                        self.available_tools.append(tool_def)

                    print(f"[{name}] Connection ready, keeping alive...", flush=True)
                    # Keep the connection alive by waiting indefinitely
                    try:
                        await asyncio.Event().wait()
                    except asyncio.CancelledError:
                        print(f"[{name}] Connection cancelled, shutting down", flush=True)
        except Exception as e:
            print(f"[{name}] ERROR in _run_server: {e}", flush=True)
            import traceback
            traceback.print_exc()

    async def query(self, prompt: str, max_turns: int = 10) -> str:
        """Query the agent with a prompt"""
        messages = [{"role": "user", "content": prompt}]

        # Filter out custom internal fields from tools before sending to API
        api_tools = [
            {
                "name": tool["name"],
                "description": tool["description"],
                "input_schema": tool["input_schema"],
            }
            for tool in self.available_tools
        ]

        for turn in range(max_turns):
            response = self.anthropic.messages.create(
                model=self.config.model,
                max_tokens=4096,
                tools=api_tools,
                messages=messages,
            )

            messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = await self._execute_tool(
                        block.name,
                        block.input
                    )
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

            if not tool_results:
                final_text = ""
                for block in response.content:
                    if hasattr(block, "text"):
                        final_text += block.text
                return final_text

            messages.append({"role": "user", "content": tool_results})

        return "Maximum turns reached without final answer"

    async def _execute_tool(self, tool_name: str, arguments: dict) -> str:
        """Execute a tool call on the appropriate MCP server"""
        parts = tool_name.split("__", 1)
        if len(parts) != 2:
            return f"Error: Invalid tool name format: {tool_name}"

        server_name, original_tool_name = parts

        if server_name not in self.sessions:
            return f"Error: Server {server_name} not connected"

        session = self.sessions[server_name]

        try:
            result = await session.call_tool(original_tool_name, arguments)

            if result.content:
                return "\n".join([
                    item.text if hasattr(item, "text") else str(item)
                    for item in result.content
                ])
            return "Tool executed successfully with no output"
        except Exception as e:
            return f"Error executing tool {original_tool_name}: {str(e)}"

    async def close(self):
        """Close all MCP server connections"""
        for task in self._server_tasks:
            task.cancel()

        if self._server_tasks:
            await asyncio.gather(*self._server_tasks, return_exceptions=True)

        self._server_tasks.clear()
        self.sessions.clear()
        print(f"Closed all connections")
