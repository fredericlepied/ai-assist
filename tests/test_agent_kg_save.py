"""Tests for agent knowledge graph auto-save"""

import pytest
from datetime import datetime
from boss.agent import BossAgent
from boss.config import BossConfig
from boss.knowledge_graph import KnowledgeGraph


@pytest.fixture
def kg():
    """Create in-memory knowledge graph"""
    return KnowledgeGraph(":memory:")


@pytest.fixture
def agent_with_kg(kg):
    """Create agent with knowledge graph"""
    config = BossConfig(
        anthropic_api_key="test-key",
        mcp_servers={}
    )
    return BossAgent(config, knowledge_graph=kg)


def test_agent_initializes_with_kg(kg):
    """Test agent accepts knowledge graph parameter"""
    config = BossConfig(anthropic_api_key="test-key", mcp_servers={})
    agent = BossAgent(config, knowledge_graph=kg)

    assert agent.knowledge_graph is kg
    assert agent.kg_save_enabled is True


def test_agent_initializes_without_kg():
    """Test agent works without knowledge graph"""
    config = BossConfig(anthropic_api_key="test-key", mcp_servers={})
    agent = BossAgent(config, knowledge_graph=None)

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
    # Initially empty
    assert len(agent_with_kg.last_tool_calls) == 0

    # Add a mock tool call
    agent_with_kg.last_tool_calls.append({
        "tool_name": "dci__search_dci_jobs",
        "arguments": {"query": "test"},
        "result": "test result",
        "timestamp": datetime.now()
    })

    assert len(agent_with_kg.last_tool_calls) == 1


def test_clear_tool_calls(agent_with_kg):
    """Test clearing tool calls"""
    # Add some calls
    agent_with_kg.last_tool_calls.append({"test": "data"})
    agent_with_kg.last_tool_calls.append({"test": "data2"})
    assert len(agent_with_kg.last_tool_calls) == 2

    # Clear
    agent_with_kg.clear_tool_calls()
    assert len(agent_with_kg.last_tool_calls) == 0


def test_get_last_kg_saved_count_zero(agent_with_kg):
    """Test getting saved count when nothing saved"""
    count = agent_with_kg.get_last_kg_saved_count()
    assert count == 0


def test_get_last_kg_saved_count_with_saves(agent_with_kg):
    """Test getting saved count when entities were saved"""
    # Add tool calls with saved counts
    agent_with_kg.last_tool_calls.append({
        "tool_name": "dci__search_dci_jobs",
        "kg_saved_count": 5
    })
    agent_with_kg.last_tool_calls.append({
        "tool_name": "dci__search_jira_tickets",
        "kg_saved_count": 3
    })

    count = agent_with_kg.get_last_kg_saved_count()
    assert count == 8  # 5 + 3


def test_get_last_kg_saved_count_mixed(agent_with_kg):
    """Test getting saved count with mixed results"""
    # Some with saves, some without
    agent_with_kg.last_tool_calls.append({
        "tool_name": "dci__search_dci_jobs",
        "kg_saved_count": 5
    })
    agent_with_kg.last_tool_calls.append({
        "tool_name": "some__other_tool"
        # No kg_saved_count
    })

    count = agent_with_kg.get_last_kg_saved_count()
    assert count == 5


@pytest.mark.asyncio
async def test_save_jira_result_to_kg(agent_with_kg, kg):
    """Test saving Jira ticket result to KG"""
    # Mock Jira API response
    jira_result = '''
    {
        "key": "CILAB-123",
        "fields": {
            "summary": "Test issue",
            "status": {"name": "Open"},
            "priority": {"name": "High"},
            "project": {"key": "CILAB"},
            "created": "2026-02-01T10:00:00Z"
        }
    }
    '''

    # Call the save method
    await agent_with_kg._save_tool_result_to_kg(
        tool_name="dci__get_jira_ticket",
        original_tool_name="get_jira_ticket",
        arguments={"ticket_key": "CILAB-123"},
        result_text=jira_result
    )

    # Verify entity was saved
    entity = kg.get_entity("CILAB-123")
    assert entity is not None
    assert entity.entity_type == "jira_ticket"
    assert entity.data["key"] == "CILAB-123"
    assert entity.data["summary"] == "Test issue"
    assert entity.data["status"] == "Open"


