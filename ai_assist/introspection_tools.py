"""Self-introspection tools for ai-assist agent

These tools allow the agent to search its own knowledge graph and conversation memory,
enabling intelligent decisions about when to use cached data vs fresh API calls.
"""

import json
from datetime import datetime, timedelta
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .knowledge_graph import KnowledgeGraph
    from .context import ConversationMemory


class IntrospectionTools:
    """Provides tools for agent self-introspection"""

    def __init__(
        self,
        knowledge_graph: Optional["KnowledgeGraph"] = None,
        conversation_memory: Optional["ConversationMemory"] = None
    ):
        self.knowledge_graph = knowledge_graph
        self.conversation_memory = conversation_memory

    def get_tool_definitions(self) -> list[dict]:
        """Get tool definitions in Anthropic format

        Returns:
            List of tool definitions that can be added to Claude's available tools
        """
        tools = []

        if self.knowledge_graph is not None:
            tools.extend([
                {
                    "name": "search_knowledge_graph",
                    "description": """Search the knowledge graph for entities and historical data.

Use this tool when you need to:
- Check if information is already known (e.g., "Do I already know about CILAB-123?")
- Find recent failures or issues without calling external APIs
- Get historical context about jobs, tickets, or components
- Answer questions using cached data instead of fresh API calls

Examples:
- "Search for Jira tickets with status Open"
- "Find DCI jobs that failed in the last 24 hours"
- "Get all components of type 'ocp'"

The tool will return entities from the knowledge graph with their data and timestamps.
""",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "entity_type": {
                                "type": "string",
                                "description": "Type of entity to search for. Options: 'jira_ticket', 'dci_job', 'dci_component'",
                                "enum": ["jira_ticket", "dci_job", "dci_component"]
                            },
                            "time_range_hours": {
                                "type": "number",
                                "description": "Optional: Only return entities from the last N hours (e.g., 24 for last day)",
                            },
                            "limit": {
                                "type": "number",
                                "description": "Maximum number of results to return (default: 20, max: 100)",
                                "default": 20
                            }
                        },
                        "required": ["entity_type"]
                    },
                    "_server": "introspection"
                },
                {
                    "name": "get_kg_entity",
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
                                "description": "The entity ID to retrieve (e.g., 'CILAB-123' for Jira ticket, 'job-abc-123' for DCI job)"
                            }
                        },
                        "required": ["entity_id"]
                    },
                    "_server": "introspection"
                },
                {
                    "name": "get_kg_stats",
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
                    "_server": "introspection"
                }
            ])

        if self.conversation_memory is not None:
            tools.append({
                "name": "search_conversation_history",
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
                            "description": "Term to search for in conversation history (case-insensitive)"
                        }
                    },
                    "required": ["search_term"]
                },
                "_server": "introspection"
            })

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
        else:
            return json.dumps({"error": f"Unknown introspection tool: {tool_name}"})

    async def _search_knowledge_graph(self, arguments: dict) -> str:
        """Search knowledge graph for entities"""
        if self.knowledge_graph is None:
            return json.dumps({"error": "Knowledge graph not available"})

        entity_type = arguments.get("entity_type")
        time_range_hours = arguments.get("time_range_hours")
        limit = min(arguments.get("limit", 20), 100)

        try:
            # Query knowledge graph
            if time_range_hours:
                # Get entities from specific time range
                since_time = datetime.now() - timedelta(hours=time_range_hours)
                entities = self.knowledge_graph.query_as_of(
                    datetime.now(),
                    entity_type=entity_type,
                    limit=None
                )
                # Filter by valid_from time
                entities = [e for e in entities if e.valid_from >= since_time][:limit]
            else:
                # Get all current entities of this type
                entities = self.knowledge_graph.query_as_of(
                    datetime.now(),
                    entity_type=entity_type,
                    limit=limit
                )

            # Format results
            results = []
            for entity in entities:
                results.append({
                    "id": entity.id,
                    "type": entity.entity_type,
                    "data": entity.data,
                    "valid_from": entity.valid_from.isoformat(),
                    "discovered_at": entity.tx_from.isoformat()
                })

            return json.dumps({
                "found": len(results),
                "entities": results,
                "message": f"Found {len(results)} {entity_type} entities in knowledge graph"
            }, indent=2)

        except Exception as e:
            return json.dumps({"error": f"Error searching knowledge graph: {str(e)}"})

    async def _get_kg_entity(self, arguments: dict) -> str:
        """Get specific entity from knowledge graph"""
        if self.knowledge_graph is None:
            return json.dumps({"error": "Knowledge graph not available"})

        entity_id = arguments.get("entity_id")

        try:
            entity = self.knowledge_graph.get_entity(entity_id)

            if entity:
                # Get related entities too
                relationships = self.knowledge_graph.get_related_entities(
                    entity_id,
                    direction="both"
                )

                related = []
                for rel, related_entity in relationships:
                    related.append({
                        "relationship": rel.rel_type,
                        "entity_id": related_entity.id,
                        "entity_type": related_entity.entity_type,
                        "data": related_entity.data
                    })

                return json.dumps({
                    "found": True,
                    "entity": {
                        "id": entity.id,
                        "type": entity.entity_type,
                        "data": entity.data,
                        "valid_from": entity.valid_from.isoformat(),
                        "discovered_at": entity.tx_from.isoformat()
                    },
                    "related_entities": related,
                    "message": f"Found entity {entity_id} in knowledge graph"
                }, indent=2)
            else:
                return json.dumps({
                    "found": False,
                    "message": f"Entity {entity_id} not found in knowledge graph"
                })

        except Exception as e:
            return json.dumps({"error": f"Error getting entity: {str(e)}"})

    async def _get_kg_stats(self, arguments: dict) -> str:
        """Get knowledge graph statistics"""
        if self.knowledge_graph is None:
            return json.dumps({"error": "Knowledge graph not available"})

        try:
            stats = self.knowledge_graph.get_stats()
            return json.dumps({
                "total_entities": stats["total_entities"],
                "entities_by_type": stats["entities_by_type"],
                "total_relationships": stats["total_relationships"],
                "relationships_by_type": stats["relationships_by_type"],
                "message": f"Knowledge graph contains {stats['total_entities']} entities"
            }, indent=2)

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
                    results.append({
                        "exchange_number": i + 1,
                        "timestamp": exchange["timestamp"],
                        "user_message": exchange["user"][:200],  # Truncate for readability
                        "assistant_response": exchange["assistant"][:200],
                        "matched_in": "user" if search_term in user_text else "assistant"
                    })

            return json.dumps({
                "found": len(results),
                "matches": results,
                "message": f"Found {len(results)} exchanges mentioning '{search_term}'"
            }, indent=2)

        except Exception as e:
            return json.dumps({"error": f"Error searching conversation: {str(e)}"})
