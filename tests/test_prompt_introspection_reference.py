"""Test that introspection tools can access agent's available_prompts"""

from ai_assist.introspection_tools import IntrospectionTools


def test_introspection_tools_reference_to_prompts():
    """Test that introspection tools can see prompts added after initialization"""
    # Simulate agent initialization sequence
    available_prompts = {}  # Agent creates empty dict

    # Introspection tools created with reference
    introspection_tools = IntrospectionTools(available_prompts=available_prompts)

    # Initially empty
    assert len(introspection_tools.available_prompts) == 0

    # Agent populates prompts during server connection (simulated)
    from unittest.mock import MagicMock

    mock_prompt = MagicMock()
    mock_prompt.name = "test_prompt"
    mock_prompt.description = "Test"
    mock_prompt.arguments = []

    available_prompts["test_server"] = {"test_prompt": mock_prompt}

    # Introspection tools should see the update
    assert len(introspection_tools.available_prompts) == 1
    assert "test_server" in introspection_tools.available_prompts
    assert "test_prompt" in introspection_tools.available_prompts["test_server"]


def test_introspection_tools_reference_works_with_reassignment():
    """Test the exact pattern used in agent.__init__"""
    # Exact pattern from agent:
    # 1. Create introspection tools (with None, so it creates empty dict)
    introspection_tools = IntrospectionTools()

    # 2. Create agent's available_prompts
    available_prompts = {}

    # 3. Assign reference (like line 79 in agent.py)
    introspection_tools.available_prompts = available_prompts

    # 4. Populate prompts (like in connect_to_servers)
    from unittest.mock import MagicMock

    mock_prompt = MagicMock()
    mock_prompt.name = "rca"
    mock_prompt.description = "Root cause analysis"

    available_prompts["dci"] = {"rca": mock_prompt}

    # Introspection tools should see the prompts
    assert "dci" in introspection_tools.available_prompts
    assert "rca" in introspection_tools.available_prompts["dci"]
