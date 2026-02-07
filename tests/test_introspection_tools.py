"""Tests for introspection tools"""

import json
from datetime import datetime, timedelta

import pytest

from ai_assist.context import ConversationMemory
from ai_assist.introspection_tools import IntrospectionTools
from ai_assist.knowledge_graph import KnowledgeGraph


@pytest.fixture
def kg():
    """Create in-memory knowledge graph"""
    return KnowledgeGraph(":memory:")


@pytest.fixture
def conversation_memory():
    """Create conversation memory"""
    return ConversationMemory(max_exchanges=10)


@pytest.fixture
def introspection_tools_with_kg(kg):
    """Create introspection tools with KG"""
    return IntrospectionTools(knowledge_graph=kg)


@pytest.fixture
def introspection_tools_full(kg, conversation_memory):
    """Create introspection tools with both KG and conversation memory"""
    return IntrospectionTools(knowledge_graph=kg, conversation_memory=conversation_memory)


def test_initialization_with_kg(kg):
    """Test introspection tools initialize with KG"""
    tools = IntrospectionTools(knowledge_graph=kg)
    assert tools.knowledge_graph is kg
    assert tools.conversation_memory is None


def test_initialization_with_both(kg, conversation_memory):
    """Test introspection tools initialize with both KG and conversation"""
    tools = IntrospectionTools(knowledge_graph=kg, conversation_memory=conversation_memory)
    assert tools.knowledge_graph is kg
    assert tools.conversation_memory is conversation_memory


def test_get_tool_definitions_with_kg(introspection_tools_with_kg):
    """Test tool definitions with KG only"""
    tools_defs = introspection_tools_with_kg.get_tool_definitions()

    # Should have 3 KG tools + 1 MCP prompt inspection tool
    assert len(tools_defs) == 4

    tool_names = [t["name"] for t in tools_defs]
    assert "introspection__search_knowledge_graph" in tool_names
    assert "introspection__get_kg_entity" in tool_names
    assert "introspection__get_kg_stats" in tool_names
    assert "introspection__inspect_mcp_prompt" in tool_names

    # All should be from introspection server
    for tool in tools_defs:
        assert tool["_server"] == "introspection"


def test_get_tool_definitions_with_both(introspection_tools_full):
    """Test tool definitions with both KG and conversation"""
    tools_defs = introspection_tools_full.get_tool_definitions()

    # Should have 3 KG + 1 MCP prompt inspection + 1 conversation
    assert len(tools_defs) == 5

    tool_names = [t["name"] for t in tools_defs]
    assert "introspection__search_knowledge_graph" in tool_names
    assert "introspection__get_kg_entity" in tool_names
    assert "introspection__get_kg_stats" in tool_names
    assert "introspection__inspect_mcp_prompt" in tool_names
    assert "introspection__search_conversation_history" in tool_names


def test_tool_definitions_have_schemas(introspection_tools_full):
    """Test all tool definitions have proper schemas"""
    tools_defs = introspection_tools_full.get_tool_definitions()

    for tool in tools_defs:
        assert "name" in tool
        assert "description" in tool
        assert "input_schema" in tool
        assert tool["description"]  # Not empty


@pytest.mark.asyncio
async def test_search_kg_by_type(introspection_tools_with_kg, kg):
    """Test searching KG by entity type"""
    # Add some entities
    for i in range(5):
        kg.insert_entity(
            entity_type="jira_ticket",
            entity_id=f"CILAB-{i}",
            valid_from=datetime.now(),
            data={"key": f"CILAB-{i}", "summary": f"Issue {i}"},
        )

    result = await introspection_tools_with_kg.execute_tool(
        "search_knowledge_graph", {"entity_type": "jira_ticket", "limit": 10}
    )

    data = json.loads(result)
    assert data["found"] == 5
    assert len(data["entities"]) == 5


@pytest.mark.asyncio
async def test_search_kg_with_time_range(introspection_tools_with_kg, kg):
    """Test searching KG with time range"""
    # Add old entity
    kg.insert_entity(
        entity_type="dci_job",
        entity_id="job-old",
        valid_from=datetime.now() - timedelta(hours=48),
        data={"status": "success"},
    )

    # Add recent entity
    kg.insert_entity(
        entity_type="dci_job",
        entity_id="job-recent",
        valid_from=datetime.now() - timedelta(hours=1),
        data={"status": "failure"},
    )

    result = await introspection_tools_with_kg.execute_tool(
        "search_knowledge_graph", {"entity_type": "dci_job", "time_range_hours": 24, "limit": 10}
    )

    data = json.loads(result)
    assert data["found"] == 1
    assert data["entities"][0]["id"] == "job-recent"


@pytest.mark.asyncio
async def test_search_kg_with_limit(introspection_tools_with_kg, kg):
    """Test search limit enforcement"""
    # Add many entities
    for i in range(20):
        kg.insert_entity(
            entity_type="jira_ticket", entity_id=f"CILAB-{i}", valid_from=datetime.now(), data={"key": f"CILAB-{i}"}
        )

    result = await introspection_tools_with_kg.execute_tool(
        "search_knowledge_graph", {"entity_type": "jira_ticket", "limit": 5}
    )

    data = json.loads(result)
    assert data["found"] == 5