@pytest.mark.asyncio
async def test_save_jira_list_to_kg(agent_with_kg, kg):
    """Test saving list of Jira tickets to KG"""
    jira_result = '''
    {
        "issues": [
            {
                "key": "CILAB-1",
                "fields": {
                    "summary": "Issue 1",
                    "status": {"name": "Open"},
                    "project": {"key": "CILAB"},
                    "created": "2026-02-01T10:00:00Z"
                }
            },
            {
                "key": "CILAB-2",
                "fields": {
                    "summary": "Issue 2",
                    "status": {"name": "Closed"},
                    "project": {"key": "CILAB"},
                    "created": "2026-02-01T11:00:00Z"
                }
            }
        ]
    }
    '''

    await agent_with_kg._save_tool_result_to_kg(
        tool_name="dci__search_jira_tickets",
        original_tool_name="search_jira_tickets",
        arguments={"jql": "project=CILAB"},
        result_text=jira_result
    )

    # Verify both entities saved
    entity1 = kg.get_entity("CILAB-1")
    entity2 = kg.get_entity("CILAB-2")

    assert entity1 is not None
    assert entity2 is not None
    assert entity1.data["summary"] == "Issue 1"
    assert entity2.data["summary"] == "Issue 2"


@pytest.mark.asyncio
async def test_save_dci_job_to_kg(agent_with_kg, kg):
    """Test saving DCI job to KG"""
    dci_result = '''
    {
        "hits": [
            {
                "id": "job-123",
                "status": "failure",
                "created_at": "2026-02-01T10:00:00Z",
                "remoteci_id": "rci-1",
                "topic_id": "topic-1",
                "state": "error",
                "components": [
                    {
                        "id": "comp-1",
                        "type": "ocp",
                        "version": "4.19.0",
                        "name": "OpenShift"
                    }
                ]
            }
        ]
    }
    '''

    await agent_with_kg._save_tool_result_to_kg(
        tool_name="dci__search_dci_jobs",
        original_tool_name="search_dci_jobs",
        arguments={"query": "status=failure"},
        result_text=dci_result
    )

    # Verify job entity saved
    job = kg.get_entity("job-123")
    assert job is not None
    assert job.entity_type == "dci_job"
    assert job.data["status"] == "failure"

    # Verify component entity saved
    component = kg.get_entity("comp-1")
    assert component is not None
    assert component.entity_type == "dci_component"
    assert component.data["version"] == "4.19.0"

    # Verify relationship exists
    relationships = kg.get_related_entities("job-123", rel_type="job_uses_component")
    assert len(relationships) == 1


@pytest.mark.asyncio
async def test_save_disabled_when_kg_save_off(agent_with_kg, kg):
    """Test that KG save is skipped when disabled"""
    agent_with_kg.kg_save_enabled = False

    jira_result = '{"key": "CILAB-999", "fields": {"summary": "Test"}}'

    await agent_with_kg._save_tool_result_to_kg(
        tool_name="dci__get_jira_ticket",
        original_tool_name="get_jira_ticket",
        arguments={},
        result_text=jira_result
    )

    # Entity should NOT be saved
    entity = kg.get_entity("CILAB-999")
    assert entity is None


@pytest.mark.asyncio
async def test_save_skips_non_json(agent_with_kg, kg):
    """Test that non-JSON results are skipped"""
    result = "This is not JSON"

    await agent_with_kg._save_tool_result_to_kg(
        tool_name="dci__search_dci_jobs",
        original_tool_name="search_dci_jobs",
        arguments={},
        result_text=result
    )

    # No error should occur, just silently skip
    stats = kg.get_stats()
    assert stats["total_entities"] == 0


@pytest.mark.asyncio
async def test_save_skips_error_results(agent_with_kg, kg):
    """Test that error results are not saved"""
    error_result = "Error: Something went wrong"

    await agent_with_kg._save_tool_result_to_kg(
        tool_name="dci__search_dci_jobs",
        original_tool_name="search_dci_jobs",
        arguments={},
        result_text=error_result
    )

    stats = kg.get_stats()
    assert stats["total_entities"] == 0


@pytest.mark.asyncio
async def test_save_limits_entities(agent_with_kg, kg):
    """Test that entity saving is limited to 20 per call"""
    # Create result with 30 jobs
    jobs = []
    for i in range(30):
        jobs.append({
            "id": f"job-{i}",
            "status": "success",
            "created_at": "2026-02-01T10:00:00Z"
        })

    result = f'{{"hits": {jobs}}}'

    await agent_with_kg._save_tool_result_to_kg(
        tool_name="dci__search_dci_jobs",
        original_tool_name="search_dci_jobs",
        arguments={},
        result_text=result
    )

    # Should only save first 20
    stats = kg.get_stats()
    assert stats["total_entities"] <= 20
