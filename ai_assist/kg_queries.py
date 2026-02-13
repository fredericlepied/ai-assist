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

    def get_job_with_context(self, job_id: str) -> dict[str, Any] | None:
        """Get a job with all related entities (components, tickets, etc.)

        Args:
            job_id: The job entity ID

        Returns:
            Dictionary with job data and all related entities
        """
        job = self.kg.get_entity(job_id)
        if not job:
            return None

        # Get related entities
        related = self.kg.get_related_entities(job_id, direction="both")

        # Organize by relationship type
        components = []
        tickets = []
        other = []

        for rel, entity in related:
            rel_info = {
                "entity_id": entity.id,
                "entity_type": entity.entity_type,
                "data": entity.data,
                "relationship": rel.rel_type,
                "properties": rel.properties,
            }

            if entity.entity_type == "component":
                components.append(rel_info)
            elif entity.entity_type == "jira_ticket":
                tickets.append(rel_info)
            else:
                other.append(rel_info)

        # Calculate discovery lag
        lag_seconds = (job.tx_from - job.valid_from).total_seconds()

        return {
            "id": job.id,
            "type": job.entity_type,
            "data": job.data,
            "valid_from": job.valid_from.isoformat(),
            "valid_to": job.valid_to.isoformat() if job.valid_to else None,
            "discovered_at": job.tx_from.isoformat(),
            "discovery_lag": self._format_duration(lag_seconds),
            "components": components,
            "tickets": tickets,
            "other_related": other,
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

    def get_ticket_with_context(self, ticket_id: str) -> dict[str, Any] | None:
        """Get a ticket with all related jobs

        Args:
            ticket_id: The ticket entity ID

        Returns:
            Dictionary with ticket data and related jobs
        """
        ticket = self.kg.get_entity(ticket_id)
        if not ticket:
            return None

        # Get related jobs (incoming relationships)
        related = self.kg.get_related_entities(ticket_id, direction="incoming")

        related_jobs = []
        for rel, entity in related:
            if entity.entity_type == "dci_job":
                related_jobs.append(
                    {
                        "job_id": entity.id,
                        "data": entity.data,
                        "valid_from": entity.valid_from.isoformat(),
                        "relationship": rel.rel_type,
                    }
                )

        return {
            "id": ticket.id,
            "type": ticket.entity_type,
            "data": ticket.data,
            "valid_from": ticket.valid_from.isoformat(),
            "discovered_at": ticket.tx_from.isoformat(),
            "related_jobs": related_jobs,
            "job_count": len(related_jobs),
        }

    def count_entities_by_status(
        self, entity_type: str = "dci_job", days: int = 7, group_by_day: bool = False
    ) -> dict[str, Any]:
        """Count entities grouped by status, optionally by day

        Args:
            entity_type: Entity type to count (default: 'dci_job')
            days: Number of days to look back
            group_by_day: If True, break down counts by day

        Returns:
            Dictionary with status counts and optional daily breakdown
        """
        cutoff = datetime.now() - timedelta(days=days)
        entities = self.kg.query_as_of(datetime.now(), entity_type=entity_type)
        recent = [e for e in entities if e.tx_from >= cutoff]

        # Count by status
        status_counts: dict[str, int] = defaultdict(int)
        for e in recent:
            status = e.data.get("status", "unknown")
            status_counts[status] += 1

        result: dict[str, Any] = {
            "entity_type": entity_type,
            "period_days": days,
            "total": len(recent),
            "by_status": dict(status_counts),
        }

        if group_by_day:
            by_day: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
            for e in recent:
                day_key = e.valid_from.strftime("%Y-%m-%d")
                status = e.data.get("status", "unknown")
                by_day[day_key][status] += 1
            result["by_day"] = {k: dict(v) for k, v in sorted(by_day.items())}

        return result

    def detect_failure_trends(self, days: int = 7) -> dict[str, Any]:
        """Detect trends in job failures over recent days

        Compares daily failure counts to identify increasing, decreasing,
        or stable trends.

        Args:
            days: Number of days to analyze

        Returns:
            Dictionary with daily counts and trend analysis
        """
        counts = self.count_entities_by_status("dci_job", days=days, group_by_day=True)

        by_day = counts.get("by_day", {})
        if not by_day:
            return {
                "period_days": days,
                "daily_counts": {},
                "trend": "no_data",
                "message": f"No jobs found in the last {days} days",
            }

        # Extract daily failure counts
        daily_failures: dict[str, int] = {}
        for day_key in sorted(by_day.keys()):
            day_statuses = by_day[day_key]
            failures = day_statuses.get("failure", 0) + day_statuses.get("error", 0)
            daily_failures[day_key] = failures

        # Determine trend from sorted daily counts
        failure_values = list(daily_failures.values())
        if len(failure_values) < 2:
            trend = "insufficient_data"
        else:
            # Compare first half vs second half averages
            mid = len(failure_values) // 2
            first_half_avg = sum(failure_values[:mid]) / max(mid, 1)
            second_half_avg = sum(failure_values[mid:]) / max(len(failure_values) - mid, 1)

            if second_half_avg > first_half_avg * 1.3:
                trend = "increasing"
            elif second_half_avg < first_half_avg * 0.7:
                trend = "decreasing"
            else:
                trend = "stable"

        return {
            "period_days": days,
            "daily_counts": daily_failures,
            "total_failures": sum(daily_failures.values()),
            "trend": trend,
        }

    def detect_component_hotspots(self, days: int = 7, min_failures: int = 3) -> dict[str, Any]:
        """Detect components appearing in multiple failed jobs

        Args:
            days: Number of days to look back
            min_failures: Minimum failed jobs to flag a component (default: 3)

        Returns:
            Dictionary with hotspot components and their failure counts
        """
        cutoff = datetime.now() - timedelta(days=days)

        # Get recent failed jobs
        entities = self.kg.query_as_of(datetime.now(), entity_type="dci_job")
        failed_jobs = [e for e in entities if e.tx_from >= cutoff and e.data.get("status") in ("failure", "error")]

        # Count component appearances in failed jobs
        component_failures: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "job_ids": [], "data": {}})
        for job in failed_jobs:
            related = self.kg.get_related_entities(job.id, rel_type="job_uses_component")
            for _rel, comp in related:
                info = component_failures[comp.id]
                info["count"] += 1
                info["job_ids"].append(job.id)
                info["data"] = comp.data

        # Filter to hotspots
        hotspots = [
            {
                "component_id": comp_id,
                "data": info["data"],
                "failure_count": info["count"],
                "job_ids": info["job_ids"],
            }
            for comp_id, info in component_failures.items()
            if info["count"] >= min_failures
        ]

        # Sort by failure count descending
        hotspots.sort(key=lambda x: x["failure_count"], reverse=True)

        return {
            "period_days": days,
            "min_failures": min_failures,
            "hotspots": hotspots,
            "total_failed_jobs": len(failed_jobs),
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
