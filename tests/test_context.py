"""Tests for conversation context management"""

import pytest
from datetime import datetime, timedelta
from boss.context import ConversationMemory, KnowledgeGraphContext
from boss.knowledge_graph import KnowledgeGraph


def test_conversation_memory_initialization():
    """Test ConversationMemory initializes correctly"""
    memory = ConversationMemory(max_exchanges=5)

    assert len(memory) == 0
    assert memory.get_exchange_count() == 0
    assert memory.max_exchanges == 5


def test_add_exchange():
    """Test adding exchanges to memory"""
    memory = ConversationMemory()

    memory.add_exchange("Question 1", "Answer 1")
    assert len(memory) == 1

    memory.add_exchange("Question 2", "Answer 2")
    assert len(memory) == 2


def test_to_messages_format():
    """Test conversion to Claude messages format"""
    memory = ConversationMemory()

    memory.add_exchange("Hello", "Hi there!")
    memory.add_exchange("How are you?", "I'm doing well!")

    messages = memory.to_messages()

    assert len(messages) == 4  # 2 exchanges = 4 messages
    assert messages[0] == {"role": "user", "content": "Hello"}
    assert messages[1] == {"role": "assistant", "content": "Hi there!"}
    assert messages[2] == {"role": "user", "content": "How are you?"}
    assert messages[3] == {"role": "assistant", "content": "I'm doing well!"}


def test_max_exchanges_limit():
    """Test that old exchanges are dropped when max is reached"""
    memory = ConversationMemory(max_exchanges=2)

    memory.add_exchange("Q1", "A1")
    memory.add_exchange("Q2", "A2")
    memory.add_exchange("Q3", "A3")  # Should drop Q1/A1

    assert len(memory) == 2

    messages = memory.to_messages()
    # Should only have Q2/A2 and Q3/A3
    assert messages[0] == {"role": "user", "content": "Q2"}
    assert messages[1] == {"role": "assistant", "content": "A2"}
    assert messages[2] == {"role": "user", "content": "Q3"}
    assert messages[3] == {"role": "assistant", "content": "A3"}


def test_clear_memory():
    """Test clearing conversation memory"""
    memory = ConversationMemory()

    memory.add_exchange("Q1", "A1")
    memory.add_exchange("Q2", "A2")
    assert len(memory) == 2

    memory.clear()
    assert len(memory) == 0
    assert memory.to_messages() == []


def test_get_last_exchange():
    """Test getting the most recent exchange"""
    memory = ConversationMemory()

    assert memory.get_last_exchange() is None

    memory.add_exchange("Q1", "A1")
    last = memory.get_last_exchange()
    assert last["user"] == "Q1"
    assert last["assistant"] == "A1"
    assert "timestamp" in last

    memory.add_exchange("Q2", "A2")
    last = memory.get_last_exchange()
    assert last["user"] == "Q2"
    assert last["assistant"] == "A2"


def test_exchange_timestamp():
    """Test that exchanges have timestamps"""
    memory = ConversationMemory()

    memory.add_exchange("Test", "Response")

    last = memory.get_last_exchange()
    assert "timestamp" in last
    assert isinstance(last["timestamp"], str)


def test_empty_messages():
    """Test to_messages on empty memory"""
    memory = ConversationMemory()

    messages = memory.to_messages()
    assert messages == []


def test_repr():
    """Test string representation"""
    memory = ConversationMemory(max_exchanges=5)
    memory.add_exchange("Q1", "A1")

    repr_str = repr(memory)
    assert "ConversationMemory" in repr_str
    assert "exchanges=1" in repr_str
    assert "max=5" in repr_str


def test_multiple_exchanges_ordering():
    """Test that exchanges maintain chronological order"""
    memory = ConversationMemory()

    memory.add_exchange("First", "Response 1")
    memory.add_exchange("Second", "Response 2")
    memory.add_exchange("Third", "Response 3")

    messages = memory.to_messages()

    # Check order is preserved
    assert messages[0]["content"] == "First"
    assert messages[2]["content"] == "Second"
    assert messages[4]["content"] == "Third"


# Knowledge Graph Context Tests

