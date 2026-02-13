"""Agent tools for querying the knowledge graph"""

import json
from typing import Any

from .kg_queries import KnowledgeGraphQueries
from .knowledge_graph import KnowledgeGraph


class KGQueryTools:
    """Tools exposing KG query capabilities to the agent"""

    def __init__(self, kg: KnowledgeGraph):
        self.kg = kg
        self.queries = KnowledgeGraphQueries(kg)

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """Get MCP-style tool definitions for KG query tools"""
        return [
            {
                "name": "internal__kg_recent_changes",
                "description": (
                    "AGENT-ONLY: Get recent changes in the knowledge graph. "
                    "Shows new entities discovered and corrected beliefs within a time window."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "hours": {
                            "type": "integer",
                            "description": "Number of hours to look back (default: 1)",
                            "default": 1,
                            "minimum": 1,
                        },
                        "entity_type": {
                            "type": "string",
                            "description": "Optional filter by entity type",
                        },
                    },
                    "required": [],
                },
                "_server": "internal",
                "_original_name": "kg_recent_changes",
            },
            {
                "name": "internal__kg_late_discoveries",
                "description": (
                    "AGENT-ONLY: Find entities discovered significantly after they became valid. "
                    "Identifies monitoring lag — entities that changed but weren't noticed promptly."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "min_delay_minutes": {
                            "type": "integer",
                            "description": "Minimum delay in minutes to consider 'late' (default: 30)",
                            "default": 30,
                            "minimum": 1,
                        },
                        "entity_type": {
                            "type": "string",
                            "description": "Optional filter by entity type",
                        },
                    },
                    "required": [],
                },
                "_server": "internal",
                "_original_name": "kg_late_discoveries",
            },
            {
                "name": "internal__kg_discovery_lag_stats",
                "description": (
                    "AGENT-ONLY: Analyze discovery lag statistics for an entity type. "
                    "Returns avg/min/max/percentile lag times."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "entity_type": {
                            "type": "string",
                            "description": "Entity type to analyze",
                        },
                        "days": {
                            "type": "integer",
                            "description": "Number of days to look back (default: 7)",
                            "default": 7,
                            "minimum": 1,
                        },
                    },
                    "required": ["entity_type"],
                },
                "_server": "internal",
                "_original_name": "kg_discovery_lag_stats",
            },
            {
                "name": "internal__kg_entity_context",
                "description": (
                    "AGENT-ONLY: Get an entity with all related entities, grouped by type. "
                    "Provides full context for investigating any entity in the knowledge graph."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "entity_id": {
                            "type": "string",
                            "description": "The entity ID in the knowledge graph",
                        },
                    },
                    "required": ["entity_id"],
                },
                "_server": "internal",
                "_original_name": "kg_entity_context",
            },
            {
                "name": "internal__kg_stats",
                "description": (
                    "AGENT-ONLY: Get knowledge graph statistics — entity counts by type, "
                    "relationship counts, and database info."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
                "_server": "internal",
                "_original_name": "kg_stats",
            },
            {
                "name": "internal__kg_failure_trends",
                "description": (
                    "AGENT-ONLY: Detect failure trends in recent entities. "
                    "Analyzes daily failure counts and identifies increasing/decreasing/stable trends."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "days": {
                            "type": "integer",
                            "description": "Number of days to analyze (default: 7)",
                            "default": 7,
                            "minimum": 1,
                        },
                        "entity_type": {
                            "type": "string",
                            "description": "Entity type to analyze (default: all types)",
                        },
                        "failure_statuses": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": 'Status values considered failures (default: ["failure", "error"])',
                        },
                    },
                    "required": [],
                },
                "_server": "internal",
                "_original_name": "kg_failure_trends",
            },
            {
                "name": "internal__kg_related_entity_hotspots",
                "description": (
                    "AGENT-ONLY: Detect related entities appearing in multiple failing entities. "
                    "Finds entities frequently associated with failures, helping identify root causes."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "days": {
                            "type": "integer",
                            "description": "Number of days to look back (default: 7)",
                            "default": 7,
                            "minimum": 1,
                        },
                        "min_occurrences": {
                            "type": "integer",
                            "description": "Minimum number of failing entities to flag (default: 3)",
                            "default": 3,
                            "minimum": 1,
                        },
                        "entity_type": {
                            "type": "string",
                            "description": "Type of the failing entities (default: all types)",
                        },
                        "failure_statuses": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": 'Status values considered failures (default: ["failure", "error"])',
                        },
                        "relationship_type": {
                            "type": "string",
                            "description": "Filter by relationship type (default: all)",
                        },
                    },
                    "required": [],
                },
                "_server": "internal",
                "_original_name": "kg_related_entity_hotspots",
            },
        ]

    async def execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """Execute a KG query tool and return JSON result"""
        if tool_name == "kg_recent_changes":
            return self._recent_changes(arguments)
        elif tool_name == "kg_late_discoveries":
            return self._late_discoveries(arguments)
        elif tool_name == "kg_discovery_lag_stats":
            return self._discovery_lag_stats(arguments)
        elif tool_name == "kg_entity_context":
            return self._entity_context(arguments)
        elif tool_name == "kg_stats":
            return self._stats()
        elif tool_name == "kg_failure_trends":
            return self._failure_trends(arguments)
        elif tool_name == "kg_related_entity_hotspots":
            return self._related_entity_hotspots(arguments)
        else:
            raise ValueError(f"Unknown KG query tool: {tool_name}")

    def _recent_changes(self, arguments: dict[str, Any]) -> str:
        hours = arguments.get("hours", 1)
        entity_type = arguments.get("entity_type")
        result = self.queries.what_changed_recently(hours=hours, entity_type=entity_type)
        return json.dumps(result, indent=2, default=str)

    def _late_discoveries(self, arguments: dict[str, Any]) -> str:
        min_delay = arguments.get("min_delay_minutes", 30)
        entity_type = arguments.get("entity_type")
        discoveries = self.queries.find_late_discoveries(min_delay_minutes=min_delay, entity_type=entity_type)
        return json.dumps(
            {"count": len(discoveries), "discoveries": discoveries},
            indent=2,
            default=str,
        )

    def _discovery_lag_stats(self, arguments: dict[str, Any]) -> str:
        entity_type = arguments["entity_type"]
        days = arguments.get("days", 7)
        result = self.queries.analyze_discovery_lag(entity_type=entity_type, days=days)
        return json.dumps(result, indent=2, default=str)

    def _entity_context(self, arguments: dict[str, Any]) -> str:
        entity_id = arguments["entity_id"]
        result = self.queries.get_entity_with_context(entity_id)
        if result is None:
            return json.dumps({"error": "not_found", "entity_id": entity_id})
        return json.dumps(result, indent=2, default=str)

    def _stats(self) -> str:
        result = self.kg.get_stats()
        return json.dumps(result, indent=2, default=str)

    def _failure_trends(self, arguments: dict[str, Any]) -> str:
        days = arguments.get("days", 7)
        entity_type = arguments.get("entity_type")
        failure_statuses = arguments.get("failure_statuses")
        result = self.queries.detect_failure_trends(
            days=days, entity_type=entity_type, failure_statuses=failure_statuses
        )
        return json.dumps(result, indent=2, default=str)

    def _related_entity_hotspots(self, arguments: dict[str, Any]) -> str:
        days = arguments.get("days", 7)
        min_occurrences = arguments.get("min_occurrences", 3)
        entity_type = arguments.get("entity_type")
        failure_statuses = arguments.get("failure_statuses")
        relationship_type = arguments.get("relationship_type")
        result = self.queries.detect_related_entity_hotspots(
            days=days,
            min_occurrences=min_occurrences,
            entity_type=entity_type,
            failure_statuses=failure_statuses,
            relationship_type=relationship_type,
        )
        return json.dumps(result, indent=2, default=str)
