# Knowledge Graph Quick Start Guide

## Installation

```bash
# Install dependencies
uv sync

# Verify installation
uv run ai-assist kg-stats
```

## Quick Demo (5 minutes)

### 1. Populate Demo Data
```bash
uv run python tests/demo_kg.py
```

Output:
```
Populating knowledge graph with demo data...
  Created component: component-ocp-4.19.0
  Created component: component-storage-ceph
  Created job: dci-job-123456 (discovered 45 min late)
  Created job: dci-job-123457 (discovered 5 min late)
  Created job: dci-job-123458 (discovered 2 min late)
  Created ticket: ticket-CILAB-1234
  Linked job to ticket

Demo data populated successfully!
Total entities: 6
Total relationships: 7
```

### 2. Explore the Knowledge Graph

**View statistics:**
```bash
uv run ai-assist kg-stats
```

**Find jobs discovered late:**
```bash
uv run ai-assist kg-late 10  # Jobs discovered >10 min late
```

**Show job details with relationships:**
```bash
uv run ai-assist kg-show dci-job-123456
```

**Show ticket with related jobs:**
```bash
uv run ai-assist kg-show ticket-CILAB-1234
```

**Temporal snapshot (what we knew at a specific time):**
```bash
uv run ai-assist kg-asof "2026-02-04 18:00"
```

**Recent changes:**
```bash
uv run ai-assist kg-changes 1  # Changes in last 1 hour
```

## CLI Commands Reference

| Command | Description | Example |
|---------|-------------|---------|
| `kg-stats` | Show statistics | `ai-assist kg-stats` |
| `kg-asof "<time>"` | Temporal snapshot | `ai-assist kg-asof "2026-02-04 14:00"` |
| `kg-late [min]` | Late discoveries | `ai-assist kg-late 30` |
| `kg-changes [hrs]` | Recent changes | `ai-assist kg-changes 2` |
| `kg-show <id>` | Entity details | `ai-assist kg-show dci-job-123456` |

## Python API

```python
from ai_assist.knowledge_graph import KnowledgeGraph
from ai_assist.kg_queries import KnowledgeGraphQueries
from datetime import datetime, timedelta

# Initialize
kg = KnowledgeGraph()
queries = KnowledgeGraphQueries(kg)

# Insert a job entity
job = kg.insert_entity(
    entity_type="dci_job",
    entity_id="job-test-001",
    valid_from=datetime(2026, 2, 4, 10, 0),  # When job started
    tx_from=datetime(2026, 2, 4, 10, 45),     # When we discovered it
    data={
        "job_id": "TEST001",
        "status": "failure",
        "remoteci": "test-lab"
    }
)

# Create a component
component = kg.insert_entity(
    entity_type="component",
    entity_id="comp-ocp-419",
    valid_from=datetime(2026, 2, 1, 0, 0),
    tx_from=datetime(2026, 2, 1, 0, 0),
    data={"type": "ocp", "version": "4.19.0"}
)

# Link job to component
kg.insert_relationship(
    rel_type="job_uses_component",
    source_id=job.id,
    target_id=component.id,
    valid_from=job.valid_from,
    tx_from=job.tx_from
)

# Query: Find late discoveries
late = queries.find_late_discoveries(min_delay_minutes=30)
for entity in late:
    print(f"{entity['id']}: {entity['lag_human']} lag")

# Query: Get job with context
context = queries.get_job_with_context("job-test-001")
print(f"Job used {len(context['components'])} components")

# Query: What did we know at a specific time?
snapshot = queries.what_did_we_know_at(datetime(2026, 2, 4, 10, 30))
print(f"Knew about {len(snapshot)} entities at 10:30")

# Clean up
kg.close()
```

## Testing

```bash
# Run all knowledge graph tests
pytest tests/test_knowledge_graph.py tests/test_kg_queries.py tests/test_integration_kg.py -v

# Run specific test
pytest tests/test_knowledge_graph.py::test_insert_entity_with_bitemporal -v
```

## Understanding Bi-Temporal Tracking

### Two Time Dimensions

1. **Valid Time** (`valid_from`, `valid_to`)
   - When the fact was **true in reality**
   - Example: Job started at 10:00, ended at 10:15

2. **Transaction Time** (`tx_from`, `tx_to`)
   - When ai-assist **learned** about the fact
   - Example: ai-assist discovered the job at 10:45

### Discovery Lag

The difference between when something happened and when we learned about it:

```
Discovery Lag = tx_from - valid_from
```

Example:
- Job failed at 10:00 (`valid_from`)
- ai-assist discovered it at 10:45 (`tx_from`)
- Discovery lag: 45 minutes

This identifies monitoring delays!

## Use Cases

### 1. Monitoring Quality
Find jobs discovered significantly late:
```bash
ai-assist kg-late 30  # >30 min lag
```

### 2. Historical Analysis
See what ai-assist knew at a specific time:
```bash
ai-assist kg-asof "2026-02-04 14:00"
```

### 3. Impact Analysis
Find all jobs using a specific component:
```python
# Get component
comp = kg.get_entity("component-ocp-4.19.0")

# Find jobs using it
related = kg.get_related_entities(comp.id, direction="incoming")
jobs = [entity for rel, entity in related if entity.entity_type == "dci_job"]
```

### 4. Ticket Tracking
See all jobs related to a ticket:
```bash
ai-assist kg-show ticket-CILAB-1234
```

### 5. Trend Analysis
Analyze discovery lag over time:
```python
stats = queries.analyze_discovery_lag("dci_job", days=7)
print(f"Average lag: {stats['avg_lag_minutes']} minutes")
print(f"P95 lag: {stats['p95_lag_minutes']} minutes")
```

## Database Location

Default: `~/.ai-assist/knowledge_graph.db`

This is a SQLite database that you can:
- Back up: `cp ~/.ai-assist/knowledge_graph.db backup.db`
- Inspect: `sqlite3 ~/.ai-assist/knowledge_graph.db`
- Export: Use SQLite export tools

## Troubleshooting

**Empty knowledge graph?**
```bash
# Populate demo data
uv run python tests/demo_kg.py

# Or run monitors to collect real data
ai-assist monitor
```

**Commands not working?**
```bash
# Check installation
uv sync

# Verify CLI works
uv run ai-assist kg-stats
```

**Need to reset?**
```bash
# Delete database (will lose all data!)
rm ~/.ai-assist/knowledge_graph.db

# Repopulate with demo data
uv run python tests/demo_kg.py
```

## Next Steps

1. **Read the full documentation**: `KNOWLEDGE_GRAPH.md`
2. **Explore the demo data**: Run all CLI commands
3. **Try the Python API**: Use in your own scripts
4. **Run monitors**: Collect real DCI/Jira data
5. **Analyze patterns**: Use temporal queries

## Getting Help

- Full documentation: `KNOWLEDGE_GRAPH.md`
- Implementation details: `IMPLEMENTATION_SUMMARY.md`
- Source code: `ai_assist/knowledge_graph.py`, `ai_assist/kg_queries.py`
- Tests: `tests/test_*.py`
