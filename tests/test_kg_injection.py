"""Tests for KG auto-context injection and learning reinforcement in system prompt"""

import time
from datetime import datetime

from ai_assist.agent import AiAssistAgent
from ai_assist.config import AiAssistConfig
from ai_assist.knowledge_graph import KnowledgeGraph


def _make_agent(kg=None):
    config = AiAssistConfig(anthropic_api_key="test-key", mcp_servers={})
    return AiAssistAgent(config, knowledge_graph=kg)


class TestExtractQueryKeywords:
    def test_extracts_significant_words(self):
        agent = _make_agent()
        keywords = agent._extract_query_keywords("Check the failing pipeline status")
        assert "failing" in keywords
        assert "pipeline" in keywords
        assert "status" in keywords

    def test_filters_stop_words(self):
        agent = _make_agent()
        keywords = agent._extract_query_keywords("What is the status of this thing")
        assert "what" not in keywords
        assert "this" not in keywords
        assert "status" in keywords

    def test_filters_short_words(self):
        agent = _make_agent()
        keywords = agent._extract_query_keywords("I am a big fan of it")
        # All words < 4 chars or stop words
        assert len(keywords) == 0

    def test_returns_max_five(self):
        agent = _make_agent()
        keywords = agent._extract_query_keywords("alpha bravo charlie delta echo foxtrot golf hotel")
        assert len(keywords) <= 5

    def test_empty_input(self):
        agent = _make_agent()
        assert agent._extract_query_keywords("") == []

    def test_deduplicates(self):
        agent = _make_agent()
        keywords = agent._extract_query_keywords("pipeline pipeline pipeline")
        assert keywords.count("pipeline") == 1


