"""Self-introspection tools for ai-assist agent

These tools allow the agent to search its own knowledge graph and conversation memory,
enabling intelligent decisions about when to use cached data vs fresh API calls.
"""

import json
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .agent import AiAssistAgent
    from .context import ConversationMemory
    from .knowledge_graph import KnowledgeGraph


class IntrospectionTools:
    """Provides tools for agent self-introspection"""

    def __init__(
        self,
        knowledge_graph: Optional["KnowledgeGraph"] = None,
        conversation_memory: Optional["ConversationMemory"] = None,
        available_prompts: dict | None = None,
        agent: Optional["AiAssistAgent"] = None,
    ):
        self.knowledge_graph = knowledge_graph
        self.conversation_memory = conversation_memory
        # IMPORTANT: Use 'if not None' to preserve reference to empty dict
        self.available_prompts = available_prompts if available_prompts is not None else {}
        self.agent = agent  # Reference to parent agent for executing prompts

    def get_tool_definitions(self) -> list[dict]:
        """Get tool definitions in Anthropic format

        Returns:
            List of tool definitions that can be added to Claude's available tools
        """
        tools = []

        if self.knowledge_graph is not None:
            tools.extend(
                [
                    {
                        "name": "introspection__search_knowledge_graph",
                        "description": """Search the knowledge graph for entities and historical data.

Use this tool when you need to:
- Check if information is already known (e.g., "Do I already know about CILAB-123?")
- Find recent failures or issues without calling external APIs
- Get historical context about jobs, tickets, or components
- Recall previous conversations (use entity_type='conversation')
- Answer questions using cached data instead of fresh API calls

Examples:
- "Search for Jira tickets with status Open"
- "Find DCI jobs that failed in the last 24 hours"
- "Search previous conversations about DCI failures"

The tool will return entities from the knowledge graph with their data and timestamps.
""",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "entity_type": {
                                    "type": "string",
                                    "description": "Type of entity to search for. Options: 'jira_ticket', 'dci_job', 'dci_component', 'conversation'",
                                    "enum": ["jira_ticket", "dci_job", "dci_component", "conversation"],
                                },
                                "search_text": {
                                    "type": "string",
                                    "description": "Optional: Case-insensitive text search within entity data. Useful for finding conversations mentioning specific topics.",
                                },
                                "time_range_hours": {
                                    "type": "number",
                                    "description": "Optional: Only return entities from the last N hours (e.g., 24 for last day)",
                                },
                                "limit": {
                                    "type": "number",
                                    "description": "Maximum number of results to return (default: 20, max: 100)",
                                    "default": 20,
                                },
                            },
                            "required": ["entity_type"],
                        },
                        "_server": "introspection",
                    },
                    {
                        "name": "introspection__get_kg_entity",
                        "description": """Get detailed information about a specific entity from the knowledge graph.

Use this tool when:
- You need details about a specific Jira ticket (e.g., CILAB-123)
- You want to check the status of a known DCI job
- You need component information you've seen before

This is faster than calling external APIs if the entity is already in the knowledge graph.

Example: Get details about Jira ticket CILAB-123 from the knowledge graph.
""",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "entity_id": {
                                    "type": "string",
                                    "description": "The entity ID to retrieve (e.g., 'CILAB-123' for Jira ticket, 'job-abc-123' for DCI job)",
                                }
                            },
                            "required": ["entity_id"],
                        },
                        "_server": "introspection",
                    },
                    {
                        "name": "introspection__get_kg_stats",
                        "description": """Get statistics about what's in the knowledge graph.

Use this to understand:
- How many entities are stored
- What types of data are available
- Whether the knowledge graph has relevant information

This helps you decide whether to search the KG or call external APIs.
""",
                        "input_schema": {
                            "type": "object",
                            "properties": {},
                        },
                        "_server": "introspection",
                    },
                ]
            )

        # MCP prompt introspection tool
        tools.append(
            {
                "name": "introspection__inspect_mcp_prompt",
                "description": """Get detailed information about an MCP prompt including its arguments.

Use this tool BEFORE creating tasks with MCP prompts to discover:
- What arguments the prompt accepts
- Which arguments are required vs optional
- Argument names and descriptions
- Correct argument format

Example: User says "schedule /tpci/weekly_report for Semih"
1. Call inspect_mcp_prompt with server="tpci" and prompt="weekly_report"
2. See that it has argument "for" (required) - person to generate report for
3. Create task with prompt="mcp://tpci/weekly_report" and prompt_arguments={"for": "Semih"}

This ensures you use the correct argument names.
""",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "server": {
                            "type": "string",
                            "description": "MCP server name (e.g., 'dci', 'tpci')",
                        },
                        "prompt": {
                            "type": "string",
                            "description": "Prompt name (e.g., 'weekly_report', 'rca')",
                        },
                    },
                    "required": ["server", "prompt"],
                },
                "_server": "introspection",
            }
        )

        # MCP prompt execution tool (only if agent is available)
        if self.agent is not None:
            tools.append(
                {
                    "name": "introspection__execute_mcp_prompt",
                    "description": """Execute an MCP prompt directly and return its result.

Use this tool when:
- User asks to run a prompt NOW (e.g., "run /tpci/weekly_report for Peri now")
- User wants immediate results from an MCP prompt
- You need to execute a prompt during conversation, not schedule it

Do NOT use this for:
- Scheduling prompts to run later (use create_task instead)
- Recurring prompts (use create_task with interval instead)

Example: User says "run /tpci/weekly_report for Peri now"
1. Call inspect_mcp_prompt to discover arguments
2. Call execute_mcp_prompt with server="tpci", prompt="weekly_report", arguments={"for": "Peri"}
3. Return the result to the user

This executes the prompt immediately in the current conversation.
""",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "server": {
                                "type": "string",
                                "description": "MCP server name (e.g., 'dci', 'tpci')",
                            },
                            "prompt": {
                                "type": "string",
                                "description": "Prompt name (e.g., 'weekly_report', 'rca')",
                            },
                            "arguments": {
                                "type": "object",
                                "description": "Arguments to pass to the prompt (optional, depends on prompt requirements)",
                            },
                        },
                        "required": ["server", "prompt"],
                    },
                    "_server": "introspection",
                }
            )

        if self.conversation_memory is not None:
            tools.append(
                {
                    "name": "introspection__search_conversation_history",
                    "description": """Search recent conversation history for context.

Use this tool when:
- You need to recall what was discussed earlier in the conversation
- The user refers to "earlier" or "before" without specifics
- You want to find when a specific topic was mentioned
- You need context about previous questions and answers

Note: This searches the current conversation session only (last 10 exchanges).

Example: Search for previous mentions of "DCI failures" in conversation.
""",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "search_term": {
                                "type": "string",
                                "description": "Term to search for in conversation history (case-insensitive)",
                            }
                        },
                        "required": ["search_term"],
                    },
                    "_server": "introspection",
                }
            )

        return tools

    async def execute_tool(self, tool_name: str, arguments: dict) -> str:
        """Execute an introspection tool

        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments

        Returns:
            JSON string with results
        """
        if tool_name == "search_knowledge_graph":
            return await self._search_knowledge_graph(arguments)
        elif tool_name == "get_kg_entity":
            return await self._get_kg_entity(arguments)
        elif tool_name == "get_kg_stats":
            return await self._get_kg_stats(arguments)
        elif tool_name == "search_conversation_history":
            return await self._search_conversation_history(arguments)
        elif tool_name == "inspect_mcp_prompt":
            return self._inspect_mcp_prompt(arguments)
        elif tool_name == "execute_mcp_prompt":
            return await self._execute_mcp_prompt(arguments)
        else:
            return json.dumps({"error": f"Unknown introspection tool: {tool_name}"})

    async def _search_knowledge_graph(self, arguments: dict) -> str:
        """Search knowledge graph for entities"""
        if self.knowledge_graph is None:
            return json.dumps({"error": "Knowledge graph not available"})

        entity_type = arguments.get("entity_type")
        time_range_hours = arguments.get("time_range_hours")
        search_text = arguments.get("search_text")
        limit = min(arguments.get("limit", 20), 100)

        try:
            # Query knowledge graph
            if time_range_hours:
                # Get entities from specific time range
                since_time = datetime.now() - timedelta(hours=time_range_hours)
                entities = self.knowledge_graph.query_as_of(
                    datetime.now(), entity_type=entity_type, limit=None, search_text=search_text
                )
                # Filter by valid_from time
                entities = [e for e in entities if e.valid_from >= since_time][:limit]
            else:
                # Get all current entities of this type
                entities = self.knowledge_graph.query_as_of(
                    datetime.now(), entity_type=entity_type, limit=limit, search_text=search_text
                )

            # Format results
            results = []
            for entity in entities:
                results.append(
                    {
                        "id": entity.id,
                        "type": entity.entity_type,
                        "data": entity.data,
                        "valid_from": entity.valid_from.isoformat(),
                        "discovered_at": entity.tx_from.isoformat(),
                    }
                )

            return json.dumps(
                {
                    "found": len(results),
                    "entities": results,
                    "message": f"Found {len(results)} {entity_type} entities in knowledge graph",
                },
                indent=2,
            )

        except Exception as e:
            return json.dumps({"error": f"Error searching knowledge graph: {str(e)}"})

    async def _get_kg_entity(self, arguments: dict) -> str:
        """Get specific entity from knowledge graph"""
        if self.knowledge_graph is None:
            return json.dumps({"error": "Knowledge graph not available"})

        entity_id = arguments.get("entity_id")
        if not entity_id:
            return json.dumps({"error": "entity_id is required"})

        try:
            entity = self.knowledge_graph.get_entity(entity_id)

            if entity:
                # Get related entities too
                relationships = self.knowledge_graph.get_related_entities(entity_id, direction="both")

                related = []
                for rel, related_entity in relationships:
                    related.append(
                        {
                            "relationship": rel.rel_type,
                            "entity_id": related_entity.id,
                            "entity_type": related_entity.entity_type,
                            "data": related_entity.data,
                        }
                    )

                return json.dumps(
                    {
                        "found": True,
                        "entity": {
                            "id": entity.id,
                            "type": entity.entity_type,
                            "data": entity.data,
                            "valid_from": entity.valid_from.isoformat(),
                            "discovered_at": entity.tx_from.isoformat(),
                        },
                        "related_entities": related,
                        "message": f"Found entity {entity_id} in knowledge graph",
                    },
                    indent=2,
                )
            else:
                return json.dumps({"found": False, "message": f"Entity {entity_id} not found in knowledge graph"})

        except Exception as e:
            return json.dumps({"error": f"Error getting entity: {str(e)}"})

    async def _get_kg_stats(self, arguments: dict) -> str:
        """Get knowledge graph statistics"""
        if self.knowledge_graph is None:
            return json.dumps({"error": "Knowledge graph not available"})

        try:
            stats = self.knowledge_graph.get_stats()
            return json.dumps(
                {
                    "total_entities": stats["total_entities"],
                    "entities_by_type": stats["entities_by_type"],
                    "total_relationships": stats["total_relationships"],
                    "relationships_by_type": stats["relationships_by_type"],
                    "message": f"Knowledge graph contains {stats['total_entities']} entities",
                },
                indent=2,
            )

        except Exception as e:
            return json.dumps({"error": f"Error getting stats: {str(e)}"})

    async def _search_conversation_history(self, arguments: dict) -> str:
        """Search conversation history"""
        if self.conversation_memory is None:
            return json.dumps({"error": "Conversation memory not available"})

        search_term = arguments.get("search_term", "").lower()

        try:
            results = []
            for i, exchange in enumerate(self.conversation_memory.exchanges):
                user_text = exchange["user"].lower()
                assistant_text = exchange["assistant"].lower()

                if search_term in user_text or search_term in assistant_text:
                    results.append(
                        {
                            "exchange_number": i + 1,
                            "timestamp": exchange["timestamp"],
                            "user_message": exchange["user"][:200],  # Truncate for readability
                            "assistant_response": exchange["assistant"][:200],
                            "matched_in": "user" if search_term in user_text else "assistant",
                        }
                    )

            return json.dumps(
                {
                    "found": len(results),
                    "matches": results,
                    "message": f"Found {len(results)} exchanges mentioning '{search_term}'",
                },
                indent=2,
            )

        except Exception as e:
            return json.dumps({"error": f"Error searching conversation: {str(e)}"})

    def _inspect_mcp_prompt(self, arguments: dict) -> str:
        """Inspect an MCP prompt to discover its arguments

        Args:
            arguments: Dict with 'server' and 'prompt' keys

        Returns:
            JSON string with prompt information including arguments
        """
        server = arguments.get("server")
        prompt = arguments.get("prompt")

        # Validate server exists
        if not server or server not in self.available_prompts:
            available = list(self.available_prompts.keys())
            return json.dumps(
                {
                    "error": f"Server '{server}' not found",
                    "available_servers": available,
                    "message": f"Available servers: {', '.join(available)}",
                },
                indent=2,
            )

        # Validate prompt exists
        if not prompt or prompt not in self.available_prompts[server]:
            available = list(self.available_prompts[server].keys())
            return json.dumps(
                {
                    "error": f"Prompt '{prompt}' not found in server '{server}'",
                    "available_prompts": available,
                    "message": f"Available prompts: {', '.join(available)}",
                }
            )

        # Get prompt definition
        prompt_def = self.available_prompts[server][prompt]

        # Build response
        result = {
            "server": server,
            "prompt": prompt,
            "mcp_format": f"mcp://{server}/{prompt}",
            "description": prompt_def.description if hasattr(prompt_def, "description") else None,
            "arguments": [],
        }

        # Extract argument information
        if hasattr(prompt_def, "arguments") and prompt_def.arguments:
            for arg in prompt_def.arguments:
                arg_info = {
                    "name": arg.name,
                    "required": arg.required,
                    "description": arg.description if hasattr(arg, "description") else None,
                }
                result["arguments"].append(arg_info)

        # Add usage example
        if result["arguments"]:
            example_args = {arg["name"]: f"<{arg['name']}>" for arg in result["arguments"] if arg["required"]}
            result["example_usage"] = {
                "prompt": f"mcp://{server}/{prompt}",
                "prompt_arguments": example_args,
            }

        return json.dumps(result, indent=2)

    async def _execute_mcp_prompt(self, arguments: dict) -> str:
        """Execute an MCP prompt directly

        Args:
            arguments: Dict with 'server', 'prompt', and optional 'arguments' keys

        Returns:
            JSON string with execution result or error
        """
        if self.agent is None:
            return json.dumps(
                {"error": "Agent reference not available", "message": "Cannot execute prompts without agent reference"},
                indent=2,
            )

        server = arguments.get("server")
        prompt = arguments.get("prompt")
        prompt_arguments = arguments.get("arguments", {})

        if not server or not prompt:
            return json.dumps({"error": "Both 'server' and 'prompt' arguments are required"}, indent=2)

        try:
            # Execute the prompt using the agent's method
            result = await self.agent.execute_mcp_prompt(server, prompt, prompt_arguments)

            return json.dumps(
                {
                    "success": True,
                    "server": server,
                    "prompt": prompt,
                    "result": result,
                    "message": f"Successfully executed {server}/{prompt}",
                },
                indent=2,
            )

        except Exception as e:
            return json.dumps(
                {"success": False, "error": str(e), "message": f"Failed to execute {server}/{prompt}: {str(e)}"},
                indent=2,
            )
