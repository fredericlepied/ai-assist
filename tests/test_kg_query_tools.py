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

    kg.insert_entity(
        entity_type="task",
        entity_id="task-old",
        valid_from=two_hours_ago,
        tx_from=two_hours_ago,
        data={"status": "done"},
    )

    kg.insert_entity(
        entity_type="task",
        entity_id="task-new",
        valid_from=thirty_min_ago,
        tx_from=thirty_min_ago,
        data={"status": "active"},
    )

    result = await tools.execute_tool("kg_recent_changes", {"hours": 1})
    data = json.loads(result)
    assert data["new_count"] == 1
    assert data["new_entities"][0]["id"] == "task-new"


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
        entity_type="event",
        entity_id="event-late",
        valid_from=datetime(2026, 2, 4, 10, 0),
        tx_from=datetime(2026, 2, 4, 10, 45),
        data={"status": "critical"},
    )

    kg.insert_entity(
        entity_type="event",
        entity_id="event-quick",
        valid_from=datetime(2026, 2, 4, 11, 0),
        tx_from=datetime(2026, 2, 4, 11, 5),
        data={"status": "critical"},
    )

    result = await tools.execute_tool("kg_late_discoveries", {"min_delay_minutes": 30})
    data = json.loads(result)
    assert data["count"] == 1
    assert data["discoveries"][0]["id"] == "event-late"


@pytest.mark.asyncio
async def test_kg_discovery_lag_stats_empty(tools):
    """Discovery lag stats on empty KG returns zero count"""
    result = await tools.execute_tool("kg_discovery_lag_stats", {"entity_type": "event"})
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
            entity_type="event",
            entity_id=f"event-{i}",
            valid_from=valid_time,
            tx_from=tx_time,
            data={"status": "critical"},
        )

    result = await tools.execute_tool("kg_discovery_lag_stats", {"entity_type": "event", "days": 7})
    data = json.loads(result)
    assert data["count"] == 5
    assert data["avg_lag_minutes"] > 0


@pytest.mark.asyncio
async def test_kg_entity_context_nonexistent(tools):
    """Entity context for non-existent entity returns not-found message"""
    result = await tools.execute_tool("kg_entity_context", {"entity_id": "no-such-entity"})
    data = json.loads(result)
    assert data["error"] == "not_found"


@pytest.mark.asyncio
async def test_kg_entity_context_with_related(kg, tools):
    """Entity context returns entity with related entities grouped by type"""
    kg.insert_entity(
        entity_type="task",
        entity_id="task-ctx",
        valid_from=datetime(2026, 2, 4, 10, 0),
        tx_from=datetime(2026, 2, 4, 10, 5),
        data={"status": "blocked"},
    )
    kg.insert_entity(
        entity_type="resource",
        entity_id="res-1",
        valid_from=datetime(2026, 2, 4, 0, 0),
        tx_from=datetime(2026, 2, 4, 0, 0),
        data={"name": "database-pool"},
    )
    kg.insert_entity(
        entity_type="person",
        entity_id="person-1",
        valid_from=datetime(2026, 2, 4, 12, 0),
        tx_from=datetime(2026, 2, 4, 12, 0),
        data={"name": "Alice"},
    )
    kg.insert_relationship(
        rel_type="depends_on",
        source_id="task-ctx",
        target_id="res-1",
        valid_from=datetime(2026, 2, 4, 10, 0),
    )
    kg.insert_relationship(
        rel_type="assigned_to",
        source_id="task-ctx",
        target_id="person-1",
        valid_from=datetime(2026, 2, 4, 12, 0),
    )

    result = await tools.execute_tool("kg_entity_context", {"entity_id": "task-ctx"})
    data = json.loads(result)
    assert data["id"] == "task-ctx"
    assert data["type"] == "task"
    assert len(data["related_by_type"]["resource"]) == 1
    assert len(data["related_by_type"]["person"]) == 1
    assert data["related_count"] == 2


@pytest.mark.asyncio
async def test_kg_stats(kg, tools):
    """KG stats returns entity and relationship counts"""
    kg.insert_entity(
        entity_type="task",
        entity_id="t1",
        valid_from=datetime.now(),
        data={"status": "active"},
    )
    kg.insert_entity(
        entity_type="person",
        entity_id="p1",
        valid_from=datetime.now(),
        data={"name": "Bob"},
    )

    result = await tools.execute_tool("kg_stats", {})
    data = json.loads(result)
    assert data["total_entities"] == 2
    assert data["entities_by_type"]["task"] == 1
    assert data["entities_by_type"]["person"] == 1


@pytest.mark.asyncio
async def test_execute_tool_unknown(tools):
    """Unknown tool name raises ValueError"""
    with pytest.raises(ValueError, match="Unknown KG query tool"):
        await tools.execute_tool("nonexistent_tool", {})