class TestGetKgLearningsSection:
    def test_no_kg_returns_empty(self):
        agent = _make_agent(kg=None)
        assert agent._get_kg_learnings_section() == ""

    def test_empty_kg_returns_empty(self):
        kg = KnowledgeGraph(":memory:")
        agent = _make_agent(kg=kg)
        assert agent._get_kg_learnings_section() == ""

    def test_preferences_always_injected(self):
        kg = KnowledgeGraph(":memory:")
        kg.insert_knowledge(
            entity_type="user_preference",
            key="report_style",
            content="User prefers concise reports with bullet points",
            confidence=0.9,
        )
        agent = _make_agent(kg=kg)
        section = agent._get_kg_learnings_section()
        assert "User Preferences" in section
        assert "report_style" in section
        assert "concise reports" in section

    def test_preferences_injected_without_query_text(self):
        """Preferences are injected even when there's no current query"""
        kg = KnowledgeGraph(":memory:")
        kg.insert_knowledge(
            entity_type="user_preference",
            key="code_style",
            content="Prefers minimal comments",
            confidence=0.8,
        )
        agent = _make_agent(kg=kg)
        agent._current_query_text = ""
        section = agent._get_kg_learnings_section()
        assert "code_style" in section

    def test_low_confidence_preferences_filtered(self):
        kg = KnowledgeGraph(":memory:")
        kg.insert_knowledge(
            entity_type="user_preference",
            key="uncertain_pref",
            content="Maybe prefers tabs",
            confidence=0.3,
        )
        agent = _make_agent(kg=kg)
        section = agent._get_kg_learnings_section()
        assert "uncertain_pref" not in section

    def test_lessons_injected_when_query_matches(self):
        kg = KnowledgeGraph(":memory:")
        kg.insert_knowledge(
            entity_type="lesson_learned",
            key="pipeline_timeout",
            content="Pipeline failures on Fridays are usually infrastructure timeouts",
            confidence=0.9,
        )
        agent = _make_agent(kg=kg)
        agent._current_query_text = "Why did the pipeline fail?"
        section = agent._get_kg_learnings_section()
        assert "pipeline" in section.lower()
        assert "infrastructure timeouts" in section

    def test_lessons_excluded_when_query_doesnt_match(self):
        kg = KnowledgeGraph(":memory:")
        kg.insert_knowledge(
            entity_type="lesson_learned",
            key="pipeline_timeout",
            content="Pipeline failures on Fridays are usually infrastructure timeouts",
            confidence=0.9,
        )
        agent = _make_agent(kg=kg)
        agent._current_query_text = "What is the weather today?"
        section = agent._get_kg_learnings_section()
        assert "infrastructure timeouts" not in section

    def test_no_query_text_skips_lessons(self):
        kg = KnowledgeGraph(":memory:")
        kg.insert_knowledge(
            entity_type="lesson_learned",
            key="some_lesson",
            content="An important lesson about testing",
            confidence=0.9,
        )
        agent = _make_agent(kg=kg)
        agent._current_query_text = ""
        section = agent._get_kg_learnings_section()
        assert "important lesson" not in section

    def test_project_context_injected_when_relevant(self):
        kg = KnowledgeGraph(":memory:")
        kg.insert_knowledge(
            entity_type="project_context",
            key="deployment_process",
            content="Deployments require approval from team lead",
            confidence=0.8,
        )
        agent = _make_agent(kg=kg)
        agent._current_query_text = "How does the deployment process work?"
        section = agent._get_kg_learnings_section()
        assert "approval from team lead" in section

    def test_decision_rationale_injected_when_relevant(self):
        kg = KnowledgeGraph(":memory:")
        kg.insert_knowledge(
            entity_type="decision_rationale",
            key="chose_pytest",
            content="Chose pytest over unittest for better fixture support",
            confidence=0.85,
        )
        agent = _make_agent(kg=kg)
        agent._current_query_text = "Which testing framework should we use for pytest?"
        section = agent._get_kg_learnings_section()
        assert "pytest" in section

    def test_low_confidence_lessons_filtered(self):
        kg = KnowledgeGraph(":memory:")
        kg.insert_knowledge(
            entity_type="lesson_learned",
            key="vague_pattern",
            content="Maybe something about network issues",
            confidence=0.4,
        )
        agent = _make_agent(kg=kg)
        agent._current_query_text = "Tell me about network issues"
        section = agent._get_kg_learnings_section()
        assert "vague_pattern" not in section

    def test_hard_cap_truncation(self):
        kg = KnowledgeGraph(":memory:")
        for i in range(50):
            kg.insert_knowledge(
                entity_type="user_preference",
                key=f"preference_{i}",
                content=f"A verbose preference description number {i} with lots of detail " * 3,
                confidence=1.0,
            )
        agent = _make_agent(kg=kg)
        section = agent._get_kg_learnings_section()
        assert len(section) <= 2000  # 1500 cap + header

    def test_learnings_in_system_prompt(self):
        kg = KnowledgeGraph(":memory:")
        kg.insert_knowledge(
            entity_type="user_preference",
            key="style",
            content="Prefers detailed explanations",
            confidence=1.0,
        )
        agent = _make_agent(kg=kg)
        prompt = agent._build_system_prompt()
        assert "What You Know" in prompt
        assert "detailed explanations" in prompt

    def test_query_aware_learnings_max_five(self):
        kg = KnowledgeGraph(":memory:")
        for i in range(20):
            kg.insert_knowledge(
                entity_type="lesson_learned",
                key=f"testing_lesson_{i}",
                content=f"Testing lesson number {i} about testing patterns",
                confidence=0.9,
            )
        agent = _make_agent(kg=kg)
        agent._current_query_text = "Tell me about testing patterns"
        section = agent._get_kg_learnings_section()
        # Count lesson entries (lines starting with "- [")
        lesson_lines = [line for line in section.split("\n") if line.strip().startswith("- [")]
        assert len(lesson_lines) <= 5

    def test_learnings_sorted_by_freshness(self):
        """Most recently learned entries appear first"""
        kg = KnowledgeGraph(":memory:")
        kg.insert_knowledge(
            entity_type="lesson_learned",
            key="deploy_old_lesson",
            content="Old deploy lesson from last month",
            confidence=0.9,
        )
        time.sleep(0.01)
        kg.insert_knowledge(
            entity_type="lesson_learned",
            key="deploy_new_lesson",
            content="Fresh deploy lesson from today",
            confidence=0.9,
        )
        agent = _make_agent(kg=kg)
        agent._current_query_text = "How should we deploy?"
        section = agent._get_kg_learnings_section()
        # Fresh lesson should appear before old one
        fresh_pos = section.find("Fresh deploy")
        old_pos = section.find("Old deploy")
        assert fresh_pos < old_pos


