"""Tests for KG query tools exposed to the agent"""

import json
from datetime import datetime, timedelta

import pytest

from ai_assist.kg_query_tools import KGQueryTools
from ai_assist.knowledge_graph import KnowledgeGraph


@pytest.fixture
def kg():
    """Create in-memory knowledge graph for testing"""
    graph = KnowledgeGraph(db_path=":memory:")
    yield graph
    graph.close()


@pytest.fixture
def tools(kg):
    """Create KGQueryTools instance"""
    return KGQueryTools(kg)


# === Phase 1: Tracer bullet — internal__kg_recent_changes ===


def test_get_tool_definitions_returns_list(tools):
    """Tool definitions are a non-empty list of valid dicts"""
    defs = tools.get_tool_definitions()
    assert isinstance(defs, list)
    assert len(defs) > 0
    for d in defs:
        assert "name" in d
        assert "description" in d
        assert "input_schema" in d
        assert d["name"].startswith("internal__kg_")
        assert d.get("_server") == "internal"


@pytest.mark.asyncio
async def test_kg_recent_changes_empty_kg(tools):
    """Recent changes on empty KG returns valid JSON with zero counts"""
    result = await tools.execute_tool("kg_recent_changes", {"hours": 1})
    data = json.loads(result)
    assert data["new_count"] == 0
    assert data["corrected_count"] == 0


@pytest.mark.asyncio
async def test_kg_recent_changes_with_data(kg, tools):
    """Recent changes returns entities added within the time window"""
    now = datetime.now()
    thirty_min_ago = now - timedelta(minutes=30)
    two_hours_ago = now - timedelta(hours=2)

    # Old entity
    kg.insert_entity(
        entity_type="dci_job",
        entity_id="job-old",
        valid_from=two_hours_ago,
        tx_from=two_hours_ago,
        data={"status": "success"},
    )

    # Recent entity
    kg.insert_entity(
        entity_type="dci_job",
        entity_id="job-new",
        valid_from=thirty_min_ago,
        tx_from=thirty_min_ago,
        data={"status": "failure"},
    )

    result = await tools.execute_tool("kg_recent_changes", {"hours": 1})
    data = json.loads(result)
    assert data["new_count"] == 1
    assert data["new_entities"][0]["id"] == "job-new"


# === Phase 2: Remaining query tools ===


@pytest.mark.asyncio
async def test_kg_late_discoveries_empty(tools):
    """Late discoveries on empty KG returns empty list"""
    result = await tools.execute_tool("kg_late_discoveries", {})
    data = json.loads(result)
    assert data["count"] == 0
    assert data["discoveries"] == []


@pytest.mark.asyncio
async def test_kg_late_discoveries_with_data(kg, tools):
    """Late discoveries returns entities discovered late"""
    kg.insert_entity(
        entity_type="dci_job",
        entity_id="job-late",
        valid_from=datetime(2026, 2, 4, 10, 0),
        tx_from=datetime(2026, 2, 4, 10, 45),
        data={"status": "failure"},
    )

    kg.insert_entity(
        entity_type="dci_job",
        entity_id="job-quick",
        valid_from=datetime(2026, 2, 4, 11, 0),
        tx_from=datetime(2026, 2, 4, 11, 5),
        data={"status": "failure"},
    )

    result = await tools.execute_tool("kg_late_discoveries", {"min_delay_minutes": 30})
    data = json.loads(result)
    assert data["count"] == 1
    assert data["discoveries"][0]["id"] == "job-late"


@pytest.mark.asyncio
async def test_kg_discovery_lag_stats_empty(tools):
    """Discovery lag stats on empty KG returns zero count"""
    result = await tools.execute_tool("kg_discovery_lag_stats", {"entity_type": "dci_job"})
    data = json.loads(result)
    assert data["count"] == 0


@pytest.mark.asyncio
async def test_kg_discovery_lag_stats_with_data(kg, tools):
    """Discovery lag stats returns statistics"""
    base_time = datetime.now() - timedelta(hours=2)

    for i in range(5):
        valid_time = base_time + timedelta(minutes=i * 10)
        tx_time = valid_time + timedelta(minutes=5 + i)
        kg.insert_entity(
            entity_type="dci_job",
            entity_id=f"job-{i}",
            valid_from=valid_time,
            tx_from=tx_time,
            data={"status": "failure"},
        )

    result = await tools.execute_tool("kg_discovery_lag_stats", {"entity_type": "dci_job", "days": 7})
    data = json.loads(result)
    assert data["count"] == 5
    assert data["avg_lag_minutes"] > 0


@pytest.mark.asyncio
async def test_kg_job_context_nonexistent(tools):
    """Job context for non-existent job returns not-found message"""
    result = await tools.execute_tool("kg_job_context", {"job_id": "no-such-job"})
    data = json.loads(result)
    assert data["error"] == "not_found"


