"""Integration tests for knowledge graph with monitors"""

from datetime import datetime, timedelta

import pytest

from ai_assist.kg_queries import KnowledgeGraphQueries
from ai_assist.knowledge_graph import KnowledgeGraph


def test_end_to_end_workflow():
    """Test complete workflow: insert jobs, query, analyze"""
    # Use in-memory database
    kg = KnowledgeGraph(db_path=":memory:")
    queries = KnowledgeGraphQueries(kg)

    # Simulate monitor discovering jobs at different times
    base_time = datetime.now() - timedelta(hours=2)

    # Job 1: Failed at 10:00, discovered at 10:45 (45 min lag)
    job1_valid_from = base_time
    job1_tx_from = base_time + timedelta(minutes=45)

    job1 = kg.insert_entity(
        entity_type="dci_job",
        entity_id="job-integration-1",
        valid_from=job1_valid_from,
        tx_from=job1_tx_from,
        data={
            "job_id": "INT001",
            "status": "failure",
            "remoteci": "test-lab",
            "components": [{"type": "ocp", "version": "4.19.0"}],
        },
    )

    # Job 2: Failed at 11:00, discovered at 11:05 (5 min lag)
    job2_valid_from = base_time + timedelta(hours=1)
    job2_tx_from = base_time + timedelta(hours=1, minutes=5)

    job2 = kg.insert_entity(
        entity_type="dci_job",
        entity_id="job-integration-2",
        valid_from=job2_valid_from,
        tx_from=job2_tx_from,
        data={
            "job_id": "INT002",
            "status": "error",
            "remoteci": "test-lab",
            "components": [{"type": "ocp", "version": "4.19.0"}, {"type": "storage", "name": "ceph"}],
        },
    )

    # Create component entities
    comp_ocp = kg.insert_entity(
        entity_type="component",
        entity_id="comp-ocp-4.19.0",
        valid_from=base_time - timedelta(days=30),
        tx_from=base_time - timedelta(days=30),
        data={"type": "ocp", "version": "4.19.0", "tags": ["build:ga"]},
    )

    comp_storage = kg.insert_entity(
        entity_type="component",
        entity_id="comp-storage-ceph",
        valid_from=base_time - timedelta(days=30),
        tx_from=base_time - timedelta(days=30),
        data={"type": "storage", "name": "ceph", "tags": ["build:ga"]},
    )

    # Create relationships
    kg.insert_relationship(
        rel_type="job_uses_component",
        source_id=job1.id,
        target_id=comp_ocp.id,
        valid_from=job1_valid_from,
        tx_from=job1_tx_from,
    )

    kg.insert_relationship(
        rel_type="job_uses_component",
        source_id=job2.id,
        target_id=comp_ocp.id,
        valid_from=job2_valid_from,
        tx_from=job2_tx_from,
    )

    kg.insert_relationship(
        rel_type="job_uses_component",
        source_id=job2.id,
        target_id=comp_storage.id,
        valid_from=job2_valid_from,
        tx_from=job2_tx_from,
    )

    # Create Jira ticket for investigation
    ticket_time = base_time + timedelta(hours=2)
    ticket = kg.insert_entity(
        entity_type="jira_ticket",
        entity_id="ticket-integration",
        valid_from=ticket_time,
        tx_from=ticket_time,
        data={"key": "TEST-1", "summary": "Investigate failures", "status": "Open"},
    )

    # Link jobs to ticket
    kg.insert_relationship(
        rel_type="job_references_ticket",
        source_id=job1.id,
        target_id=ticket.id,
        valid_from=ticket_time,
        tx_from=ticket_time,
    )

    kg.insert_relationship(
        rel_type="job_references_ticket",
        source_id=job2.id,
        target_id=ticket.id,
        valid_from=ticket_time,
        tx_from=ticket_time,
    )

    # Test 1: Statistics
    stats = kg.get_stats()
    assert stats["total_entities"] == 5  # 2 jobs + 2 components + 1 ticket
    assert stats["total_relationships"] == 5  # 3 job-component + 2 job-ticket
    assert stats["entities_by_type"]["dci_job"] == 2
    assert stats["entities_by_type"]["component"] == 2
    assert stats["entities_by_type"]["jira_ticket"] == 1

    # Test 2: Find late discoveries (>30 min)
    late = queries.find_late_discoveries(min_delay_minutes=30)
    assert len(late) == 1
    assert late[0]["id"] == "job-integration-1"
    assert late[0]["lag_minutes"] == 45.0

    # Test 3: Find late discoveries (>1 min)
    all_late = queries.find_late_discoveries(min_delay_minutes=1)
    assert len(all_late) == 2  # Both jobs discovered late

    # Test 4: Get job with context
    context = queries.get_job_with_context("job-integration-1")
    assert context is not None
    assert context["data"]["status"] == "failure"
    assert len(context["components"]) == 1
    assert len(context["tickets"]) == 1
    assert context["components"][0]["data"]["type"] == "ocp"
    assert context["tickets"][0]["data"]["key"] == "TEST-1"

    # Test 5: Get job 2 with multiple components
    context2 = queries.get_job_with_context("job-integration-2")
    assert len(context2["components"]) == 2
    comp_types = {c["data"]["type"] for c in context2["components"]}
    assert comp_types == {"ocp", "storage"}

    # Test 6: Get ticket with related jobs
    ticket_context = queries.get_ticket_with_context("ticket-integration")
    assert ticket_context is not None
    assert len(ticket_context["related_jobs"]) == 2
    job_ids = {j["job_id"] for j in ticket_context["related_jobs"]}
    assert job_ids == {"job-integration-1", "job-integration-2"}

    # Test 7: Temporal snapshot (at 10:30, before first job discovered)
    snapshot_early = queries.what_did_we_know_at(base_time + timedelta(minutes=30))
    assert len(snapshot_early) == 2  # Only components known
    assert all(e["type"] == "component" for e in snapshot_early)

    # Test 8: Temporal snapshot (at 11:00, after first job discovered)
    snapshot_mid = queries.what_did_we_know_at(base_time + timedelta(hours=1))
    assert len(snapshot_mid) == 3  # Components + job1

    # Test 9: Temporal snapshot (now, all entities)
    snapshot_now = queries.what_did_we_know_at(datetime.now())
    assert len(snapshot_now) == 5  # All entities

    # Test 10: Analyze discovery lag
    lag_stats = queries.analyze_discovery_lag("dci_job", days=7)
    assert lag_stats["count"] == 2
    assert lag_stats["avg_lag_minutes"] == 25.0  # (45 + 5) / 2
    assert lag_stats["min_lag_minutes"] == 5.0
    assert lag_stats["max_lag_minutes"] == 45.0

    kg.close()


