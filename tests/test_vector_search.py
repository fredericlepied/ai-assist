"""Tests for vector-based semantic search on KnowledgeGraph"""

from datetime import datetime

import pytest

from ai_assist.knowledge_graph import KnowledgeGraph


@pytest.fixture
def kg():
    graph = KnowledgeGraph(db_path=":memory:")
    yield graph
    graph.close()


def test_semantic_search_finds_related_content(kg):
    kg.insert_knowledge(
        "lesson_learned", "deploy_issue", "Deployment failures on Fridays are usually infrastructure timeouts"
    )
    kg.insert_knowledge("lesson_learned", "test_flaky", "Flaky tests in CI are caused by shared database state")

    results = kg.semantic_search("deploy error on Friday", limit=2)
    assert len(results) >= 1
    assert results[0]["key"] == "deploy_issue"


def test_semantic_search_ranks_by_similarity(kg):
    kg.insert_knowledge("lesson_learned", "deploy_issue", "Deployment failures are usually infrastructure timeouts")
    kg.insert_knowledge("lesson_learned", "test_flaky", "Flaky tests in CI are caused by shared database state")
    kg.insert_knowledge("lesson_learned", "cake_recipe", "The best chocolate cake uses Dutch cocoa")

    results = kg.semantic_search("deploy error", limit=3)
    assert len(results) >= 2
    # deploy_issue should rank higher than cake_recipe
    ids = [r["key"] for r in results]
    assert ids.index("deploy_issue") < ids.index("cake_recipe")


def test_semantic_search_respects_entity_type_filter(kg):
    kg.insert_knowledge("user_preference", "report_style", "User prefers bullet points in reports")
    kg.insert_knowledge("lesson_learned", "report_format", "Reports work best with tables for data")

    results = kg.semantic_search("report format", entity_types=["lesson_learned"])
    assert all(r["entity_type"] == "lesson_learned" for r in results)


def test_semantic_search_respects_min_confidence(kg):
    kg.insert_knowledge("lesson_learned", "vague", "Maybe something about testing", confidence=0.3)
    kg.insert_knowledge("lesson_learned", "certain", "Testing requires isolated database fixtures", confidence=0.9)

    results = kg.semantic_search("testing practices", min_confidence=0.7)
    assert all(r["metadata"]["confidence"] >= 0.7 for r in results)


def test_semantic_search_returns_empty_for_empty_kg(kg):
    results = kg.semantic_search("anything at all")
    assert results == []


def test_semantic_search_limits_results(kg):
    for i in range(10):
        kg.insert_knowledge("lesson_learned", f"lesson_{i}", f"Lesson number {i} about deployment")

    results = kg.semantic_search("deployment lessons", limit=3)
    assert len(results) <= 3


def test_semantic_search_includes_score(kg):
    kg.insert_knowledge("lesson_learned", "deploy_issue", "Deployment failures on Fridays")

    results = kg.semantic_search("deploy error", limit=1)
    assert len(results) == 1
    assert "score" in results[0]
    assert 0.0 <= results[0]["score"] <= 1.0


def test_vector_updated_on_knowledge_upsert(kg):
    kg.insert_knowledge("lesson_learned", "test_key", "Original content about testing")
    kg.insert_knowledge("lesson_learned", "test_key", "Updated content about deployment pipelines")

    results = kg.semantic_search("deployment pipeline")
    assert len(results) >= 1
    assert results[0]["key"] == "test_key"
    assert "deployment" in results[0]["content"]


def test_semantic_search_on_domain_entities(kg):
    kg.insert_entity(
        entity_type="dci_job",
        entity_id="job-123",
        valid_from=datetime.now(),
        data={
            "name": "openshift-installer",
            "status": "failure",
            "summary": "Job failed during component verification",
        },
    )
    kg.insert_entity(
        entity_type="component",
        entity_id="comp-ocp",
        valid_from=datetime.now(),
        data={"name": "OpenShift 4.16", "summary": "OpenShift container platform version 4.16"},
    )

    results = kg.semantic_search("openshift install failure", limit=5)
    assert len(results) >= 1
    ids = [r["entity_id"] for r in results]
    assert "job-123" in ids


def test_tool_result_entities_not_embedded(kg):
    kg.insert_entity(
        entity_type="tool_result",
        entity_id="tool-abc",
        valid_from=datetime.now(),
        data={"tool_name": "search", "result": {"count": 42}},
    )
    count = kg.conn.execute("SELECT COUNT(*) FROM vec_embeddings").fetchone()[0]
    assert count == 0


def test_backfill_embeddings_for_pre_migration_data(kg):
    # Insert entity via raw SQL to simulate pre-migration data without embeddings
    cursor = kg.conn.cursor()
    cursor.execute(
        "INSERT INTO entities (id, entity_type, valid_from, tx_from, data) VALUES (?, ?, ?, ?, ?)",
        (
            "old-entity",
            "lesson_learned",
            datetime.now().isoformat(),
            datetime.now().isoformat(),
            '{"key": "old_lesson", "content": "Database migrations need rollback plans", "metadata": {"confidence": 0.9}}',
        ),
    )
    kg.conn.commit()

    # Backfill populates embeddings for entities inserted before vector support
    kg.backfill_embeddings()

    results = kg.semantic_search("database migration rollback")
    assert len(results) >= 1
    assert results[0]["entity_id"] == "old-entity"
