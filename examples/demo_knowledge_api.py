#!/usr/bin/env python3
"""Demo: Using the Knowledge Management API

This example shows how to programmatically use the knowledge management API
to save and search knowledge. For inspecting real data, use inspect_knowledge_base.py
"""

import asyncio
from pathlib import Path

from ai_assist.agent import AiAssistAgent
from ai_assist.config import AiAssistConfig
from ai_assist.context import ConversationMemory
from ai_assist.knowledge_graph import KnowledgeGraph


async def demo_knowledge_api():
    """Demonstrate knowledge management API usage"""

    print("🔧 Knowledge Management API Demo\n")

    kg_path = Path("/tmp/test_knowledge.db")
    kg_path.unlink(missing_ok=True)

    kg = KnowledgeGraph(str(kg_path))

    config = AiAssistConfig(anthropic_api_key="test-key", model="claude-3-5-sonnet-20241022", mcp_servers={})

    agent = AiAssistAgent(config, knowledge_graph=kg)

    print("✅ Agent initialized with knowledge graph\n")

    print("📝 Testing direct knowledge save:")
    result = await agent.knowledge_tools.save_knowledge(
        entity_type="user_preference",
        key="python_test_framework",
        content="User prefers pytest over unittest for all Python testing",
        tags=["python", "testing"],
        confidence=1.0,
    )
    print(f"   {result}\n")

    print("📝 Testing knowledge search:")
    search_result = await agent.knowledge_tools.search_knowledge(entity_type="user_preference", query="%python%")
    import json

    data = json.loads(search_result)
    print(f"   Found {data['count']} results:")
    for item in data["results"]:
        print(f"   - {item['type']}: {item['key']}")
        print(f"     {item['content']}")
        print(f"     Tags: {item['tags']}, Confidence: {item['confidence']}\n")

    print("📝 Testing synthesis trigger:")
    conversation = ConversationMemory()
    conversation.add_exchange(
        "I always use black for Python formatting",
        "Got it! I'll remember to use black for Python code formatting.",
    )

    agent._pending_synthesis = {"focus": "all"}
    print("   Synthesis flag set: ✓")
    print(f"   Pending: {agent._pending_synthesis}\n")

    print("📊 Knowledge Graph Stats:")
    stats = kg.get_stats()
    print(f"   Total entities: {stats['total_entities']}")
    print(f"   By type: {stats['entities_by_type']}")

    print("\n✅ Demo complete!")


if __name__ == "__main__":
    asyncio.run(demo_knowledge_api())
