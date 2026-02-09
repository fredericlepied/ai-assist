#!/usr/bin/env python3
"""Inspect knowledge base contents

This script shows different ways to inspect what the agent has learned.
"""

import asyncio
from pathlib import Path

from ai_assist.knowledge_graph import KnowledgeGraph


async def inspect_knowledge_base():
    """Demonstrate different ways to inspect the knowledge base"""

    print("🔍 Knowledge Base Inspection\n")

    # Use the actual knowledge graph location
    kg_path = Path.home() / ".ai-assist" / "knowledge_graph.db"

    if not kg_path.exists():
        print(f"❌ Knowledge graph not found at {kg_path}")
        print("   Run ai-assist in interactive mode first to create it.")
        return

    kg = KnowledgeGraph(str(kg_path))

    print("=" * 70)
    print("1. OVERALL STATISTICS")
    print("=" * 70)
    stats = kg.get_stats()
    print(f"\nTotal entities: {stats['total_entities']}")
    print("\nEntities by type:")
    for entity_type, count in sorted(stats["entities_by_type"].items()):
        print(f"  • {entity_type}: {count}")

    print(f"\nTotal relationships: {stats['total_relationships']}")
    if stats["relationships_by_type"]:
        print("\nRelationships by type:")
        for rel_type, count in sorted(stats["relationships_by_type"].items()):
            print(f"  • {rel_type}: {count}")

    print("\n" + "=" * 70)
    print("2. KNOWLEDGE MANAGEMENT ENTITIES")
    print("=" * 70)

    knowledge_types = [
        "user_preference",
        "lesson_learned",
        "project_context",
        "decision_rationale",
    ]

    for entity_type in knowledge_types:
        results = kg.search_knowledge(entity_type=entity_type, limit=100)

        if results:
            print(f"\n{entity_type.replace('_', ' ').title()} ({len(results)}):")
            print("-" * 70)
            for r in results:
                print(f"\n  Key: {r['key']}")
                print(f"  Content: {r['content']}")
                print(f"  Tags: {r['metadata'].get('tags', [])}")
                print(f"  Confidence: {r['metadata'].get('confidence', 'N/A')}")
                print(f"  Learned at: {r['learned_at']}")
        else:
            print(f"\n{entity_type.replace('_', ' ').title()}: None")

    print("\n" + "=" * 70)
    print("3. SEARCH EXAMPLES")
    print("=" * 70)

    # Search by key pattern
    print("\n📌 Search for 'python' related knowledge:")
    results = kg.search_knowledge(key_pattern="%python%", limit=10)
    if results:
        for r in results:
            print(f"  • [{r['entity_type']}] {r['key']}: {r['content'][:60]}...")
    else:
        print("  No results found")

    # Search by tags
    print("\n📌 Search for knowledge tagged with 'testing':")
    results = kg.search_knowledge(tags=["testing"], limit=10)
    if results:
        for r in results:
            print(f"  • [{r['entity_type']}] {r['key']}")
    else:
        print("  No results found")

    # Search with high confidence filter
    print("\n📌 High confidence knowledge (>= 0.9):")
    results = kg.search_knowledge(min_confidence=0.9, limit=10)
    if results:
        for r in results:
            confidence = r["metadata"].get("confidence", 0)
            print(f"  • [{r['entity_type']}] {r['key']} (confidence: {confidence})")
    else:
        print("  No results found")

    print("\n" + "=" * 70)
    print("4. OTHER ENTITIES (DCI/JIRA)")
    print("=" * 70)

    # Check for DCI jobs
    dci_count = stats["entities_by_type"].get("dci_job", 0)
    if dci_count > 0:
        print(f"\n📊 DCI Jobs: {dci_count} stored")
        print("   (These are automatically saved when you query DCI)")

    # Check for Jira tickets
    jira_count = stats["entities_by_type"].get("jira_ticket", 0)
    if jira_count > 0:
        print(f"\n🎫 Jira Tickets: {jira_count} stored")
        print("   (These are automatically saved when you query Jira)")

    # Check for components
    comp_count = stats["entities_by_type"].get("dci_component", 0)
    if comp_count > 0:
        print(f"\n🔧 DCI Components: {comp_count} stored")

    print("\n" + "=" * 70)
    print("✅ Inspection complete")
    print("=" * 70)

    kg.close()


if __name__ == "__main__":
    asyncio.run(inspect_knowledge_base())
