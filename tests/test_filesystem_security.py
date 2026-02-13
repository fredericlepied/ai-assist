"""Tests for filesystem tools security: command allowlist, path restrictions, and confirmations"""

import pytest

from ai_assist.config import AiAssistConfig
from ai_assist.filesystem_tools import FilesystemTools

# --- Phase 1: Command allowlist + user confirmation ---


@pytest.mark.asyncio
async def test_allowlisted_command_executes_directly():
    """Allowlisted commands like ls, grep run without confirmation"""
    config = AiAssistConfig(anthropic_api_key="test")
    tools = FilesystemTools(config)

    result = await tools.execute_tool("execute_command", {"command": "ls /tmp"})

    assert "Error" not in result or "not found" not in result.lower()
    assert "not allowed" not in result.lower()


@pytest.mark.asyncio
async def test_non_allowlisted_command_blocked_without_callback():
    """Non-allowlisted commands return error when no confirmation callback is set"""
    config = AiAssistConfig(anthropic_api_key="test")
    tools = FilesystemTools(config)
    # No confirmation_callback set

    result = await tools.execute_tool("execute_command", {"command": "curl http://example.com"})

    assert "not allowed" in result.lower() or "not in the allowed" in result.lower()


@pytest.mark.asyncio
async def test_non_allowlisted_command_prompts_user():
    """Non-allowlisted commands call the confirmation callback when set"""
    config = AiAssistConfig(anthropic_api_key="test")
    tools = FilesystemTools(config)

    callback_called = False

    async def mock_callback(command: str) -> bool:
        nonlocal callback_called
        callback_called = True
        return True

    tools.confirmation_callback = mock_callback

    await tools.execute_tool("execute_command", {"command": "curl http://example.com"})

    assert callback_called


@pytest.mark.asyncio
async def test_user_rejects_command():
    """When user rejects via callback, command is not executed"""
    config = AiAssistConfig(anthropic_api_key="test")
    tools = FilesystemTools(config)

    async def reject_callback(command: str) -> bool:
        return False

    tools.confirmation_callback = reject_callback

    result = await tools.execute_tool("execute_command", {"command": "curl http://example.com"})

    assert "rejected" in result.lower()
    assert "allowed commands" in result.lower()


@pytest.mark.asyncio
async def test_user_approves_command():
    """When user approves via callback, command runs"""
    config = AiAssistConfig(anthropic_api_key="test")
    tools = FilesystemTools(config)

    async def approve_callback(command: str) -> bool:
        return True

    tools.confirmation_callback = approve_callback

    result = await tools.execute_tool("execute_command", {"command": "echo approved"})

    assert "approved" in result


@pytest.mark.asyncio
async def test_allowlist_checks_first_token():
    """Allowlist extracts command name from first token, including full paths and pipes"""
    config = AiAssistConfig(anthropic_api_key="test")
    tools = FilesystemTools(config)

    # Full path to an allowlisted command should work
    result = await tools.execute_tool("execute_command", {"command": "/usr/bin/ls /tmp"})
    assert "not allowed" not in result.lower()

    # Pipe with allowlisted first command should work (shell constructs preserved)
    result = await tools.execute_tool("execute_command", {"command": "ls /tmp | grep test"})
    assert "not allowed" not in result.lower()

    # Non-allowlisted command is still blocked
    result = await tools.execute_tool("execute_command", {"command": "rm -rf /tmp/test"})
    assert "not allowed" in result.lower() or "not in the allowed" in result.lower()


@pytest.mark.asyncio
async def test_no_timeout_in_interactive_mode():
    """In interactive mode (callback set), no timeout is applied"""
    config = AiAssistConfig(anthropic_api_key="test")
    tools = FilesystemTools(config)

    async def approve_all(command: str) -> bool:
        return True

    # Non-interactive: timeout is applied (default 30s, capped at 300s)
    assert tools.confirmation_callback is None

    # Interactive: setting callback signals interactive mode
    tools.confirmation_callback = approve_all

    # sleep 1 should complete fine without being killed by timeout
    result = await tools.execute_tool("execute_command", {"command": "sleep 1 && echo done"})
    assert "done" in result


@pytest.mark.asyncio
async def test_custom_allowlist_from_config():
    """Config overrides default allowlist"""
    config = AiAssistConfig(anthropic_api_key="test", allowed_commands=["echo", "pwd"])
    tools = FilesystemTools(config)

    # 'echo' is in custom allowlist - should work
    result = await tools.execute_tool("execute_command", {"command": "echo hello"})
    assert "hello" in result

    # 'ls' is NOT in custom allowlist - should be blocked without callback
    result = await tools.execute_tool("execute_command", {"command": "ls /tmp"})
    assert "not allowed" in result.lower() or "not in the allowed" in result.lower()


# --- Phase 2: Filesystem path restrictions ---


@pytest.mark.asyncio
async def test_read_file_allowed_path(tmp_path):
    """Reading a file under an allowed path succeeds"""
    config = AiAssistConfig(anthropic_api_key="test", allowed_paths=[str(tmp_path)])
    tools = FilesystemTools(config)

    test_file = tmp_path / "test.txt"
    test_file.write_text("hello world")

    result = await tools.execute_tool("read_file", {"path": str(test_file)})

    assert "hello world" in result
    assert "Error" not in result


