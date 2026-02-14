"""High-level query interface for the knowledge graph"""

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from .knowledge_graph import KnowledgeGraph


class KnowledgeGraphQueries:
    """High-level query interface for temporal and graph queries"""

    def __init__(self, kg: KnowledgeGraph):
        self.kg = kg

    def what_did_we_know_at(self, time: datetime, entity_type: str | None = None) -> list[dict[str, Any]]:
        """Query what ai-assist knew at a specific time

        Args:
            time: The transaction time to query
            entity_type: Optional filter by entity type

        Returns:
            List of entity dictionaries with their data
        """
        entities = self.kg.query_as_of(time, entity_type=entity_type)

        return [
            {
                "id": e.id,
                "type": e.entity_type,
                "data": e.data,
                "valid_from": e.valid_from.isoformat(),
                "known_since": e.tx_from.isoformat(),
            }
            for e in entities
        ]

    def what_changed_recently(self, hours: int = 1, entity_type: str | None = None) -> dict[str, Any]:
        """Get changes in the last N hours

        Args:
            hours: Number of hours to look back
            entity_type: Optional filter by entity type

        Returns:
            Dictionary with new entities and updated beliefs
        """
        cutoff = datetime.now() - timedelta(hours=hours)

        # Get all current entities
        current_entities = self.kg.query_as_of(datetime.now(), entity_type=entity_type)

        # Get entities as they were N hours ago
        previous_entities = self.kg.query_as_of(cutoff, entity_type=entity_type)

        # Build ID sets for comparison
        current_ids = {e.id for e in current_entities}
        previous_ids = {e.id for e in previous_entities}

        # New entities we learned about
        new_ids = current_ids - previous_ids
        new_entities = [e for e in current_entities if e.id in new_ids]

        # Entities we no longer believe (corrected)
        removed_ids = previous_ids - current_ids
        removed_entities = [e for e in previous_entities if e.id in removed_ids]

        return {
            "period_hours": hours,
            "new_count": len(new_entities),
            "new_entities": [
                {
                    "id": e.id,
                    "type": e.entity_type,
                    "data": e.data,
                    "discovered_at": e.tx_from.isoformat(),
                    "valid_from": e.valid_from.isoformat(),
                }
                for e in new_entities
            ],
            "corrected_count": len(removed_entities),
            "corrected_entities": [
                {"id": e.id, "type": e.entity_type, "was_believed": e.data} for e in removed_entities
            ],
        }

    def find_late_discoveries(
        self, min_delay_minutes: int = 30, entity_type: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Find entities discovered significantly after they became valid

        This identifies monitoring lag - jobs that failed but we didn't
        discover for a while.

        Args:
            min_delay_minutes: Minimum delay in minutes to consider "late"
            entity_type: Optional filter by entity type
            limit: Maximum number of results

        Returns:
            List of entities with discovery lag information
        """
        # Get all current entities
        entities = self.kg.query_as_of(datetime.now(), entity_type=entity_type, limit=limit)

        late_discoveries = []
        for entity in entities:
            # Calculate discovery lag
            lag_seconds = (entity.tx_from - entity.valid_from).total_seconds()
            lag_minutes = lag_seconds / 60

            if lag_minutes >= min_delay_minutes:
                late_discoveries.append(
                    {
                        "id": entity.id,
                        "type": entity.entity_type,
                        "data": entity.data,
                        "valid_from": entity.valid_from.isoformat(),
                        "discovered_at": entity.tx_from.isoformat(),
                        "lag_minutes": round(lag_minutes, 1),
                        "lag_human": self._format_duration(lag_seconds),
                    }
                )

        # Sort by lag (worst first)
        late_discoveries.sort(key=lambda x: float(str(x["lag_minutes"])), reverse=True)

        return late_discoveries

    def get_entity_with_context(self, entity_id: str) -> dict[str, Any] | None:
        """Get an entity with all related entities, grouped by type

        Args:
            entity_id: The entity ID

        Returns:
            Dictionary with entity data and related entities grouped by type
        """
        entity = self.kg.get_entity(entity_id)
        if not entity:
            return None

        # Get related entities
        related = self.kg.get_related_entities(entity_id, direction="both")

        # Group by entity type dynamically
        related_by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for rel, rel_entity in related:
            rel_info = {
                "entity_id": rel_entity.id,
                "entity_type": rel_entity.entity_type,
                "data": rel_entity.data,
                "valid_from": rel_entity.valid_from.isoformat(),
                "relationship": rel.rel_type,
                "properties": rel.properties,
            }
            related_by_type[rel_entity.entity_type].append(rel_info)

        # Calculate discovery lag
        lag_seconds = (entity.tx_from - entity.valid_from).total_seconds()

        return {
            "id": entity.id,
            "type": entity.entity_type,
            "data": entity.data,
            "valid_from": entity.valid_from.isoformat(),
            "valid_to": entity.valid_to.isoformat() if entity.valid_to else None,
            "discovered_at": entity.tx_from.isoformat(),
            "discovery_lag": self._format_duration(lag_seconds),
            "related_by_type": dict(related_by_type),
            "related_count": sum(len(v) for v in related_by_type.values()),
        }

    def analyze_discovery_lag(self, entity_type: str, days: int = 7) -> dict[str, Any]:
        """Analyze discovery lag statistics for an entity type

        Args:
            entity_type: Entity type to analyze
            days: Number of days to look back

        Returns:
            Statistics about discovery lag
        """
        cutoff = datetime.now() - timedelta(days=days)

        # Get all entities of this type discovered recently
        entities = self.kg.query_as_of(datetime.now(), entity_type=entity_type)

        # Filter to those discovered in the time window
        recent = [e for e in entities if e.tx_from >= cutoff]

        if not recent:
            return {
                "entity_type": entity_type,
                "period_days": days,
                "count": 0,
                "message": f"No {entity_type} entities discovered in the last {days} days",
            }

        # Calculate lags
        lags = [(e.tx_from - e.valid_from).total_seconds() for e in recent]
        lag_minutes = [lag / 60 for lag in lags]

        # Statistics
        avg_lag = sum(lag_minutes) / len(lag_minutes)
        min_lag = min(lag_minutes)
        max_lag = max(lag_minutes)

        # Percentiles
        sorted_lags = sorted(lag_minutes)
        p50_idx = len(sorted_lags) // 2
        p90_idx = int(len(sorted_lags) * 0.9)
        p95_idx = int(len(sorted_lags) * 0.95)

        return {
            "entity_type": entity_type,
            "period_days": days,
            "count": len(recent),
            "avg_lag_minutes": round(avg_lag, 1),
            "min_lag_minutes": round(min_lag, 1),
            "max_lag_minutes": round(max_lag, 1),
            "p50_lag_minutes": round(sorted_lags[p50_idx], 1),
            "p90_lag_minutes": round(sorted_lags[p90_idx], 1) if p90_idx < len(sorted_lags) else None,
            "p95_lag_minutes": round(sorted_lags[p95_idx], 1) if p95_idx < len(sorted_lags) else None,
            "avg_lag_human": self._format_duration(avg_lag * 60),
            "max_lag_human": self._format_duration(max_lag * 60),
        }

    @staticmethod
    def _format_duration(seconds: float) -> str:
        """Format duration in human-readable format

        Args:
            seconds: Duration in seconds

        Returns:
            Human-readable string like "5m 30s" or "2h 15m"
        """
        if seconds < 0:
            return "0s"

        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)

        parts = []
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        if secs > 0 or not parts:
            parts.append(f"{secs}s")

        return " ".join(parts)
