"""Internal tools for agent knowledge management"""

import json
from datetime import datetime
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from .agent import AiAssistAgent
    from .knowledge_graph import KnowledgeGraph


class KnowledgeTools:
    """Tools for agent to manage its own knowledge"""

    def __init__(self, knowledge_graph: "KnowledgeGraph"):
        self.kg = knowledge_graph
        self.agent: "AiAssistAgent | None" = None

    def get_tool_definitions(self) -> list[dict]:
        """Get MCP-style tool definitions for knowledge management"""
        return [
            {
                "name": "internal__save_knowledge",
                "description": """AGENT-ONLY: Directly save a specific piece of knowledge.

Use this for immediate, explicit saves (not synthesis).
For broader reflection, use internal__trigger_synthesis instead.

Call this when you notice:
- User stated a preference about workflows/tools/style
- You learned a pattern or best practice
- User provided project context or goals
- A decision was made with clear rationale

Args:
    entity_type: Type of knowledge (user_preference, lesson_learned, project_context, decision_rationale)
    key: Unique identifier (e.g., "python_test_framework")
    content: The knowledge (1-2 sentences)
    tags: Optional categorization tags (default: [])
    confidence: How confident 0.0-1.0 (default: 1.0)

Returns:
    Confirmation with entity ID

Example:
    save_knowledge(
        "user_preference",
        "python_test_framework",
        "User prefers pytest over unittest for all Python testing",
        tags=["python", "testing"],
        confidence=1.0
    )
""",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "entity_type": {
                            "type": "string",
                            "enum": [
                                "user_preference",
                                "lesson_learned",
                                "project_context",
                                "decision_rationale",
                            ],
                            "description": "Type of knowledge being stored",
                        },
                        "key": {
                            "type": "string",
                            "description": "Unique identifier for this knowledge",
                        },
                        "content": {
                            "type": "string",
                            "description": "The actual knowledge (1-2 sentences)",
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional tags for categorization",
                            "default": [],
                        },
                        "confidence": {
                            "type": "number",
                            "minimum": 0.0,
                            "maximum": 1.0,
                            "description": "Confidence level (0.0-1.0)",
                            "default": 1.0,
                        },
                    },
                    "required": ["entity_type", "key", "content"],
                },
                "_server": "internal",
                "_original_name": "save_knowledge",
            },
            {
                "name": "internal__search_knowledge",
                "description": """Search stored knowledge before making decisions.

Use this to check:
- "Do I know user's preference for X?"
- "Have I learned about Y before?"
- "What's the context for project Z?"

Args:
    entity_type: Filter by type or "all" (default: "all")
    query: Search in keys (SQL LIKE pattern, e.g., "%test%")
    tags: Must have these tags
    limit: Max results (default: 10)

Returns:
    JSON list of matching knowledge entries

Example:
    # Before suggesting a test framework:
    search_knowledge(entity_type="user_preference", query="%test%")
""",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "entity_type": {
                            "type": "string",
                            "enum": [
                                "user_preference",
                                "lesson_learned",
                                "project_context",
                                "decision_rationale",
                                "all",
                            ],
                            "description": "Filter by entity type",
                            "default": "all",
                        },
                        "query": {
                            "type": "string",
                            "description": "Search pattern for keys (SQL LIKE, e.g., '%python%')",
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Filter by tags (must have all)",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum results to return",
                            "default": 10,
                            "minimum": 1,
                            "maximum": 100,
                        },
                    },
                    "required": [],
                },
                "_server": "internal",
                "_original_name": "search_knowledge",
            },
            {
                "name": "internal__trigger_synthesis",
                "description": """AGENT-ONLY: Trigger synthesis of conversation learnings.

Call this when you notice:
- User stated a preference about workflows/tools/style
- You learned a pattern or best practice from discussion
- User provided project context or goals
- A decision was made with clear rationale

The synthesis happens in background after your response.
User won't be interrupted.

Args:
    focus: What to synthesize (default: "all")
        - "all": everything
        - "preferences": only user preferences
        - "lessons": only lessons learned
        - "context": only project context

Returns:
    Confirmation that synthesis will run

Example:
    If user says "I prefer pytest", call this before responding.
""",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "focus": {
                            "type": "string",
                            "enum": ["all", "preferences", "lessons", "context"],
                            "description": "What to synthesize",
                            "default": "all",
                        }
                    },
                    "required": [],
                },
                "_server": "internal",
                "_original_name": "trigger_synthesis",
            },
        ]

    async def execute_tool(self, tool_name: str, arguments: dict) -> str:
        """Execute a knowledge management tool"""
        if tool_name == "save_knowledge":
            return await self.save_knowledge(
                entity_type=arguments["entity_type"],
                key=arguments["key"],
                content=arguments["content"],
                tags=arguments.get("tags", []),
                confidence=arguments.get("confidence", 1.0),
            )
        elif tool_name == "search_knowledge":
            return await self.search_knowledge(
                entity_type=arguments.get("entity_type", "all"),
                query=arguments.get("query"),
                tags=arguments.get("tags"),
                limit=arguments.get("limit", 10),
            )
        elif tool_name == "trigger_synthesis":
            return await self.trigger_synthesis(focus=arguments.get("focus", "all"))
        else:
            raise ValueError(f"Unknown knowledge tool: {tool_name}")

    async def save_knowledge(
        self,
        entity_type: Literal["user_preference", "lesson_learned", "project_context", "decision_rationale"],
        key: str,
        content: str,
        tags: list[str] | None = None,
        confidence: float = 1.0,
    ) -> str:
        """Save a piece of knowledge to the graph"""
        metadata = {
            "tags": tags or [],
            "source": "agent_direct_save",
            "saved_at": datetime.now().isoformat(),
        }

        entity_id = self.kg.insert_knowledge(
            entity_type=entity_type,
            key=key,
            content=content,
            metadata=metadata,
            confidence=confidence,
        )

        return f"✓ Saved {entity_type}: {key} (ID: {entity_id})"

    async def search_knowledge(
        self,
        entity_type: Literal[
            "user_preference",
            "lesson_learned",
            "project_context",
            "decision_rationale",
            "all",
        ] = "all",
        query: str | None = None,
        tags: list[str] | None = None,
        limit: int = 10,
    ) -> str:
        """Search stored knowledge"""
        type_filter = None if entity_type == "all" else entity_type

        results = self.kg.search_knowledge(entity_type=type_filter, key_pattern=query, tags=tags, limit=limit)

        if not results:
            return json.dumps({"results": [], "count": 0})

        return json.dumps(
            {
                "results": [
                    {
                        "type": r["entity_type"],
                        "key": r["key"],
                        "content": r["content"],
                        "tags": r["metadata"].get("tags", []),
                        "confidence": r["metadata"].get("confidence", 1.0),
                        "learned_at": r["learned_at"],
                    }
                    for r in results
                ],
                "count": len(results),
            },
            indent=2,
        )

    async def trigger_synthesis(self, focus: Literal["all", "preferences", "lessons", "context"] = "all") -> str:
        """Trigger synthesis of conversation learnings"""
        if self.agent is None:
            return "Error: Agent not set on KnowledgeTools"

        self.agent._pending_synthesis = {"focus": focus, "triggered_at": datetime.now()}

        return f"✓ Synthesis scheduled (focus: {focus}). Will run after this response completes."