@pytest.mark.asyncio
async def test_read_file_blocked_path(tmp_path):
    """Reading a file outside allowed paths returns error"""
    config = AiAssistConfig(anthropic_api_key="test", allowed_paths=[str(tmp_path / "allowed")])
    tools = FilesystemTools(config)

    blocked_file = tmp_path / "blocked" / "secret.txt"
    blocked_file.parent.mkdir(parents=True, exist_ok=True)
    blocked_file.write_text("secret data")

    result = await tools.execute_tool("read_file", {"path": str(blocked_file)})

    assert "not allowed" in result.lower() or "outside allowed" in result.lower()


@pytest.mark.asyncio
async def test_create_directory_blocked_path(tmp_path):
    """Cannot create directory outside allowed paths"""
    config = AiAssistConfig(anthropic_api_key="test", allowed_paths=[str(tmp_path / "allowed")])
    tools = FilesystemTools(config)

    result = await tools.execute_tool("create_directory", {"path": str(tmp_path / "blocked" / "new_dir")})

    assert "not allowed" in result.lower() or "outside allowed" in result.lower()


@pytest.mark.asyncio
async def test_custom_allowed_paths_from_config(tmp_path):
    """Config overrides default allowed paths"""
    custom_dir = tmp_path / "custom"
    custom_dir.mkdir()
    test_file = custom_dir / "data.txt"
    test_file.write_text("custom data")

    config = AiAssistConfig(anthropic_api_key="test", allowed_paths=[str(custom_dir)])
    tools = FilesystemTools(config)

    result = await tools.execute_tool("read_file", {"path": str(test_file)})
    assert "custom data" in result


@pytest.mark.asyncio
async def test_path_traversal_blocked(tmp_path):
    """Path traversal attempts (../../) are resolved and blocked"""
    allowed_dir = tmp_path / "allowed"
    allowed_dir.mkdir()

    config = AiAssistConfig(anthropic_api_key="test", allowed_paths=[str(allowed_dir)])
    tools = FilesystemTools(config)

    # Try to traverse out of allowed directory
    traversal_path = str(allowed_dir / ".." / ".." / "etc" / "passwd")
    result = await tools.execute_tool("read_file", {"path": traversal_path})

    assert "not allowed" in result.lower() or "outside allowed" in result.lower()


@pytest.mark.asyncio
async def test_list_directory_blocked_path(tmp_path):
    """Cannot list directory outside allowed paths"""
    config = AiAssistConfig(anthropic_api_key="test", allowed_paths=[str(tmp_path / "allowed")])
    tools = FilesystemTools(config)

    blocked_dir = tmp_path / "blocked"
    blocked_dir.mkdir()

    result = await tools.execute_tool("list_directory", {"path": str(blocked_dir)})

    assert "not allowed" in result.lower() or "outside allowed" in result.lower()


@pytest.mark.asyncio
async def test_search_in_file_blocked_path(tmp_path):
    """Cannot search file outside allowed paths"""
    config = AiAssistConfig(anthropic_api_key="test", allowed_paths=[str(tmp_path / "allowed")])
    tools = FilesystemTools(config)

    blocked_file = tmp_path / "blocked" / "data.txt"
    blocked_file.parent.mkdir(parents=True, exist_ok=True)
    blocked_file.write_text("secret data")

    result = await tools.execute_tool("search_in_file", {"path": str(blocked_file), "pattern": "secret"})

    assert "not allowed" in result.lower() or "outside allowed" in result.lower()


@pytest.mark.asyncio
async def test_empty_allowed_paths_allows_all(tmp_path):
    """When allowed_paths is empty, all paths are accessible (backwards compat)"""
    config = AiAssistConfig(anthropic_api_key="test", allowed_paths=[])
    tools = FilesystemTools(config)

    test_file = tmp_path / "anywhere.txt"
    test_file.write_text("accessible")

    result = await tools.execute_tool("read_file", {"path": str(test_file)})
    assert "accessible" in result


# --- Phase 4: Confirmation for destructive tools ---


@pytest.mark.asyncio
async def test_create_directory_prompts_confirmation(tmp_path):
    """create_directory triggers confirmation callback when in confirm_tools"""
    config = AiAssistConfig(
        anthropic_api_key="test",
        allowed_paths=[str(tmp_path)],
        confirm_tools=["internal__create_directory"],
    )
    tools = FilesystemTools(config)

    callback_called = False

    async def mock_callback(command: str) -> bool:
        nonlocal callback_called
        callback_called = True
        return True

    tools.confirmation_callback = mock_callback

    result = await tools.execute_tool("create_directory", {"path": str(tmp_path / "new_dir")})

    assert callback_called
    assert "created" in result.lower() or "Error" not in result


@pytest.mark.asyncio
async def test_configurable_confirm_tools_list(tmp_path):
    """Config controls which tools prompt for confirmation"""
    # create_directory NOT in confirm_tools - should proceed without callback
    config = AiAssistConfig(
        anthropic_api_key="test",
        allowed_paths=[str(tmp_path)],
        confirm_tools=[],
    )
    tools = FilesystemTools(config)

    callback_called = False

    async def mock_callback(command: str) -> bool:
        nonlocal callback_called
        callback_called = True
        return True

    tools.confirmation_callback = mock_callback

    result = await tools.execute_tool("create_directory", {"path": str(tmp_path / "no_confirm_dir")})

    assert not callback_called
    assert "created" in result.lower()
