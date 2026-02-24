# How to Inspect the Knowledge Base

There are three main ways to see what the agent has learned:

## 1. Ask the Agent (Easiest)

Just talk to the agent in interactive mode:

```bash
ai-assist /interactive
```

### Check Preferences

```
You: What preferences do you know about me?

Agent: Let me check... [calls internal__search_knowledge(entity_type="user_preference")]

Agent: I know the following preferences:
  • python_test_framework: You prefer pytest over unittest
  • code_formatter: You use black for Python formatting
  • git_branch_style: You name bug fix branches as bug/TICKET-ID
```

### Check Lessons Learned

```
You: What have you learned about DCI?

Agent: [calls internal__search_knowledge(entity_type="lesson_learned", query="%dci%")]

Agent: I've learned:
  • dci_friday_pattern: DCI jobs fail more on Fridays due to upstream CI runs
  • dci_error_handling: Always check rate limits before bulk operations
```

### See Everything

```
You: Show me everything in your knowledge graph

Agent: [calls introspection__get_kg_stats]

Agent: Knowledge graph contains:
  Total: 285 entities
    • user_preference: 3
    • lesson_learned: 2
    • project_context: 1
    • dci_job: 114
    • jira_ticket: 156
    • dci_component: 9
```

### Search for Specific Topics

```
You: Do you remember anything about Python?

Agent: [calls internal__search_knowledge(query="%python%")]

Agent: Yes, I found:
  • python_test_framework (preference): You prefer pytest
  • python_formatter (preference): You use black
  • python_best_practices (lesson): Always use type hints...
```

## 2. Use the Inspector Script

Run the provided inspection script:

```bash
python examples/inspect_knowledge_base.py
```

This shows:
- **Statistics**: Total entities, counts by type
- **Knowledge entities**: All preferences, lessons, context, rationale
- **Search examples**: Demonstrates different search queries
- **Other entities**: DCI jobs, Jira tickets, components

Example output:
```
🔍 Knowledge Base Inspection

======================================================================
1. OVERALL STATISTICS
======================================================================

Total entities: 285

Entities by type:
  • user_preference: 3
  • lesson_learned: 2
  • project_context: 1
  • dci_job: 114
  • jira_ticket: 156
  • dci_component: 9

======================================================================
2. KNOWLEDGE MANAGEMENT ENTITIES
======================================================================

User Preference (3):
----------------------------------------------------------------------

  Key: python_test_framework
  Content: User prefers pytest over unittest for all Python testing
  Tags: ['python', 'testing']
  Confidence: 1.0
  Learned at: 2024-02-09T10:30:00
...
```

## 3. Direct Database Access (Advanced)

For advanced users who want full control:

```bash
sqlite3 ~/.ai-assist/knowledge_graph.db
```

### Useful Queries

**List all entity types:**
```sql
SELECT entity_type, COUNT(*)
FROM entities
WHERE tx_to IS NULL  -- Only current (not superseded)
GROUP BY entity_type;
```

**View all user preferences:**
```sql
SELECT
    id,
    json_extract(data, '$.key') as key,
    json_extract(data, '$.content') as content,
    json_extract(data, '$.metadata.tags') as tags,
    json_extract(data, '$.metadata.confidence') as confidence,
    tx_from as learned_at
FROM entities
WHERE entity_type = 'user_preference'
AND tx_to IS NULL
ORDER BY tx_from DESC;
```

**Search knowledge by content:**
```sql
SELECT
    entity_type,
    json_extract(data, '$.key') as key,
    json_extract(data, '$.content') as content
FROM entities
WHERE entity_type IN ('user_preference', 'lesson_learned', 'project_context', 'decision_rationale')
AND json_extract(data, '$.content') LIKE '%python%'
AND tx_to IS NULL;
```

**View knowledge with high confidence:**
```sql
SELECT
    entity_type,
    json_extract(data, '$.key') as key,
    json_extract(data, '$.content') as content,
    CAST(json_extract(data, '$.metadata.confidence') AS REAL) as confidence
FROM entities
WHERE entity_type IN ('user_preference', 'lesson_learned', 'project_context', 'decision_rationale')
AND CAST(json_extract(data, '$.metadata.confidence') AS REAL) >= 0.9
AND tx_to IS NULL;
```

**View when knowledge was learned:**
```sql
SELECT
    entity_type,
    json_extract(data, '$.key') as key,
    tx_from as learned_at,
    valid_from as became_true_at,
    date(tx_from) as date
FROM entities
WHERE entity_type IN ('user_preference', 'lesson_learned', 'project_context', 'decision_rationale')
AND tx_to IS NULL
ORDER BY tx_from DESC;
```

## Understanding the Knowledge Graph Structure

The knowledge graph uses **bi-temporal tracking**:

- **`valid_from` / `valid_to`**: When the fact was true in reality
- **`tx_from` / `tx_to`**: When the agent learned/stopped believing it

This allows you to answer questions like:
- "What did I know on January 1st?" (transaction time)
- "What was true on January 1st?" (valid time)

### Entity Types

**Knowledge Management:**
- `user_preference`: Your stated preferences
- `lesson_learned`: Patterns and insights
- `project_context`: Background information
- `decision_rationale`: Why choices were made

**Conversations:**
- `conversation`: User/assistant exchanges (saved on-the-fly during interactive sessions)
- `synthesis_marker`: Tracks when KG synthesis last ran

**Automatically Captured:**
- `dci_job`: DCI jobs from searches
- `jira_ticket`: Jira tickets from searches
- `dci_component`: Components used in DCI jobs

## Quick Reference

| What You Want | How to Get It |
|---------------|---------------|
| See all preferences | Ask agent: "What preferences do you know?" |
| Check specific topic | Ask agent: "What do you know about X?" |
| View statistics | Ask agent: "What's in your knowledge graph?" |
| Detailed inspection | Run `python examples/inspect_knowledge_base.py` |
| Raw database access | `sqlite3 ~/.ai-assist/knowledge_graph.db` |

## Location

Knowledge graph database:
```
~/.ai-assist/knowledge_graph.db
```

Backup recommendation:
```bash
# Backup your knowledge
cp ~/.ai-assist/knowledge_graph.db ~/backups/knowledge-$(date +%Y%m%d).db
```