@pytest.mark.asyncio
async def test_kg_job_context_with_related(kg, tools):
    """Job context returns job with related entities"""
    kg.insert_entity(
        entity_type="dci_job",
        entity_id="job-ctx",
        valid_from=datetime(2026, 2, 4, 10, 0),
        tx_from=datetime(2026, 2, 4, 10, 5),
        data={"status": "failure"},
    )
    kg.insert_entity(
        entity_type="component",
        entity_id="comp-1",
        valid_from=datetime(2026, 2, 4, 0, 0),
        tx_from=datetime(2026, 2, 4, 0, 0),
        data={"type": "ocp", "version": "4.19.0"},
    )
    kg.insert_relationship(
        rel_type="job_uses_component",
        source_id="job-ctx",
        target_id="comp-1",
        valid_from=datetime(2026, 2, 4, 10, 0),
    )

    result = await tools.execute_tool("kg_job_context", {"job_id": "job-ctx"})
    data = json.loads(result)
    assert data["id"] == "job-ctx"
    assert len(data["components"]) == 1


@pytest.mark.asyncio
async def test_kg_ticket_context_nonexistent(tools):
    """Ticket context for non-existent ticket returns not-found message"""
    result = await tools.execute_tool("kg_ticket_context", {"ticket_id": "no-such-ticket"})
    data = json.loads(result)
    assert data["error"] == "not_found"


@pytest.mark.asyncio
async def test_kg_ticket_context_with_related(kg, tools):
    """Ticket context returns ticket with related jobs"""
    kg.insert_entity(
        entity_type="jira_ticket",
        entity_id="ticket-t1",
        valid_from=datetime(2026, 2, 4, 12, 0),
        tx_from=datetime(2026, 2, 4, 12, 0),
        data={"key": "CILAB-100"},
    )
    kg.insert_entity(
        entity_type="dci_job",
        entity_id="job-t1",
        valid_from=datetime(2026, 2, 4, 10, 0),
        tx_from=datetime(2026, 2, 4, 10, 5),
        data={"status": "failure"},
    )
    kg.insert_relationship(
        rel_type="job_references_ticket",
        source_id="job-t1",
        target_id="ticket-t1",
        valid_from=datetime(2026, 2, 4, 12, 0),
    )

    result = await tools.execute_tool("kg_ticket_context", {"ticket_id": "ticket-t1"})
    data = json.loads(result)
    assert data["id"] == "ticket-t1"
    assert data["job_count"] == 1


@pytest.mark.asyncio
async def test_kg_stats(kg, tools):
    """KG stats returns entity and relationship counts"""
    kg.insert_entity(
        entity_type="dci_job",
        entity_id="j1",
        valid_from=datetime.now(),
        data={"status": "success"},
    )
    kg.insert_entity(
        entity_type="jira_ticket",
        entity_id="t1",
        valid_from=datetime.now(),
        data={"key": "X-1"},
    )

    result = await tools.execute_tool("kg_stats", {})
    data = json.loads(result)
    assert data["total_entities"] == 2
    assert data["entities_by_type"]["dci_job"] == 1
    assert data["entities_by_type"]["jira_ticket"] == 1


# === Phase 3: Insight detection tools ===


@pytest.mark.asyncio
async def test_kg_failure_trends(kg, tools):
    """Failure trends tool returns valid JSON"""
    now = datetime.now()
    # Insert jobs across 3 days with increasing failures
    for day_offset in range(3):
        day = now - timedelta(days=day_offset)
        # More failures on recent days
        for i in range(day_offset + 1):
            kg.insert_entity(
                entity_type="dci_job",
                entity_id=f"job-d{day_offset}-{i}",
                valid_from=day,
                tx_from=day,
                data={"status": "failure"},
            )

    result = await tools.execute_tool("kg_failure_trends", {"days": 7})
    data = json.loads(result)
    assert "daily_counts" in data
    assert "trend" in data


@pytest.mark.asyncio
async def test_kg_component_hotspots(kg, tools):
    """Component hotspots tool returns valid JSON"""
    now = datetime.now()

    # Create a component
    kg.insert_entity(
        entity_type="component",
        entity_id="comp-hot",
        valid_from=now - timedelta(days=5),
        tx_from=now - timedelta(days=5),
        data={"type": "ocp", "version": "4.19.0"},
    )

    # Create 3 failed jobs using that component
    for i in range(3):
        job_time = now - timedelta(days=i)
        kg.insert_entity(
            entity_type="dci_job",
            entity_id=f"job-hot-{i}",
            valid_from=job_time,
            tx_from=job_time,
            data={"status": "failure"},
        )
        kg.insert_relationship(
            rel_type="job_uses_component",
            source_id=f"job-hot-{i}",
            target_id="comp-hot",
            valid_from=job_time,
        )

    result = await tools.execute_tool("kg_component_hotspots", {"days": 7})
    data = json.loads(result)
    assert "hotspots" in data


@pytest.mark.asyncio
async def test_execute_tool_unknown(tools):
    """Unknown tool name raises ValueError"""
    with pytest.raises(ValueError, match="Unknown KG query tool"):
        await tools.execute_tool("nonexistent_tool", {})
