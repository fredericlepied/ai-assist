"""Tests for knowledge graph visualization"""

from datetime import datetime
from unittest.mock import patch

import pytest

from ai_assist.kg_visualization import (
    ENTITY_TYPE_STYLES,
    _get_entity_label,
    generate_kg_html,
    open_kg_visualization,
)
from ai_assist.knowledge_graph import KnowledgeGraph


@pytest.fixture
def kg():
    """Create in-memory knowledge graph for testing"""
    graph = KnowledgeGraph(db_path=":memory:")
    yield graph
    graph.close()


def test_generate_html_empty_kg(kg):
    """Empty KG produces valid HTML with 'empty' message"""
    html = generate_kg_html(kg)
    assert "<html" in html
    assert "empty" in html.lower()


def test_generate_html_with_entities(kg):
    """Entities appear as nodes in the HTML"""
    kg.insert_entity(
        entity_type="dci_job",
        entity_id="job-1",
        valid_from=datetime(2026, 2, 4, 10, 0),
        data={"status": "failure"},
    )
    kg.insert_entity(
        entity_type="jira_ticket",
        entity_id="ticket-1",
        valid_from=datetime(2026, 2, 4, 12, 0),
        data={"key": "CILAB-1234"},
    )

    html = generate_kg_html(kg)
    assert "job-1" in html
    assert "ticket-1" in html
    assert "vis.Network" in html


def test_generate_html_with_relationships(kg):
    """Relationships appear as edges in the HTML"""
    job = kg.insert_entity(
        entity_type="dci_job",
        entity_id="job-1",
        valid_from=datetime(2026, 2, 4, 10, 0),
        data={"status": "failure"},
    )
    comp = kg.insert_entity(
        entity_type="component",
        entity_id="comp-1",
        valid_from=datetime(2026, 2, 4, 0, 0),
        data={"type": "ocp", "version": "4.19.0"},
    )
    kg.insert_relationship(
        rel_type="job_uses_component",
        source_id=job.id,
        target_id=comp.id,
        valid_from=datetime(2026, 2, 4, 10, 0),
    )

    html = generate_kg_html(kg)
    assert "job_uses_component" in html
    assert "arrows" in html


def test_get_entity_label_jira_key(kg):
    """Label extraction for Jira ticket uses key"""
    entity = kg.insert_entity(
        entity_type="jira_ticket",
        entity_id="ticket-1",
        valid_from=datetime(2026, 2, 4, 12, 0),
        data={"key": "CILAB-1234", "summary": "Some issue"},
    )
    label = _get_entity_label(entity)
    assert label == "CILAB-1234"


def test_get_entity_label_component(kg):
    """Label extraction for component uses type + version"""
    entity = kg.insert_entity(
        entity_type="component",
        entity_id="comp-1",
        valid_from=datetime(2026, 2, 4, 0, 0),
        data={"type": "ocp", "version": "4.19.0"},
    )
    label = _get_entity_label(entity)
    assert label == "ocp 4.19.0"


def test_get_entity_label_job_status(kg):
    """Label extraction for job uses entity_type prefix + status"""
    entity = kg.insert_entity(
        entity_type="dci_job",
        entity_id="job-1",
        valid_from=datetime(2026, 2, 4, 10, 0),
        data={"status": "failure"},
    )
    label = _get_entity_label(entity)
    assert "failure" in label
    assert "dci_job" in label


def test_get_entity_label_fallback(kg):
    """Label falls back to last 16 chars of entity ID"""
    entity = kg.insert_entity(
        entity_type="unknown_type",
        entity_id="very-long-entity-id-that-needs-truncation",
        valid_from=datetime(2026, 2, 4, 10, 0),
        data={"some": "data"},
    )
    label = _get_entity_label(entity)
    assert len(label) <= 16
    assert label == entity.id[-16:]


@patch("webbrowser.open")
def test_open_visualization_creates_file(mock_open, kg, tmp_path):
    """open_kg_visualization writes file and opens browser"""
    kg.insert_entity(
        entity_type="dci_job",
        entity_id="job-1",
        valid_from=datetime(2026, 2, 4, 10, 0),
        data={"status": "failure"},
    )

    with patch("ai_assist.kg_visualization.get_config_dir", return_value=tmp_path):
        filepath = open_kg_visualization(kg)

    assert filepath.endswith(".html")
    mock_open.assert_called_once()
    # Verify file was actually written
    with open(filepath) as f:
        content = f.read()
    assert "<html" in content


def test_node_and_edge_counts(kg):
    """Node and edge counts in HTML match inserted data"""
    # Insert 3 entities
    job = kg.insert_entity(
        entity_type="dci_job",
        entity_id="job-1",
        valid_from=datetime(2026, 2, 4, 10, 0),
        data={"status": "failure"},
    )
    comp = kg.insert_entity(
        entity_type="component",
        entity_id="comp-1",
        valid_from=datetime(2026, 2, 4, 0, 0),
        data={"type": "ocp", "version": "4.19.0"},
    )
    ticket = kg.insert_entity(
        entity_type="jira_ticket",
        entity_id="ticket-1",
        valid_from=datetime(2026, 2, 4, 12, 0),
        data={"key": "CILAB-1234"},
    )

    # Insert 2 relationships
    kg.insert_relationship(
        rel_type="job_uses_component",
        source_id=job.id,
        target_id=comp.id,
        valid_from=datetime(2026, 2, 4, 10, 0),
    )
    kg.insert_relationship(
        rel_type="job_references_ticket",
        source_id=job.id,
        target_id=ticket.id,
        valid_from=datetime(2026, 2, 4, 12, 0),
    )

    html = generate_kg_html(kg)
    # Stats bar should show counts
    assert "3 entities" in html
    assert "2 relationships" in html


def test_entity_type_styles_coverage():
    """All expected entity types have styles defined"""
    expected_types = [
        "dci_job",
        "dci_component",
        "component",
        "jira_ticket",
        "user_preference",
        "lesson_learned",
        "project_context",
        "decision_rationale",
    ]
    for entity_type in expected_types:
        assert entity_type in ENTITY_TYPE_STYLES, f"Missing style for {entity_type}"
        assert "color" in ENTITY_TYPE_STYLES[entity_type]
        assert "shape" in ENTITY_TYPE_STYLES[entity_type]


def test_expired_entities_excluded(kg):
    """Entities with tx_to set should not appear in visualization"""
    # Insert a current entity
    kg.insert_entity(
        entity_type="dci_job",
        entity_id="job-current",
        valid_from=datetime(2026, 2, 4, 10, 0),
        data={"status": "failure"},
    )
    # Insert an expired entity (tx_to is set)
    kg.insert_entity(
        entity_type="dci_job",
        entity_id="job-expired",
        valid_from=datetime(2026, 2, 4, 10, 0),
        tx_to=datetime(2026, 2, 4, 11, 0),
        data={"status": "failure"},
    )

    html = generate_kg_html(kg)
    assert "job-current" in html
    assert "job-expired" not in html
