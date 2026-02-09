# Knowledge Management Examples

This directory contains examples for working with the agent's knowledge management system.

## Scripts

### `inspect_knowledge_base.py`

Inspect what's stored in the knowledge graph.

```bash
# Run the inspector
python examples/inspect_knowledge_base.py
```

**Output:**
- Overall statistics (entity counts by type)
- Knowledge management entities (preferences, lessons, context)
- Search examples (by query, tags, confidence)
- Other entities (DCI jobs, Jira tickets)

### `demo_knowledge_api.py`

Demonstrates how to programmatically use the knowledge management API.

```bash
# Run the API demo
python examples/demo_knowledge_api.py
```

**Features demonstrated:**
- Creating agent with knowledge graph
- Direct knowledge save
- Knowledge search
- Synthesis trigger
- Statistics

## Usage in Interactive Mode

The easiest way to inspect knowledge is through conversation:

```bash
ai-assist /interactive

# Check what the agent knows about you
You: What preferences do you know about me?

# See all stored knowledge
You: What's in your knowledge graph?

# Search for specific knowledge
You: Do you remember anything about Python testing?

# View statistics
You: How many things have you learned?
```

## Database Location

The knowledge graph is stored at:
```
~/.ai-assist/knowledge_graph.db
```

You can inspect it directly with SQLite:

```bash
sqlite3 ~/.ai-assist/knowledge_graph.db

# List all tables
.tables

# View entity types and counts
SELECT entity_type, COUNT(*)
FROM entities
WHERE tx_to IS NULL
GROUP BY entity_type;

# View knowledge entities
SELECT
    id,
    entity_type,
    json_extract(data, '$.key') as key,
    json_extract(data, '$.content') as content,
    json_extract(data, '$.metadata.confidence') as confidence
FROM entities
WHERE entity_type IN ('user_preference', 'lesson_learned', 'project_context', 'decision_rationale')
AND tx_to IS NULL;
```

## See Also

- [docs/KNOWLEDGE_MANAGEMENT.md](../docs/KNOWLEDGE_MANAGEMENT.md) - User guide
- [tests/test_knowledge_tools.py](../tests/test_knowledge_tools.py) - Unit tests
- [tests/test_agent_synthesis.py](../tests/test_agent_synthesis.py) - Synthesis tests