class TestGetKgAutoContextSection:
    def test_no_kg_returns_empty(self):
        agent = _make_agent(kg=None)
        agent._current_query_text = "some query"
        assert agent._get_kg_auto_context_section() == ""

    def test_no_query_text_returns_empty(self):
        kg = KnowledgeGraph(":memory:")
        agent = _make_agent(kg=kg)
        agent._current_query_text = ""
        assert agent._get_kg_auto_context_section() == ""

    def test_matching_entity_injected(self):
        kg = KnowledgeGraph(":memory:")
        kg.insert_entity(
            entity_type="component",
            entity_id="openshift-4.16",
            valid_from=datetime.now(),
            data={"name": "OpenShift", "version": "4.16", "status": "active"},
        )
        agent = _make_agent(kg=kg)
        agent._current_query_text = "What happened with OpenShift recently?"
        section = agent._get_kg_auto_context_section()
        assert "openshift-4.16" in section

    def test_non_matching_entity_excluded(self):
        kg = KnowledgeGraph(":memory:")
        kg.insert_entity(
            entity_type="component",
            entity_id="openshift-4.16",
            valid_from=datetime.now(),
            data={"name": "OpenShift", "version": "4.16"},
        )
        agent = _make_agent(kg=kg)
        agent._current_query_text = "How is the weather?"
        section = agent._get_kg_auto_context_section()
        assert section == ""

    def test_knowledge_types_excluded(self):
        """Knowledge entities are handled by learnings section, not auto context"""
        kg = KnowledgeGraph(":memory:")
        kg.insert_knowledge(
            entity_type="user_preference",
            key="testing_pref",
            content="Prefers testing with pytest",
            confidence=1.0,
        )
        agent = _make_agent(kg=kg)
        agent._current_query_text = "Tell me about testing preferences"
        section = agent._get_kg_auto_context_section()
        # user_preference should NOT appear in auto context
        assert "testing_pref" not in section

    def test_max_five_results(self):
        kg = KnowledgeGraph(":memory:")
        for i in range(20):
            kg.insert_entity(
                entity_type="job",
                entity_id=f"build-job-{i}",
                valid_from=datetime.now(),
                data={"name": f"build job {i}", "status": "failure"},
            )
        agent = _make_agent(kg=kg)
        agent._current_query_text = "Show me the build jobs"
        section = agent._get_kg_auto_context_section()
        entity_lines = [line for line in section.split("\n") if line.strip().startswith("- [")]
        assert len(entity_lines) <= 5

    def test_deduplication(self):
        kg = KnowledgeGraph(":memory:")
        kg.insert_entity(
            entity_type="job",
            entity_id="build-deploy-job",
            valid_from=datetime.now(),
            data={"name": "build and deploy job", "status": "success"},
        )
        agent = _make_agent(kg=kg)
        # Both "build" and "deploy" match the same entity
        agent._current_query_text = "Check the build deploy status"
        section = agent._get_kg_auto_context_section()
        assert section.count("build-deploy-job") == 1

    def test_auto_context_in_system_prompt(self):
        kg = KnowledgeGraph(":memory:")
        kg.insert_entity(
            entity_type="ticket",
            entity_id="PROJECT-999",
            valid_from=datetime.now(),
            data={"name": "PROJECT-999", "summary": "Critical production issue", "status": "Open"},
        )
        agent = _make_agent(kg=kg)
        agent._current_query_text = "What is the critical production issue?"
        prompt = agent._build_system_prompt()
        assert "Relevant Context" in prompt