@pytest.mark.asyncio
async def test_get_kg_entity_found(introspection_tools_with_kg, kg):
    """Test getting a specific entity"""
    kg.insert_entity(
        entity_type="jira_ticket",
        entity_id="CILAB-123",
        valid_from=datetime.now(),
        data={"key": "CILAB-123", "summary": "Test issue", "status": "Open"},
    )

    result = await introspection_tools_with_kg.execute_tool("get_kg_entity", {"entity_id": "CILAB-123"})

    data = json.loads(result)
    assert data["found"] is True
    assert data["entity"]["id"] == "CILAB-123"
    assert data["entity"]["data"]["summary"] == "Test issue"


@pytest.mark.asyncio
async def test_get_kg_entity_not_found(introspection_tools_with_kg, kg):
    """Test getting non-existent entity"""
    result = await introspection_tools_with_kg.execute_tool("get_kg_entity", {"entity_id": "CILAB-999"})

    data = json.loads(result)
    assert data["found"] is False


@pytest.mark.asyncio
async def test_get_kg_entity_with_relationships(introspection_tools_with_kg, kg):
    """Test getting entity with its relationships"""
    # Add job
    kg.insert_entity(entity_type="dci_job", entity_id="job-1", valid_from=datetime.now(), data={"status": "success"})

    # Add component
    kg.insert_entity(
        entity_type="dci_component", entity_id="comp-1", valid_from=datetime.now(), data={"version": "4.19.0"}
    )

    # Add relationship
    kg.insert_relationship(
        rel_type="job_uses_component", source_id="job-1", target_id="comp-1", valid_from=datetime.now()
    )

    result = await introspection_tools_with_kg.execute_tool("get_kg_entity", {"entity_id": "job-1"})

    data = json.loads(result)
    assert data["found"] is True
    assert len(data["related_entities"]) == 1
    assert data["related_entities"][0]["relationship"] == "job_uses_component"


@pytest.mark.asyncio
async def test_get_kg_stats(introspection_tools_with_kg, kg):
    """Test getting KG statistics"""
    # Add some entities
    kg.insert_entity(entity_type="jira_ticket", entity_id="CILAB-1", valid_from=datetime.now(), data={})
    kg.insert_entity(entity_type="dci_job", entity_id="job-1", valid_from=datetime.now(), data={})

    result = await introspection_tools_with_kg.execute_tool("get_kg_stats", {})

    data = json.loads(result)
    assert data["total_entities"] == 2
    assert "jira_ticket" in data["entities_by_type"]
    assert "dci_job" in data["entities_by_type"]


@pytest.mark.asyncio
async def test_search_conversation_history(introspection_tools_full):
    """Test searching conversation history"""
    # Add some exchanges
    introspection_tools_full.conversation_memory.add_exchange("What DCI jobs failed?", "Here are 5 failed jobs...")
    introspection_tools_full.conversation_memory.add_exchange(
        "Why did they fail?", "The failures were due to network issues..."
    )

    result = await introspection_tools_full.execute_tool("search_conversation_history", {"search_term": "failed"})

    data = json.loads(result)
    # Only first exchange contains exact substring "failed"
    # Second has "fail" and "failures" but not "failed"
    assert data["found"] == 1


@pytest.mark.asyncio
async def test_search_conversation_no_matches(introspection_tools_full):
    """Test conversation search with no matches"""
    introspection_tools_full.conversation_memory.add_exchange("Hello", "Hi there!")

    result = await introspection_tools_full.execute_tool("search_conversation_history", {"search_term": "kubernetes"})

    data = json.loads(result)
    assert data["found"] == 0


@pytest.mark.asyncio
async def test_search_conversation_case_insensitive(introspection_tools_full):
    """Test conversation search is case insensitive"""
    introspection_tools_full.conversation_memory.add_exchange("What about OpenShift?", "OpenShift is working fine.")

    result = await introspection_tools_full.execute_tool(
        "search_conversation_history", {"search_term": "openshift"}  # lowercase
    )

    data = json.loads(result)
    assert data["found"] == 1


@pytest.mark.asyncio
async def test_tool_without_kg(conversation_memory):
    """Test KG tools fail gracefully without KG"""
    tools = IntrospectionTools(knowledge_graph=None, conversation_memory=conversation_memory)

    result = await tools.execute_tool("search_knowledge_graph", {"entity_type": "jira_ticket"})

    data = json.loads(result)
    assert "error" in data
    assert "not available" in data["error"].lower()


@pytest.mark.asyncio
async def test_tool_without_conversation(kg):
    """Test conversation tool fails gracefully without conversation memory"""
    tools = IntrospectionTools(knowledge_graph=kg, conversation_memory=None)

    result = await tools.execute_tool("search_conversation_history", {"search_term": "test"})

    data = json.loads(result)
    assert "error" in data
    assert "not available" in data["error"].lower()


@pytest.mark.asyncio
async def test_unknown_tool(introspection_tools_full):
    """Test calling unknown tool returns error"""
    result = await introspection_tools_full.execute_tool("unknown_tool", {})

    data = json.loads(result)
    assert "error" in data
