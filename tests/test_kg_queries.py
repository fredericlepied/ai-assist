"""Tests for knowledge graph query interface"""

import pytest
from datetime import datetime, timedelta
from boss.knowledge_graph import KnowledgeGraph
from boss.kg_queries import KnowledgeGraphQueries


@pytest.fixture
def kg():
    """Create in-memory knowledge graph for testing"""
    graph = KnowledgeGraph(db_path=":memory:")
    yield graph
    graph.close()


@pytest.fixture
def queries(kg):
    """Create query interface"""
    return KnowledgeGraphQueries(kg)


def test_what_did_we_know_at(kg, queries):
    """Test querying what was known at a specific time"""
    # Insert entities at different transaction times
    kg.insert_entity(
        entity_type="dci_job",
        entity_id="job-1",
        valid_from=datetime(2026, 2, 4, 10, 0),
        tx_from=datetime(2026, 2, 4, 11, 0),
        data={"status": "failure"}
    )

    kg.insert_entity(
        entity_type="dci_job",
        entity_id="job-2",
        valid_from=datetime(2026, 2, 4, 10, 30),
        tx_from=datetime(2026, 2, 4, 12, 0),
        data={"status": "error"}
    )

    # Query what we knew at 11:30
    results = queries.what_did_we_know_at(datetime(2026, 2, 4, 11, 30))
    assert len(results) == 1
    assert results[0]["id"] == "job-1"


def test_what_changed_recently(kg, queries):
    """Test finding recent changes"""
    now = datetime.now()
    two_hours_ago = now - timedelta(hours=2)
    thirty_min_ago = now - timedelta(minutes=30)

    # Old entity (discovered 2 hours ago)
    kg.insert_entity(
        entity_type="dci_job",
        entity_id="job-old",
        valid_from=two_hours_ago,
        tx_from=two_hours_ago,
        data={"status": "success"}
    )

    # Recent entity (discovered 30 min ago)
    kg.insert_entity(
        entity_type="dci_job",
        entity_id="job-new",
        valid_from=thirty_min_ago,
        tx_from=thirty_min_ago,
        data={"status": "failure"}
    )

    # Check changes in last hour
    changes = queries.what_changed_recently(hours=1)
    assert changes["new_count"] == 1
    assert changes["new_entities"][0]["id"] == "job-new"


def test_find_late_discoveries(kg, queries):
    """Test finding entities discovered late"""
    # Job that failed at 10:00, discovered at 10:45 (45 min lag)
    kg.insert_entity(
        entity_type="dci_job",
        entity_id="job-late",
        valid_from=datetime(2026, 2, 4, 10, 0),
        tx_from=datetime(2026, 2, 4, 10, 45),
        data={"status": "failure"}
    )

    # Job that failed at 11:00, discovered at 11:05 (5 min lag)
    kg.insert_entity(
        entity_type="dci_job",
        entity_id="job-quick",
        valid_from=datetime(2026, 2, 4, 11, 0),
        tx_from=datetime(2026, 2, 4, 11, 5),
        data={"status": "failure"}
    )

    # Find discoveries with >30 min lag
    late = queries.find_late_discoveries(min_delay_minutes=30)
    assert len(late) == 1
    assert late[0]["id"] == "job-late"
    assert late[0]["lag_minutes"] == 45.0

    # Find discoveries with >1 min lag
    all_late = queries.find_late_discoveries(min_delay_minutes=1)
    assert len(all_late) == 2


def test_get_job_with_context(kg, queries):
    """Test getting job with all related entities"""
    # Create job
    kg.insert_entity(
        entity_type="dci_job",
        entity_id="job-123",
        valid_from=datetime(2026, 2, 4, 10, 0),
        tx_from=datetime(2026, 2, 4, 10, 5),
        data={"status": "failure", "remoteci": "test-lab"}
    )

    # Create components
    comp1 = kg.insert_entity(
        entity_type="component",
        entity_id="comp-ocp",
        valid_from=datetime(2026, 2, 4, 0, 0),
        tx_from=datetime(2026, 2, 4, 0, 0),
        data={"type": "ocp", "version": "4.19.0"}
    )

    comp2 = kg.insert_entity(
        entity_type="component",
        entity_id="comp-storage",
        valid_from=datetime(2026, 2, 4, 0, 0),
        tx_from=datetime(2026, 2, 4, 0, 0),
        data={"type": "storage", "name": "ceph"}
    )

    # Create ticket
    ticket = kg.insert_entity(
        entity_type="jira_ticket",
        entity_id="ticket-456",
        valid_from=datetime(2026, 2, 4, 12, 0),
        tx_from=datetime(2026, 2, 4, 12, 0),
        data={"key": "CILAB-1234"}
    )

    # Create relationships
    kg.insert_relationship(
        rel_type="job_uses_component",
        source_id="job-123",
        target_id=comp1.id,
        valid_from=datetime(2026, 2, 4, 10, 0),
        properties={"build": "ga"}
    )

    kg.insert_relationship(
        rel_type="job_uses_component",
        source_id="job-123",
        target_id=comp2.id,
        valid_from=datetime(2026, 2, 4, 10, 0)
    )

    kg.insert_relationship(
        rel_type="job_references_ticket",
        source_id="job-123",
        target_id=ticket.id,
        valid_from=datetime(2026, 2, 4, 12, 0)
    )

    # Get job with context
    context = queries.get_job_with_context("job-123")
    assert context is not None
    assert context["id"] == "job-123"
    assert len(context["components"]) == 2
    assert len(context["tickets"]) == 1
    assert context["discovery_lag"] == "5m"

    # Check component details
    comp_ids = {c["entity_id"] for c in context["components"]}
    assert comp_ids == {"comp-ocp", "comp-storage"}