def test_kg_context_initialization():
    """Test KnowledgeGraphContext initializes correctly"""
    kg = KnowledgeGraph(":memory:")
    context = KnowledgeGraphContext(kg)

    assert context.knowledge_graph is kg
    assert context.last_context_used == []


def test_kg_context_without_kg():
    """Test KnowledgeGraphContext works without KG (disabled)"""
    context = KnowledgeGraphContext(None)

    enriched, summary = context.enrich_prompt("Test prompt")

    assert enriched == "Test prompt"
    assert summary == []


def test_extract_jira_references():
    """Test extracting Jira ticket references"""
    context = KnowledgeGraphContext(None)

    text = "Check CILAB-123 and CNF-456 for issues"
    refs = context.extract_entity_references(text)

    assert "CILAB-123" in refs["jira_tickets"]
    assert "CNF-456" in refs["jira_tickets"]
    assert len(refs["jira_tickets"]) == 2


def test_extract_time_references():
    """Test extracting time references"""
    context = KnowledgeGraphContext(None)

    text = "What failed yesterday?"
    refs = context.extract_entity_references(text)

    assert len(refs["time_refs"]) == 1
    assert "yesterday" in refs["time_refs"][0].lower()


def test_parse_time_reference():
    """Test parsing time references to datetime"""
    context = KnowledgeGraphContext(None)

    yesterday = context.parse_time_reference("yesterday")
    now = datetime.now()

    # Should be roughly 1 day ago
    delta = now - yesterday
    assert 0.9 < delta.total_seconds() / (24 * 3600) < 1.1


def test_enrich_prompt_with_jira_ticket():
    """Test enriching prompt with Jira ticket context"""
    kg = KnowledgeGraph(":memory:")

    # Insert a Jira ticket
    kg.insert_entity(
        entity_type="jira_ticket",
        entity_id="CILAB-123",
        valid_from=datetime.now(),
        data={
            "key": "CILAB-123",
            "summary": "Test failure in CI",
            "status": "Open"
        }
    )

    context = KnowledgeGraphContext(kg)
    prompt = "What's the status of CILAB-123?"

    enriched, summary = context.enrich_prompt(prompt)

    assert "CILAB-123" in enriched
    assert "Test failure in CI" in enriched
    assert "Open" in enriched
    assert len(summary) == 1
    assert "CILAB-123" in summary[0]


def test_enrich_prompt_with_recent_failures():
    """Test enriching prompt with recent failure context"""
    kg = KnowledgeGraph(":memory:")

    # Insert recent failed jobs
    now = datetime.now()
    for i in range(3):
        kg.insert_entity(
            entity_type="dci_job",
            entity_id=f"job-{i}",
            valid_from=now - timedelta(hours=1),
            data={
                "job_id": f"job-{i}",
                "status": "failure"
            }
        )

    context = KnowledgeGraphContext(kg)
    prompt = "What failed yesterday?"

    enriched, summary = context.enrich_prompt(prompt)

    assert "Recent failures" in enriched
    assert "3 DCI job(s) failed" in enriched
    assert len(summary) == 1
    assert "recent failures" in summary[0].lower()


def test_enrich_prompt_max_entities():
    """Test max_entities limit"""
    kg = KnowledgeGraph(":memory:")

    # Insert many tickets
    for i in range(10):
        kg.insert_entity(
            entity_type="jira_ticket",
            entity_id=f"CILAB-{i}",
            valid_from=datetime.now(),
            data={"key": f"CILAB-{i}", "summary": f"Issue {i}", "status": "Open"}
        )

    context = KnowledgeGraphContext(kg)
    prompt = " ".join([f"CILAB-{i}" for i in range(10)])

    enriched, summary = context.enrich_prompt(prompt, max_entities=3)

    # Should only include 3 entities
    assert len(summary) == 3


def test_get_last_context():
    """Test getting last used context summary"""
    kg = KnowledgeGraph(":memory:")

    kg.insert_entity(
        entity_type="jira_ticket",
        entity_id="CILAB-123",
        valid_from=datetime.now(),
        data={"key": "CILAB-123", "summary": "Test", "status": "Open"}
    )

    context = KnowledgeGraphContext(kg)
    prompt = "Check CILAB-123"

    _, summary = context.enrich_prompt(prompt)
    last_context = context.get_last_context()

    assert last_context == summary
    assert len(last_context) == 1
