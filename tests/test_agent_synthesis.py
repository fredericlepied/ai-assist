"""Tests for agent synthesis functionality"""

import json
from unittest.mock import MagicMock, patch

import pytest

from ai_assist.agent import AiAssistAgent
from ai_assist.config import AiAssistConfig
from ai_assist.context import ConversationMemory
from ai_assist.knowledge_graph import KnowledgeGraph


@pytest.fixture
def kg():
    """Create in-memory knowledge graph"""
    return KnowledgeGraph(":memory:")


@pytest.fixture
def config():
    """Create test configuration"""
    return AiAssistConfig(
        anthropic_api_key="test-key",
        model="claude-3-5-sonnet-20241022",
        mcp_servers={},
    )


@pytest.fixture
def agent(config, kg):
    """Create agent with knowledge graph"""
    agent = AiAssistAgent(config, knowledge_graph=kg)
    return agent


@pytest.fixture
def conversation():
    """Create conversation memory with sample exchanges"""
    conv = ConversationMemory()
    conv.add_exchange(
        "I prefer pytest over unittest for Python testing",
        "Got it! I'll use pytest for Python tests.",
    )
    conv.add_exchange(
        "Also, DCI jobs tend to fail more on Fridays due to upstream CI",
        "Interesting pattern. I'll keep that in mind.",
    )
    return conv


class TestSynthesisEngine:
    """Test synthesis of conversation learnings"""

    @pytest.mark.asyncio
    async def test_synthesis_extracts_preferences(self, agent, conversation):
        """Synthesis should extract user preferences from conversation"""
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text=json.dumps(
                    {
                        "insights": [
                            {
                                "category": "user_preference",
                                "key": "python_test_framework",
                                "content": "User prefers pytest over unittest",
                                "confidence": 1.0,
                                "tags": ["python", "testing"],
                            }
                        ]
                    }
                )
            )
        ]

        with patch.object(agent.anthropic.messages, "create", return_value=mock_response):
            await agent._run_synthesis(conversation, focus="preferences")

        results = agent.knowledge_graph.search_knowledge(entity_type="user_preference")
        assert len(results) >= 1
        assert any("pytest" in r["content"].lower() for r in results)

    @pytest.mark.asyncio
    async def test_synthesis_extracts_lessons(self, agent, conversation):
        """Synthesis should extract lessons learned"""
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text=json.dumps(
                    {
                        "insights": [
                            {
                                "category": "lesson_learned",
                                "key": "dci_friday_pattern",
                                "content": "DCI jobs fail more on Fridays due to upstream CI",
                                "confidence": 0.8,
                                "tags": ["dci", "patterns"],
                            }
                        ]
                    }
                )
            )
        ]

        with patch.object(agent.anthropic.messages, "create", return_value=mock_response):
            await agent._run_synthesis(conversation, focus="lessons")

        results = agent.knowledge_graph.search_knowledge(entity_type="lesson_learned")
        assert len(results) >= 1
        assert any("friday" in r["content"].lower() for r in results)

    @pytest.mark.asyncio
    async def test_synthesis_handles_no_insights(self, agent, conversation):
        """Synthesis handles case with no new insights"""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({"insights": []}))]

        with patch.object(agent.anthropic.messages, "create", return_value=mock_response):
            await agent._run_synthesis(conversation, focus="all")

        results = agent.knowledge_graph.search_knowledge()
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_synthesis_handles_json_error(self, agent, conversation):
        """Synthesis handles invalid JSON gracefully"""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Not valid JSON")]

        with patch.object(agent.anthropic.messages, "create", return_value=mock_response):
            await agent._run_synthesis(conversation, focus="all")

        results = agent.knowledge_graph.search_knowledge()
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_synthesis_handles_markdown_json(self, agent, conversation):
        """Synthesis handles JSON wrapped in markdown code blocks"""
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text='```json\n{"insights": [{"category": "user_preference", "key": "test", "content": "test", "confidence": 1.0, "tags": []}]}\n```'
            )
        ]

        with patch.object(agent.anthropic.messages, "create", return_value=mock_response):
            await agent._run_synthesis(conversation, focus="all")

        results = agent.knowledge_graph.search_knowledge()
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_pending_synthesis_flag(self, agent):
        """Check pending synthesis flag is set correctly"""
        assert agent._pending_synthesis is None

        agent._pending_synthesis = {"focus": "all", "triggered_at": "2024-01-01"}
        assert agent._pending_synthesis is not None
        assert agent._pending_synthesis["focus"] == "all"

        agent._pending_synthesis = None
        assert agent._pending_synthesis is None


class TestSynthesisIntegration:
    """Test integration of synthesis with agent query"""

    @pytest.mark.asyncio
    async def test_synthesis_after_trigger(self, agent, conversation):
        """Synthesis runs after trigger_synthesis tool is called"""
        agent._pending_synthesis = {"focus": "all"}

        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text=json.dumps(
                    {
                        "insights": [
                            {
                                "category": "user_preference",
                                "key": "test_pref",
                                "content": "Test preference",
                                "confidence": 1.0,
                                "tags": [],
                            }
                        ]
                    }
                )
            )
        ]

        with patch.object(agent.anthropic.messages, "create", return_value=mock_response):
            await agent.check_and_run_synthesis(conversation)

        assert agent._pending_synthesis is None
        results = agent.knowledge_graph.search_knowledge()
        assert len(results) >= 1
