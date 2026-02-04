#!/usr/bin/env python3
"""Demo script to populate knowledge graph with sample data"""

from datetime import datetime, timedelta
from pathlib import Path
from boss.knowledge_graph import KnowledgeGraph

def populate_demo_data():
    """Populate knowledge graph with demo data"""
    # Use default location
    kg = KnowledgeGraph()

    print("Populating knowledge graph with demo data...")

    # Base timestamp
    base_time = datetime.now() - timedelta(hours=2)

    # Create some DCI jobs with varying discovery lags
    jobs = [
        {
            "job_id": "123456",
            "status": "failure",
            "remoteci": "telco-cilab-bos2",
            "valid_from": base_time,
            "valid_to": base_time + timedelta(minutes=15),
            "tx_from": base_time + timedelta(minutes=45),  # Discovered 45 min late
        },
        {
            "job_id": "123457",
            "status": "error",
            "remoteci": "telco-cilab-bos2",
            "valid_from": base_time + timedelta(hours=1),
            "valid_to": base_time + timedelta(hours=1, minutes=12),
            "tx_from": base_time + timedelta(hours=1, minutes=5),  # Discovered 5 min late
        },
        {
            "job_id": "123458",
            "status": "success",
            "remoteci": "edge-lab-01",
            "valid_from": base_time + timedelta(hours=1, minutes=30),
            "valid_to": base_time + timedelta(hours=1, minutes=45),
            "tx_from": base_time + timedelta(hours=1, minutes=32),  # Discovered 2 min late
        },
    ]

    # Create components
    components = [
        {
            "id": "component-ocp-4.19.0",
            "type": "ocp",
            "version": "4.19.0",
            "tags": ["build:ga"]
        },
        {
            "id": "component-storage-ceph",
            "type": "storage",
            "version": "17.2.0",
            "tags": ["build:ga"]
        }
    ]

    # Insert components
    for comp in components:
        kg.insert_entity(
            entity_type="component",
            entity_id=comp["id"],
            valid_from=base_time - timedelta(days=30),  # Components existed before jobs
            tx_from=base_time - timedelta(days=30),
            data={
                "type": comp["type"],
                "version": comp.get("version"),
                "tags": comp.get("tags", [])
            }
        )
        print(f"  Created component: {comp['id']}")

    # Insert jobs and create relationships
    for job in jobs:
        entity_id = f"dci-job-{job['job_id']}"
        kg.insert_entity(
            entity_type="dci_job",
            entity_id=entity_id,
            valid_from=job["valid_from"],
            valid_to=job.get("valid_to"),
            tx_from=job["tx_from"],
            data={
                "job_id": job["job_id"],
                "status": job["status"],
                "remoteci": job["remoteci"]
            }
        )

        # Create relationships to components
        for comp in components:
            kg.insert_relationship(
                rel_type="job_uses_component",
                source_id=entity_id,
                target_id=comp["id"],
                valid_from=job["valid_from"],
                tx_from=job["tx_from"],
                properties={"tags": comp.get("tags", [])}
            )

        lag_minutes = (job["tx_from"] - job["valid_from"]).total_seconds() / 60
        print(f"  Created job: {entity_id} (discovered {lag_minutes:.0f} min late)")

    # Create a Jira ticket related to the first failing job
    ticket_time = base_time + timedelta(hours=1)
    kg.insert_entity(
        entity_type="jira_ticket",
        entity_id="ticket-CILAB-1234",
        valid_from=ticket_time,
        tx_from=ticket_time,
        data={
            "key": "CILAB-1234",
            "summary": "Investigate DCI job failures in telco-cilab-bos2",
            "status": "In Progress"
        }
    )
    print("  Created ticket: ticket-CILAB-1234")

    # Link ticket to failing job
    kg.insert_relationship(
        rel_type="job_references_ticket",
        source_id="dci-job-123456",
        target_id="ticket-CILAB-1234",
        valid_from=ticket_time,
        tx_from=ticket_time
    )
    print("  Linked job to ticket")

    # Get stats
    stats = kg.get_stats()
    print(f"\nDemo data populated successfully!")
    print(f"Total entities: {stats['total_entities']}")
    print(f"Total relationships: {stats['total_relationships']}")
    print(f"\nDatabase: {stats['db_path']}")

    kg.close()

if __name__ == "__main__":
    populate_demo_data()