def test_correction_workflow():
    """Test correcting beliefs over time"""
    kg = KnowledgeGraph(db_path=":memory:")
    queries = KnowledgeGraphQueries(kg)

    base_time = datetime.now() - timedelta(hours=1)

    # Initial belief: Job failed
    kg.insert_entity(
        entity_type="dci_job",
        entity_id="job-corrected",
        valid_from=base_time,
        tx_from=base_time + timedelta(minutes=10),
        data={"job_id": "CORR001", "status": "failure"},
    )

    # Later: Realize it actually succeeded (correction)
    correction_time = base_time + timedelta(minutes=30)

    # Mark old belief as no longer valid
    kg.update_entity("job-corrected", tx_to=correction_time)

    # Insert corrected belief
    kg.insert_entity(
        entity_type="dci_job",
        entity_id="job-corrected-v2",
        valid_from=base_time,  # Same valid time (reality didn't change)
        tx_from=correction_time,  # New transaction time (belief changed)
        data={"job_id": "CORR001", "status": "success"},
    )

    # Query at different transaction times
    before_correction = queries.what_did_we_know_at(base_time + timedelta(minutes=20))
    assert len(before_correction) == 1
    assert before_correction[0]["id"] == "job-corrected"
    assert before_correction[0]["data"]["status"] == "failure"

    after_correction = queries.what_did_we_know_at(datetime.now())
    assert len(after_correction) == 1
    assert after_correction[0]["id"] == "job-corrected-v2"
    assert after_correction[0]["data"]["status"] == "success"

    kg.close()


def test_graph_traversal():
    """Test bidirectional relationship traversal"""
    kg = KnowledgeGraph(db_path=":memory:")

    base_time = datetime.now()

    # Create a component used by multiple jobs
    comp = kg.insert_entity(
        entity_type="component",
        entity_id="comp-shared",
        valid_from=base_time - timedelta(days=1),
        tx_from=base_time - timedelta(days=1),
        data={"type": "ocp", "version": "4.19.0"},
    )

    # Create 3 jobs using this component
    jobs = []
    for i in range(3):
        job = kg.insert_entity(
            entity_type="dci_job",
            entity_id=f"job-{i}",
            valid_from=base_time + timedelta(hours=i),
            tx_from=base_time + timedelta(hours=i, minutes=5),
            data={"job_id": f"J{i}", "status": "failure"},
        )
        jobs.append(job)

        kg.insert_relationship(
            rel_type="job_uses_component",
            source_id=job.id,
            target_id=comp.id,
            valid_from=job.valid_from,
            tx_from=job.tx_from,
        )

    # Traverse from component to jobs (incoming relationships)
    related = kg.get_related_entities(comp.id, direction="incoming")
    assert len(related) == 3
    job_ids = {entity.id for _, entity in related}
    assert job_ids == {f"job-{i}" for i in range(3)}

    # Traverse from job to component (outgoing relationships)
    related_comp = kg.get_related_entities("job-0", direction="outgoing")
    assert len(related_comp) == 1
    assert related_comp[0][1].id == "comp-shared"

    kg.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