def test_get_job_with_context_nonexistent(kg, queries):
    """Test getting context for non-existent job"""
    context = queries.get_job_with_context("non-existent")
    assert context is None


def test_analyze_discovery_lag(kg, queries):
    """Test discovery lag analysis"""
    base_time = datetime.now() - timedelta(hours=2)

    # Create multiple jobs with different lags
    for i in range(10):
        valid_time = base_time + timedelta(minutes=i * 10)
        tx_time = valid_time + timedelta(minutes=5 + i)  # Increasing lag

        kg.insert_entity(
            entity_type="dci_job",
            entity_id=f"job-{i}",
            valid_from=valid_time,
            tx_from=tx_time,
            data={"status": "failure"}
        )

    # Analyze lag
    stats = queries.analyze_discovery_lag("dci_job", days=7)
    assert stats["count"] == 10
    assert stats["avg_lag_minutes"] > 0
    assert stats["min_lag_minutes"] >= 5
    assert stats["max_lag_minutes"] >= stats["avg_lag_minutes"]
    assert stats["p50_lag_minutes"] is not None


def test_analyze_discovery_lag_no_data(kg, queries):
    """Test lag analysis with no data"""
    stats = queries.analyze_discovery_lag("dci_job", days=7)
    assert stats["count"] == 0
    assert "message" in stats


def test_get_ticket_with_context(kg, queries):
    """Test getting ticket with related jobs"""
    # Create ticket
    kg.insert_entity(
        entity_type="jira_ticket",
        entity_id="ticket-789",
        valid_from=datetime(2026, 2, 4, 12, 0),
        tx_from=datetime(2026, 2, 4, 12, 0),
        data={"key": "CILAB-5678", "summary": "Test issue"}
    )

    # Create jobs
    job1 = kg.insert_entity(
        entity_type="dci_job",
        entity_id="job-a",
        valid_from=datetime(2026, 2, 4, 10, 0),
        tx_from=datetime(2026, 2, 4, 10, 5),
        data={"status": "failure"}
    )

    job2 = kg.insert_entity(
        entity_type="dci_job",
        entity_id="job-b",
        valid_from=datetime(2026, 2, 4, 10, 30),
        tx_from=datetime(2026, 2, 4, 10, 35),
        data={"status": "failure"}
    )

    # Create relationships
    kg.insert_relationship(
        rel_type="job_references_ticket",
        source_id=job1.id,
        target_id="ticket-789",
        valid_from=datetime(2026, 2, 4, 12, 0)
    )

    kg.insert_relationship(
        rel_type="job_references_ticket",
        source_id=job2.id,
        target_id="ticket-789",
        valid_from=datetime(2026, 2, 4, 12, 0)
    )

    # Get ticket with context
    context = queries.get_ticket_with_context("ticket-789")
    assert context is not None
    assert context["id"] == "ticket-789"
    assert context["job_count"] == 2
    assert len(context["related_jobs"]) == 2

    job_ids = {job["job_id"] for job in context["related_jobs"]}
    assert job_ids == {"job-a", "job-b"}


def test_format_duration():
    """Test duration formatting"""
    from boss.kg_queries import KnowledgeGraphQueries

    assert KnowledgeGraphQueries._format_duration(0) == "0s"
    assert KnowledgeGraphQueries._format_duration(45) == "45s"
    assert KnowledgeGraphQueries._format_duration(90) == "1m 30s"
    assert KnowledgeGraphQueries._format_duration(300) == "5m"
    assert KnowledgeGraphQueries._format_duration(3665) == "1h 1m 5s"
    assert KnowledgeGraphQueries._format_duration(7200) == "2h"
    assert KnowledgeGraphQueries._format_duration(-10) == "0s"  # Negative handled


def test_what_changed_with_corrections(kg, queries):
    """Test that corrections show up in changes"""
    now = datetime.now()
    thirty_min_ago = now - timedelta(minutes=30)

    # Original belief
    kg.insert_entity(
        entity_type="dci_job",
        entity_id="job-original",
        valid_from=thirty_min_ago - timedelta(hours=1),
        tx_from=thirty_min_ago - timedelta(hours=1),
        data={"status": "failure"}
    )

    # Corrected belief (discovered original was wrong)
    kg.update_entity("job-original", tx_to=thirty_min_ago)

    # New corrected version
    kg.insert_entity(
        entity_type="dci_job",
        entity_id="job-corrected",
        valid_from=thirty_min_ago - timedelta(hours=1),
        tx_from=thirty_min_ago,
        data={"status": "success"}  # Actually succeeded
    )

    # Check changes in last hour
    changes = queries.what_changed_recently(hours=1)
    assert changes["new_count"] == 1  # The corrected version
    assert changes["corrected_count"] == 1  # The original belief
