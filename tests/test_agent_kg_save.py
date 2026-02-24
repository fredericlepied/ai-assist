"""Tests for agent knowledge graph auto-save (generic tool results)"""

import json
from datetime import datetime

import pytest

from ai_assist.agent import AiAssistAgent
from ai_assist.config import AiAssistConfig
from ai_assist.knowledge_graph import KnowledgeGraph


@pytest.fixture
def kg():
    """Create in-memory knowledge graph"""
    return KnowledgeGraph(":memory:")


@pytest.fixture
def agent_with_kg(kg):
    """Create agent with knowledge graph"""
    config = AiAssistConfig(anthropic_api_key="test-key", mcp_servers={})
    return AiAssistAgent(config, knowledge_graph=kg)


def test_agent_initializes_with_kg(kg):
    """Test agent accepts knowledge graph parameter"""
    config = AiAssistConfig(anthropic_api_key="test-key", mcp_servers={})
    agent = AiAssistAgent(config, knowledge_graph=kg)

    assert agent.knowledge_graph is kg
    assert agent.kg_save_enabled is True


def test_agent_initializes_without_kg():
    """Test agent works without knowledge graph"""
    config = AiAssistConfig(anthropic_api_key="test-key", mcp_servers={})
    agent = AiAssistAgent(config, knowledge_graph=None)

    assert agent.knowledge_graph is None
    assert agent.kg_save_enabled is True


def test_kg_save_can_be_toggled(agent_with_kg):
    """Test KG save can be enabled/disabled"""
    assert agent_with_kg.kg_save_enabled is True

    agent_with_kg.kg_save_enabled = False
    assert agent_with_kg.kg_save_enabled is False

    agent_with_kg.kg_save_enabled = True
    assert agent_with_kg.kg_save_enabled is True


def test_tool_calls_tracked(agent_with_kg):
    """Test tool calls are tracked in last_tool_calls"""
    assert len(agent_with_kg.last_tool_calls) == 0

    agent_with_kg.last_tool_calls.append(
        {
            "tool_name": "my_server__search_items",
            "arguments": {"query": "test"},
            "result": "test result",
            "timestamp": datetime.now(),
        }
    )

    assert len(agent_with_kg.last_tool_calls) == 1


def test_clear_tool_calls(agent_with_kg):
    """Test clearing tool calls"""
    agent_with_kg.last_tool_calls.append({"test": "data"})
    agent_with_kg.last_tool_calls.append({"test": "data2"})
    assert len(agent_with_kg.last_tool_calls) == 2

    agent_with_kg.clear_tool_calls()
    assert len(agent_with_kg.last_tool_calls) == 0


def test_get_last_kg_saved_count_zero(agent_with_kg):
    """Test getting saved count when nothing saved"""
    count = agent_with_kg.get_last_kg_saved_count()
    assert count == 0


def test_get_last_kg_saved_count_with_saves(agent_with_kg):
    """Test getting saved count when entities were saved"""
    agent_with_kg.last_tool_calls.append({"tool_name": "search_items", "kg_saved_count": 5})
    agent_with_kg.last_tool_calls.append({"tool_name": "get_ticket", "kg_saved_count": 3})

    count = agent_with_kg.get_last_kg_saved_count()
    assert count == 8


def test_get_last_kg_saved_count_mixed(agent_with_kg):
    """Test getting saved count with mixed results"""
    agent_with_kg.last_tool_calls.append({"tool_name": "search_items", "kg_saved_count": 5})
    agent_with_kg.last_tool_calls.append({"tool_name": "some_other_tool"})

    count = agent_with_kg.get_last_kg_saved_count()
    assert count == 5


@pytest.mark.asyncio
async def test_save_generic_json_result(agent_with_kg, kg):
    """Test saving any JSON tool result as a tool_result entity"""
    result = json.dumps({"name": "widget", "status": "active", "count": 42})

    agent_with_kg.last_tool_calls.append(
        {"tool_name": "server__get_widget", "arguments": {"id": "w1"}, "timestamp": datetime.now()}
    )

    await agent_with_kg._save_tool_result_to_kg(
        tool_name="server__get_widget",
        original_tool_name="get_widget",
        arguments={"id": "w1"},
        result_text=result,
    )

    # Verify entity was saved with generic type
    stats = kg.get_stats()
    assert stats["total_entities"] == 1

    # Verify the entity data
    entities = kg.query_as_of(datetime.now(), entity_type="tool_result")
    assert len(entities) == 1
    entity = entities[0]
    assert entity.entity_type == "tool_result"
    assert entity.data["tool_name"] == "get_widget"
    assert entity.data["arguments"] == {"id": "w1"}
    assert entity.data["result"]["name"] == "widget"
    assert entity.data["result"]["count"] == 42


