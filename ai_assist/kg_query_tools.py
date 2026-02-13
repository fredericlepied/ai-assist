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
                            "description": "Optional filter by entity type (e.g., 'dci_job', 'jira_ticket')",
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
                    "Identifies monitoring lag — e.g., jobs that failed but weren't noticed for a while."
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
                            "description": "Entity type to analyze (e.g., 'dci_job')",
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
                "name": "internal__kg_job_context",
                "description": (
                    "AGENT-ONLY: Get a job with all related entities (components, tickets, etc.). "
                    "Provides full context for investigating a specific job."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "job_id": {
                            "type": "string",
                            "description": "The job entity ID in the knowledge graph",
                        },
                    },
                    "required": ["job_id"],
                },
                "_server": "internal",
                "_original_name": "kg_job_context",
            },
            {
                "name": "internal__kg_ticket_context",
                "description": (
                    "AGENT-ONLY: Get a ticket with all related jobs. " "Shows which jobs reference a given ticket."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "ticket_id": {
                            "type": "string",
                            "description": "The ticket entity ID in the knowledge graph",
                        },
                    },
                    "required": ["ticket_id"],
                },
                "_server": "internal",
                "_original_name": "kg_ticket_context",
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
                    "AGENT-ONLY: Detect failure trends in recent jobs. "
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
                    },
                    "required": [],
                },
                "_server": "internal",
                "_original_name": "kg_failure_trends",
            },
            {
                "name": "internal__kg_component_hotspots",
                "description": (
                    "AGENT-ONLY: Detect component hotspots — components appearing in multiple "
                    "failed jobs recently. Helps identify problematic components."
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
                        "min_failures": {
                            "type": "integer",
                            "description": "Minimum number of failed jobs to flag (default: 3)",
                            "default": 3,
                            "minimum": 1,
                        },
                    },
                    "required": [],
                },
                "_server": "internal",
                "_original_name": "kg_component_hotspots",
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
        elif tool_name == "kg_job_context":
            return self._job_context(arguments)
        elif tool_name == "kg_ticket_context":
            return self._ticket_context(arguments)
        elif tool_name == "kg_stats":
            return self._stats()
        elif tool_name == "kg_failure_trends":
            return self._failure_trends(arguments)
        elif tool_name == "kg_component_hotspots":
            return self._component_hotspots(arguments)
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

    def _job_context(self, arguments: dict[str, Any]) -> str:
        job_id = arguments["job_id"]
        result = self.queries.get_job_with_context(job_id)
        if result is None:
            return json.dumps({"error": "not_found", "job_id": job_id})
        return json.dumps(result, indent=2, default=str)

    def _ticket_context(self, arguments: dict[str, Any]) -> str:
        ticket_id = arguments["ticket_id"]
        result = self.queries.get_ticket_with_context(ticket_id)
        if result is None:
            return json.dumps({"error": "not_found", "ticket_id": ticket_id})
        return json.dumps(result, indent=2, default=str)

    def _stats(self) -> str:
        result = self.kg.get_stats()
        return json.dumps(result, indent=2, default=str)

    def _failure_trends(self, arguments: dict[str, Any]) -> str:
        days = arguments.get("days", 7)
        result = self.queries.detect_failure_trends(days=days)
        return json.dumps(result, indent=2, default=str)

    def _component_hotspots(self, arguments: dict[str, Any]) -> str:
        days = arguments.get("days", 7)
        min_failures = arguments.get("min_failures", 3)
        result = self.queries.detect_component_hotspots(days=days, min_failures=min_failures)
        return json.dumps(result, indent=2, default=str)
