"""Tests for agent MCP prompt execution"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from ai_assist.agent import AiAssistAgent
from ai_assist.config import AiAssistConfig


@pytest.fixture
def mock_config():
    """Create mock config"""
    config = MagicMock(spec=AiAssistConfig)
    config.use_vertex = False
    config.anthropic_api_key = "test-key"
    config.model = "claude-3-5-sonnet-20241022"
    config.mcp_servers = {}
    config.allow_skill_script_execution = False
    return config


@pytest.fixture
def agent(mock_config):
    """Create agent instance"""
    return AiAssistAgent(mock_config)


@pytest.mark.asyncio
async def test_execute_mcp_prompt_server_not_found(agent):
    """Test error when server not connected"""
    with pytest.raises(ValueError, match="MCP server 'nonexistent' not connected"):
        await agent.execute_mcp_prompt("nonexistent", "rca", {})


@pytest.mark.asyncio
async def test_execute_mcp_prompt_server_no_prompts(agent):
    """Test error when server has no prompts"""
    # Add a mock session but no prompts
    agent.sessions["dci"] = MagicMock()

    with pytest.raises(ValueError, match="Server 'dci' has no prompts"):
        await agent.execute_mcp_prompt("dci", "rca", {})


@pytest.mark.asyncio
async def test_execute_mcp_prompt_prompt_not_found(agent):
    """Test error when prompt not found in server"""
    # Add mock session and prompts
    agent.sessions["dci"] = MagicMock()
    agent.available_prompts["dci"] = {"other_prompt": MagicMock(name="other_prompt", description="Other prompt")}

    with pytest.raises(ValueError, match="Prompt 'rca' not found in server 'dci'"):
        await agent.execute_mcp_prompt("dci", "rca", {})


@pytest.mark.asyncio
async def test_execute_mcp_prompt_missing_required_argument(agent):
    """Test error when required argument is missing"""
    # Setup mock session and prompt with required argument
    mock_session = MagicMock()
    agent.sessions["dci"] = mock_session

    # Create mock argument
    mock_arg = MagicMock()
    mock_arg.name = "days"
    mock_arg.required = True
    mock_arg.description = "Number of days"

    # Create mock prompt
    mock_prompt = MagicMock()
    mock_prompt.name = "rca"
    mock_prompt.arguments = [mock_arg]

    agent.available_prompts["dci"] = {"rca": mock_prompt}

    with pytest.raises(ValueError, match="Required argument 'days' missing"):
        await agent.execute_mcp_prompt("dci", "rca", {})


@pytest.mark.asyncio
async def test_execute_mcp_prompt_success(agent):
    """Test successful prompt execution"""
    # Setup mock session
    mock_session = MagicMock()
    agent.sessions["dci"] = mock_session

    # Create mock prompt (no required arguments)
    mock_prompt = MagicMock()
    mock_prompt.name = "rca"
    mock_prompt.arguments = []

    agent.available_prompts["dci"] = {"rca": mock_prompt}

    # Mock get_prompt response
    mock_message = MagicMock()
    mock_message.content = MagicMock()
    mock_message.content.text = "Test prompt result"

    mock_result = MagicMock()
    mock_result.messages = [mock_message]

    mock_session.get_prompt = AsyncMock(return_value=mock_result)

    # Execute
    result = await agent.execute_mcp_prompt("dci", "rca", None)

    assert result == "Test prompt result"
    mock_session.get_prompt.assert_called_once_with("rca", arguments=None)


@pytest.mark.asyncio
async def test_execute_mcp_prompt_with_arguments(agent):
    """Test prompt execution with arguments"""
    # Setup mock session
    mock_session = MagicMock()
    agent.sessions["dci"] = mock_session

    # Create mock argument (optional)
    mock_arg = MagicMock()
    mock_arg.name = "days"
    mock_arg.required = False
    mock_arg.description = "Number of days"

    # Create mock prompt
    mock_prompt = MagicMock()
    mock_prompt.name = "rca"
    mock_prompt.arguments = [mock_arg]

    agent.available_prompts["dci"] = {"rca": mock_prompt}

    # Mock get_prompt response
    mock_message = MagicMock()
    mock_message.content = MagicMock()
    mock_message.content.text = "RCA for 7 days"

    mock_result = MagicMock()
    mock_result.messages = [mock_message]

    mock_session.get_prompt = AsyncMock(return_value=mock_result)

    # Execute with arguments
    result = await agent.execute_mcp_prompt("dci", "rca", {"days": "7"})

    assert result == "RCA for 7 days"
    mock_session.get_prompt.assert_called_once_with("rca", arguments={"days": "7"})


@pytest.mark.asyncio
async def test_execute_mcp_prompt_multiple_messages(agent):
    """Test prompt execution with multiple messages in result"""
    # Setup mock session
    mock_session = MagicMock()
    agent.sessions["dci"] = mock_session

    # Create mock prompt
    mock_prompt = MagicMock()
    mock_prompt.name = "rca"
    mock_prompt.arguments = []

    agent.available_prompts["dci"] = {"rca": mock_prompt}

    # Mock get_prompt response with multiple messages
    mock_message1 = MagicMock()
    mock_message1.content = MagicMock()
    mock_message1.content.text = "First message"

    mock_message2 = MagicMock()
    mock_message2.content = MagicMock()
    mock_message2.content.text = "Second message"

    mock_result = MagicMock()
    mock_result.messages = [mock_message1, mock_message2]

    mock_session.get_prompt = AsyncMock(return_value=mock_result)

    # Execute
    result = await agent.execute_mcp_prompt("dci", "rca", None)

    assert result == "First message\n\nSecond message"
