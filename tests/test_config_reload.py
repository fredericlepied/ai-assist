"""Tests for configuration auto-reload functionality"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_mcp_config_file_watching(tmp_path):
    """Test that mcp_servers.yaml changes are detected"""
    from ai_assist.file_watchdog import FileWatchdog

    config_file = tmp_path / "mcp_servers.yaml"
    config_file.write_text("servers: {}")

    callback_called = False

    async def callback():
        nonlocal callback_called
        callback_called = True

    watcher = FileWatchdog(config_file, callback)
    await watcher.start()

    # Modify file
    config_file.write_text("servers: {test: {}}")
    await asyncio.sleep(1.0)

    assert callback_called
    await watcher.stop()


@pytest.mark.asyncio
async def test_identity_file_watching(tmp_path):
    """Test that identity.yaml changes are detected"""
    from ai_assist.file_watchdog import FileWatchdog

    identity_file = tmp_path / "identity.yaml"
    identity_file.write_text("version: '1.0'\nuser:\n  name: 'Test'")

    callback_called = False

    async def callback():
        nonlocal callback_called
        callback_called = True

    watcher = FileWatchdog(identity_file, callback)
    await watcher.start()

    # Modify file
    identity_file.write_text("version: '1.0'\nuser:\n  name: 'Updated'")
    await asyncio.sleep(1.0)

    assert callback_called
    await watcher.stop()


@pytest.mark.asyncio
async def test_skills_file_watching(tmp_path):
    """Test that installed-skills.json changes are detected"""
    from ai_assist.file_watchdog import FileWatchdog

    skills_file = tmp_path / "installed-skills.json"
    skills_file.write_text('{"skills": []}')

    callback_called = False

    async def callback():
        nonlocal callback_called
        callback_called = True

    watcher = FileWatchdog(skills_file, callback)
    await watcher.start()

    # Modify file
    skills_file.write_text('{"skills": ["test"]}')
    await asyncio.sleep(1.0)

    assert callback_called
    await watcher.stop()


@pytest.mark.asyncio
async def test_reload_mcp_servers_add_server(tmp_path):
    """Test adding a new MCP server via config reload"""
    from ai_assist.agent import AiAssistAgent
    from ai_assist.config import AiAssistConfig

    # Setup agent with empty servers
    config = AiAssistConfig(mcp_servers={})
    with patch("ai_assist.agent.Anthropic"):
        agent = AiAssistAgent(config)

    assert len(agent.sessions) == 0

    # Create mcp_servers.yaml with a new server
    mcp_file = tmp_path / "mcp_servers.yaml"
    mcp_file.write_text(
        """
servers:
  test-server:
    command: echo
    args: ["hello"]
    enabled: true
"""
    )

    # Mock the _run_server method to avoid actually starting a server
    agent._run_server = AsyncMock()

    # Reload MCP servers with the new config directory
    with patch("ai_assist.config.get_config_dir", return_value=tmp_path):
        await agent.reload_mcp_servers()

    # Verify the server was added
    assert "test-server" in agent.config.mcp_servers
    agent._run_server.assert_called_once()


@pytest.mark.asyncio
async def test_reload_mcp_servers_remove_server(tmp_path):
    """Test removing an MCP server via config reload"""
    from ai_assist.agent import AiAssistAgent
    from ai_assist.config import AiAssistConfig, MCPServerConfig

    # Setup agent with one server
    config = AiAssistConfig(
        mcp_servers={
            "test-server": MCPServerConfig(command="echo", args=["hello"], enabled=True),
        }
    )
    with patch("ai_assist.agent.Anthropic"):
        agent = AiAssistAgent(config)

    # Add a mock session
    mock_session = MagicMock()
    agent.sessions["test-server"] = mock_session

    # Add mock tools for this server
    agent.available_tools = [
        {"name": "test-server__tool1", "_server": "test-server"},
        {"name": "test-server__tool2", "_server": "test-server"},
    ]

    # Add mock server task
    mock_task = MagicMock()
    mock_task.cancel = MagicMock()
    agent._server_tasks = [mock_task]

    # Create empty mcp_servers.yaml
    mcp_file = tmp_path / "mcp_servers.yaml"
    mcp_file.write_text(
        """
servers: {}
"""
    )

    # Reload MCP servers with the new config directory
    with patch("ai_assist.config.get_config_dir", return_value=tmp_path):
        await agent.reload_mcp_servers()

    # Verify the server was removed
    assert "test-server" not in agent.sessions
    assert len([t for t in agent.available_tools if t["_server"] == "test-server"]) == 0


@pytest.mark.asyncio
async def test_restart_mcp_server():
    """Test restarting a single MCP server"""
    from ai_assist.agent import AiAssistAgent
    from ai_assist.config import AiAssistConfig, MCPServerConfig

    # Setup agent with one server
    config = AiAssistConfig(
        mcp_servers={
            "test-server": MCPServerConfig(command="echo", args=["hello"], enabled=True),
        }
    )
    with patch("ai_assist.agent.Anthropic"):
        agent = AiAssistAgent(config)

    # Add a mock session
    mock_session = MagicMock()
    agent.sessions["test-server"] = mock_session

    # Add mock tools for this server
    agent.available_tools = [
        {"name": "test-server__tool1", "_server": "test-server"},
        {"name": "test-server__tool2", "_server": "test-server"},
    ]

    # Add mock prompts for this server
    agent.available_prompts["test-server"] = {"prompt1": MagicMock()}

    # Add mock server task
    mock_task = MagicMock()
    mock_task.get_name.return_value = "mcp_test-server"
    mock_task.cancel = MagicMock()
    agent._server_tasks = [mock_task]

    # Mock _run_server to simulate a successful reconnection
    async def fake_run_server(name, cfg):
        agent.sessions[name] = MagicMock()
        agent.available_tools.append({"name": "test-server__new_tool", "_server": name})

    agent._run_server = AsyncMock(side_effect=fake_run_server)

    await agent.restart_mcp_server("test-server")

    # Verify the old task was cancelled
    mock_task.cancel.assert_called_once()

    # Verify old session/tools/prompts were cleaned up before reconnection
    # (the fake_run_server added back a new session and tool)
    assert "test-server" in agent.sessions
    agent._run_server.assert_called_once()

    # Verify only the new tool exists (old ones were removed)
    server_tools = [t for t in agent.available_tools if t.get("_server") == "test-server"]
    assert len(server_tools) == 1
    assert server_tools[0]["name"] == "test-server__new_tool"

    # Verify prompts were cleaned
    assert "test-server" not in agent.available_prompts


@pytest.mark.asyncio
async def test_restart_mcp_server_unknown():
    """Test restarting an unknown MCP server raises ValueError"""
    from ai_assist.agent import AiAssistAgent
    from ai_assist.config import AiAssistConfig

    config = AiAssistConfig(mcp_servers={})
    with patch("ai_assist.agent.Anthropic"):
        agent = AiAssistAgent(config)

    with pytest.raises(ValueError, match="Unknown MCP server: nonexistent"):
        await agent.restart_mcp_server("nonexistent")
