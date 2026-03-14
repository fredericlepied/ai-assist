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

        # AWL script execution tool (only if agent is available)
        if self.agent is not None:
            tools.append(
                {
                    "name": "introspection__execute_awl_script",
                    "description": """Execute an AWL (Agent Workflow Language) script from the filesystem.

Use this tool when:
- User asks to run an AWL workflow or references a .awl file
- A task requires structured multi-step orchestration with variables and conditionals
- User mentions workflow files like "run the analysis script"

Script search order for relative paths:
1. Current working directory

Variable injection: Pass {"key": "value"} to pre-populate workflow variables (${key} in scripts).

Returns task outcomes, return value, and final variables.
""",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "script_path": {
                                "type": "string",
                                "description": "Path to AWL script (.awl extension, relative or absolute)",
                            },
                            "variables": {
                                "type": "object",
                                "description": "Optional initial variables to inject into the workflow",
                                "additionalProperties": True,
                            },
                        },
                        "required": ["script_path"],
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

        # AWL validation tool — always available, teaches AWL syntax via its description
        tools.append(
            {
                "name": "introspection__validate_awl_script",
                "description": """Validate an AWL (Agent Workflow Language) script for syntax errors.

Use this tool when:
- You want to write an AWL script for the user
- You need to verify AWL syntax before asking the user to run it
- The user asks about AWL syntax or how to write a workflow

Returns "Valid AWL script." on success, or a parse error with line number.

━━━ AWL SYNTAX REFERENCE ━━━

## Structure

Every script starts with @start and ends with @end:

  @start
    ... directives ...
  @end

## Directives

  @task <id> [hints]     — agent task block
  Goal: <text>           — what to achieve (required)
  Context: <text>        — additional context (optional)
  Constraints: <text>    — limitations (optional)
  Success: <text>        — completion criteria (optional)
  Expose: var1, var2     — variables to extract from the agent response
  @end

  @set <var> = <value>   — assign a variable (literal or ${interpolation})

  @if <expr>             — conditional
    ...
  @else
    ...
  @end

  @loop <collection> as <item> [limit=N] [collect=<var>[(<fields>)]]
    ...
  @end

  @return <expr>         — return workflow result

## Task Hints (placed after task id)

  @no-history    agent ignores prior conversation history
  @no-kg         agent does not consult the knowledge graph

## Variables

  @set x = "literal"    assign a string
  @set x = ${y}         copy from another variable
  ${varname}            interpolation in any text field

## Expressions (used in @if conditions and @loop collections)

  handlers              variable truthiness
  not report_exists     negation
  len(handlers) > 0     length comparison (>, <, >=, <=, ==, !=)
  handlers[0]           index access
  config.entrypoint     property access

## Collecting Loop Results

  @loop items as item collect=results
  collect=results(field1,field2)   — collect only specific exposed fields

After the loop, `results` is a list of dicts from each successful iteration.

## Initial Variables (injected before the script runs)

  CLI:   ai-assist /run workflow.awl key=value
  Agent: call introspection__execute_awl_script with variables={"key": "value"}

## Complete Example

  @start

  @task find_handlers @no-kg
  Goal: Find all HTTP handlers in the repository.
  Expose: handlers
  @end

  @if len(handlers) > 0

    @loop handlers as handler limit=5 collect=summaries

      @task inspect_handler @no-history
      Goal: Understand what ${handler} does.
      Expose: handler_summary
      @end

    @end

  @else

    @task fallback_search
    Goal: Search more broadly for request entry points.
    Expose: handlers
    @end

  @end

  @return handlers

  @end
""",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "awl_code": {
                            "type": "string",
                            "description": "The complete AWL script source to validate",
                        }
                    },
                    "required": ["awl_code"],
                },
                "_server": "introspection",
            }
        )

        # Always add get_tool_help (works with any agent reference)
        tools.append(
            {
                "name": "introspection__get_tool_help",
                "description": "Get full documentation for a tool including query syntax, available fields, and examples.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "tool_name": {
                            "type": "string",
                            "description": "Full tool name (e.g., 'dci__search_dci_jobs')",
                        },
                    },
                    "required": ["tool_name"],
                },
                "_server": "introspection",
            }
        )

        # Always add get_skill_help (works with any agent reference that has skills_manager)
        tools.append(
            {
                "name": "introspection__get_skill_help",
                "description": (
                    "Get full instructions for an installed skill including its SKILL.md body "
                    "and skill directory path."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "skill_name": {
                            "type": "string",
                            "description": "Name of the installed skill (e.g., 'redhat-directory')",
                        },
                    },
                    "required": ["skill_name"],
                },
                "_server": "introspection",
            }
        )

        return tools

    async def execute_tool(self, tool_name: str, arguments: dict) -> str:
        """Execute an introspection tool"""
        dispatch = {
            "search_knowledge_graph": self._search_knowledge_graph,
            "get_kg_entity": self._get_kg_entity,
            "get_kg_stats": self._get_kg_stats,
            "search_conversation_history": self._search_conversation_history,
            "inspect_mcp_prompt": self._inspect_mcp_prompt,
            "execute_mcp_prompt": self._execute_mcp_prompt,
            "execute_awl_script": self._execute_awl_script,
            "validate_awl_script": self._validate_awl_script,
            "get_tool_help": self._get_tool_help,
            "get_skill_help": self._get_skill_help,
        }

        handler = dispatch.get(tool_name)
        if not handler:
            return json.dumps({"error": f"Unknown introspection tool: {tool_name}"})

        result = handler(arguments)
        if hasattr(result, "__await__"):
            result = await result
        return str(result)

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

    def _get_tool_help(self, arguments: dict) -> str:
        """Return full documentation for a tool (progressive disclosure).

        Args:
            arguments: Dict with 'tool_name' key

        Returns:
            JSON string with full description and input_schema
        """
        tool_name = arguments.get("tool_name", "")
        if not self.agent:
            return json.dumps({"error": "Agent reference not available"})

        for tool in self.agent.available_tools:
            if tool["name"] == tool_name:
                return json.dumps(
                    {
                        "tool_name": tool_name,
                        "description": tool.get("_full_description", tool["description"]),
                        "input_schema": tool["input_schema"],
                    },
                    indent=2,
                )

        return json.dumps({"error": f"Tool not found: {tool_name}"})

    def _get_skill_help(self, arguments: dict) -> str:
        """Return full instructions for an installed skill (progressive disclosure).

        Args:
            arguments: Dict with 'skill_name' key

        Returns:
            JSON string with full skill body, directory path, and scripts
        """
        skill_name = arguments.get("skill_name", "")
        if not self.agent:
            return json.dumps({"error": "Agent reference not available"})

        content = self.agent.skills_manager.loaded_skills.get(skill_name)
        if not content:
            available = list(self.agent.skills_manager.loaded_skills.keys())
            return json.dumps(
                {
                    "error": f"Skill not found: {skill_name}",
                    "available_skills": available,
                }
            )

        result = {
            "skill_name": skill_name,
            "description": content.metadata.description,
            "skill_directory": str(content.metadata.skill_path),
            "body": content.body,
        }

        script_execution_enabled = (
            hasattr(self.agent, "script_execution_tools") and self.agent.script_execution_tools.enabled
        )
        if not script_execution_enabled:
            result["warning"] = (
                "Script execution is DISABLED. Do NOT execute any scripts from this skill's directory, "
                "neither via internal__execute_skill_script nor via shell commands."
            )

        return json.dumps(
            result,
            indent=2,
        )

    def _validate_awl_script(self, arguments: dict) -> str:
        """Parse an AWL script and report syntax errors"""
        from .awl_parser import AWLParser, ParseError

        awl_code = arguments.get("awl_code", "")
        if not awl_code.strip():
            return "Error: awl_code is required"

        try:
            AWLParser(awl_code).parse()
            return "Valid AWL script."
        except ParseError as e:
            return f"Parse Error: {e}"
        except Exception as e:
            return f"Error: {e}"

    async def _execute_awl_script(self, arguments: dict) -> str:
        """Execute an AWL script with optional variable injection"""
        from pathlib import Path

        from .awl_parser import AWLParser, ParseError
        from .awl_runtime import AWLRuntime, AWLRuntimeError

        if self.agent is None:
            return "Error: Agent not available for AWL execution"

        script_path = arguments.get("script_path", "")
        variables = arguments.get("variables") or {}

        if not script_path.endswith(".awl"):
            return f"Error: Script must have .awl extension, got: {script_path}"

        path_obj = Path(script_path).expanduser()

        if not path_obj.is_absolute():
            candidate = Path.cwd() / script_path
            if not candidate.exists() or not candidate.is_file():
                return f"Error: AWL script not found: {script_path}\nSearched in: {Path.cwd()}"
            path_obj = candidate
        elif not path_obj.exists() or not path_obj.is_file():
            return f"Error: AWL script not found: {script_path}"

        try:
            source = path_obj.read_text()
            workflow = AWLParser(source).parse()
        except ParseError as e:
            return f"AWL Parse Error in {path_obj.name}:\n{e}"
        except Exception as e:
            return f"Error reading script: {e}"

        try:
            runtime = AWLRuntime(self.agent)
            result = await runtime.execute(workflow, variables=variables or None)
        except AWLRuntimeError as e:
            return f"AWL Runtime Error:\n{e}"

        lines = [f"AWL Workflow: {path_obj.name}", f"Success: {result.success}"]
        if result.return_value is not None:
            lines.append(f"Return: {json.dumps(result.return_value)}")
        for outcome in result.task_outcomes:
            lines.append(f"  [{outcome.status}] {outcome.summary[:100]}")
        return "\n".join(lines)