@pytest.mark.asyncio
async def test_save_stores_original_tool_name_not_prefixed(agent_with_kg, kg):
    """Test that the MCP prefix is NOT stored — only the original tool name"""
    result = json.dumps({"key": "value"})

    agent_with_kg.last_tool_calls.append(
        {"tool_name": "myserver__fetch_data", "arguments": {}, "timestamp": datetime.now()}
    )

    await agent_with_kg._save_tool_result_to_kg(
        tool_name="myserver__fetch_data",
        original_tool_name="fetch_data",
        arguments={},
        result_text=result,
    )

    entities = kg.query_as_of(datetime.now(), entity_type="tool_result")
    assert len(entities) == 1
    # Must store "fetch_data", NOT "myserver__fetch_data"
    assert entities[0].data["tool_name"] == "fetch_data"
    assert "myserver" not in entities[0].id


@pytest.mark.asyncio
async def test_save_large_result_omits_data(agent_with_kg, kg):
    """Test that large results (>10000 chars) are stored without the result blob"""
    large_data = {"items": ["x" * 500 for _ in range(30)]}  # >10000 chars
    result = json.dumps(large_data)
    assert len(result) > 10000

    agent_with_kg.last_tool_calls.append(
        {"tool_name": "server__big_query", "arguments": {"q": "all"}, "timestamp": datetime.now()}
    )

    await agent_with_kg._save_tool_result_to_kg(
        tool_name="server__big_query",
        original_tool_name="big_query",
        arguments={"q": "all"},
        result_text=result,
    )

    entities = kg.query_as_of(datetime.now(), entity_type="tool_result")
    assert len(entities) == 1
    # Result should be None for large results
    assert entities[0].data["result"] is None
    # But tool name and arguments are still stored
    assert entities[0].data["tool_name"] == "big_query"
    assert entities[0].data["arguments"] == {"q": "all"}


@pytest.mark.asyncio
async def test_save_dedup_same_args(agent_with_kg, kg):
    """Test that same tool+args produces same entity_id (dedup)"""
    result = json.dumps({"value": 1})
    args = {"key": "abc"}

    agent_with_kg.last_tool_calls.append({"tool_name": "s__get_item", "arguments": args, "timestamp": datetime.now()})

    await agent_with_kg._save_tool_result_to_kg(
        tool_name="s__get_item", original_tool_name="get_item", arguments=args, result_text=result
    )

    # Call again with same args — should produce same entity_id
    agent_with_kg.last_tool_calls.append({"tool_name": "s__get_item", "arguments": args, "timestamp": datetime.now()})

    await agent_with_kg._save_tool_result_to_kg(
        tool_name="s__get_item", original_tool_name="get_item", arguments=args, result_text=result
    )

    # Should still be 1 entity (upsert by entity_id)
    stats = kg.get_stats()
    assert stats["total_entities"] == 1

    # Both calls should report kg_saved_count=1 (upsert always succeeds)
    assert agent_with_kg.last_tool_calls[0].get("kg_saved_count") == 1
    assert agent_with_kg.last_tool_calls[1].get("kg_saved_count") == 1


@pytest.mark.asyncio
async def test_save_disabled_when_kg_save_off(agent_with_kg, kg):
    """Test that KG save is skipped when disabled"""
    agent_with_kg.kg_save_enabled = False

    result = json.dumps({"key": "value"})

    await agent_with_kg._save_tool_result_to_kg(
        tool_name="server__get_data", original_tool_name="get_data", arguments={}, result_text=result
    )

    stats = kg.get_stats()
    assert stats["total_entities"] == 0


@pytest.mark.asyncio
async def test_save_skips_non_json(agent_with_kg, kg):
    """Test that non-JSON results are skipped"""
    await agent_with_kg._save_tool_result_to_kg(
        tool_name="server__get_data", original_tool_name="get_data", arguments={}, result_text="This is not JSON"
    )

    stats = kg.get_stats()
    assert stats["total_entities"] == 0


@pytest.mark.asyncio
async def test_save_skips_error_results(agent_with_kg, kg):
    """Test that error results are not saved"""
    await agent_with_kg._save_tool_result_to_kg(
        tool_name="server__get_data",
        original_tool_name="get_data",
        arguments={},
        result_text="Error: Something went wrong",
    )

    stats = kg.get_stats()
    assert stats["total_entities"] == 0


@pytest.mark.asyncio
async def test_save_skips_empty_result(agent_with_kg, kg):
    """Test that empty results are not saved"""
    await agent_with_kg._save_tool_result_to_kg(
        tool_name="server__get_data", original_tool_name="get_data", arguments={}, result_text=""
    )

    stats = kg.get_stats()
    assert stats["total_entities"] == 0


@pytest.mark.asyncio
async def test_save_tracks_count(agent_with_kg, kg):
    """Test that saved count is tracked in last_tool_calls"""
    result = json.dumps({"value": 1})

    agent_with_kg.last_tool_calls.append(
        {"tool_name": "server__get_data", "arguments": {}, "timestamp": datetime.now()}
    )

    await agent_with_kg._save_tool_result_to_kg(
        tool_name="server__get_data", original_tool_name="get_data", arguments={}, result_text=result
    )

    assert agent_with_kg.last_tool_calls[-1].get("kg_saved_count") == 1
