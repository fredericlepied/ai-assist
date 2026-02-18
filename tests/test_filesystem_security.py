"""Tests for filesystem tools security: command allowlist, path restrictions, and confirmations"""

import json
import re
from datetime import date

import pytest

from ai_assist.config import AiAssistConfig
from ai_assist.filesystem_tools import ALLOWED_COMMANDS_FILE, ALLOWED_PATHS_FILE, FilesystemTools

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


# --- Phase 5: Persistent command allowlist ---


def test_add_permanent_allowed_command(tmp_path):
    """add_permanent_allowed_command persists command to JSON file"""
    config = AiAssistConfig(anthropic_api_key="test")
    tools = FilesystemTools(config)

    json_file = tmp_path / ALLOWED_COMMANDS_FILE
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("ai_assist.filesystem_tools.get_config_dir", lambda: tmp_path)

        tools.add_permanent_allowed_command("curl")

    assert "curl" in tools.allowed_commands

    data = json.loads(json_file.read_text())
    assert "curl" in data


def test_add_permanent_allowed_command_no_duplicate(tmp_path):
    """Adding the same command twice does not create duplicates"""
    config = AiAssistConfig(anthropic_api_key="test")
    tools = FilesystemTools(config)

    json_file = tmp_path / ALLOWED_COMMANDS_FILE
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("ai_assist.filesystem_tools.get_config_dir", lambda: tmp_path)

        tools.add_permanent_allowed_command("curl")
        tools.add_permanent_allowed_command("curl")

    data = json.loads(json_file.read_text())
    assert data.count("curl") == 1


def test_load_user_allowed_commands(tmp_path):
    """Commands from persistent JSON file are loaded at init"""
    json_file = tmp_path / ALLOWED_COMMANDS_FILE
    json_file.write_text(json.dumps(["docker", "podman"]))

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("ai_assist.filesystem_tools.get_config_dir", lambda: tmp_path)

        config = AiAssistConfig(anthropic_api_key="test")
        tools = FilesystemTools(config)

    assert "docker" in tools.allowed_commands
    assert "podman" in tools.allowed_commands


def test_load_user_allowed_commands_no_file():
    """Missing JSON file does not cause errors"""
    config = AiAssistConfig(anthropic_api_key="test")
    tools = FilesystemTools(config)
    # Should not raise - the file simply doesn't exist
    assert len(tools.allowed_commands) > 0  # has defaults


def test_load_user_allowed_commands_corrupt_json(tmp_path):
    """Corrupt JSON file is silently ignored"""
    json_file = tmp_path / ALLOWED_COMMANDS_FILE
    json_file.write_text("not valid json {{{")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("ai_assist.filesystem_tools.get_config_dir", lambda: tmp_path)

        config = AiAssistConfig(anthropic_api_key="test")
        tools = FilesystemTools(config)

    # Should still have defaults, no crash
    assert len(tools.allowed_commands) > 0


@pytest.mark.asyncio
async def test_permanently_allowed_command_executes(tmp_path):
    """A permanently added command runs without confirmation callback"""
    json_file = tmp_path / ALLOWED_COMMANDS_FILE
    json_file.write_text(json.dumps(["echo"]))

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("ai_assist.filesystem_tools.get_config_dir", lambda: tmp_path)

        config = AiAssistConfig(anthropic_api_key="test", allowed_commands=["ls"])
        tools = FilesystemTools(config)

    # echo is not in the config allowlist but is in the persistent file
    result = await tools.execute_tool("execute_command", {"command": "echo persistent"})
    assert "persistent" in result


# --- Phase 6: Date and time tools ---


@pytest.mark.asyncio
async def test_get_today_date():
    """get_today_date returns today's date in YYYY-MM-DD format"""
    config = AiAssistConfig(anthropic_api_key="test")
    tools = FilesystemTools(config)

    result = await tools.execute_tool("get_today_date", {})

    assert re.match(r"^\d{4}-\d{2}-\d{2}$", result)
    assert result == date.today().isoformat()


@pytest.mark.asyncio
async def test_get_current_time():
    """get_current_time returns current date and time in ISO format"""
    config = AiAssistConfig(anthropic_api_key="test")
    tools = FilesystemTools(config)

    result = await tools.execute_tool("get_current_time", {})

    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", result)


# --- Phase 7: Interactive path approval ---


@pytest.mark.asyncio
async def test_blocked_path_calls_path_confirmation_callback(tmp_path):
    """When path is blocked and path_confirmation_callback is set, it is called"""
    config = AiAssistConfig(
        anthropic_api_key="test",
        allowed_paths=[str(tmp_path / "allowed")],
    )
    tools = FilesystemTools(config)

    blocked_file = tmp_path / "blocked" / "data.txt"
    blocked_file.parent.mkdir(parents=True, exist_ok=True)
    blocked_file.write_text("hello")

    callback_called_with = None

    async def mock_path_callback(description: str) -> bool:
        nonlocal callback_called_with
        callback_called_with = description
        return True

    tools.path_confirmation_callback = mock_path_callback

    result = await tools.execute_tool("read_file", {"path": str(blocked_file)})

    assert callback_called_with is not None
    assert "hello" in result


@pytest.mark.asyncio
async def test_blocked_path_user_rejects(tmp_path):
    """When user rejects path via callback, access is denied"""
    config = AiAssistConfig(
        anthropic_api_key="test",
        allowed_paths=[str(tmp_path / "allowed")],
    )
    tools = FilesystemTools(config)

    blocked_file = tmp_path / "blocked" / "data.txt"
    blocked_file.parent.mkdir(parents=True, exist_ok=True)
    blocked_file.write_text("secret")

    async def reject_callback(description: str) -> bool:
        return False

    tools.path_confirmation_callback = reject_callback

    result = await tools.execute_tool("read_file", {"path": str(blocked_file)})

    assert "rejected" in result.lower() or "not allowed" in result.lower()
    assert "secret" not in result


@pytest.mark.asyncio
async def test_blocked_path_no_callback_still_blocks(tmp_path):
    """Without callback, blocked paths return error (existing behavior)"""
    config = AiAssistConfig(
        anthropic_api_key="test",
        allowed_paths=[str(tmp_path / "allowed")],
    )
    tools = FilesystemTools(config)

    blocked_file = tmp_path / "blocked" / "data.txt"
    blocked_file.parent.mkdir(parents=True, exist_ok=True)
    blocked_file.write_text("secret")

    # No path_confirmation_callback set
    result = await tools.execute_tool("read_file", {"path": str(blocked_file)})

    assert "not allowed" in result.lower() or "outside allowed" in result.lower()


@pytest.mark.asyncio
async def test_path_callback_works_for_search_in_file(tmp_path):
    """Path confirmation callback works for search_in_file too"""
    config = AiAssistConfig(
        anthropic_api_key="test",
        allowed_paths=[str(tmp_path / "allowed")],
    )
    tools = FilesystemTools(config)

    blocked_file = tmp_path / "blocked" / "data.txt"
    blocked_file.parent.mkdir(parents=True, exist_ok=True)
    blocked_file.write_text("findme\nother line")

    async def approve_callback(description: str) -> bool:
        return True

    tools.path_confirmation_callback = approve_callback

    result = await tools.execute_tool("search_in_file", {"path": str(blocked_file), "pattern": "findme"})

    assert "findme" in result


@pytest.mark.asyncio
async def test_path_callback_works_for_list_directory(tmp_path):
    """Path confirmation callback works for list_directory too"""
    config = AiAssistConfig(
        anthropic_api_key="test",
        allowed_paths=[str(tmp_path / "allowed")],
    )
    tools = FilesystemTools(config)

    blocked_dir = tmp_path / "blocked"
    blocked_dir.mkdir(parents=True, exist_ok=True)
    (blocked_dir / "file.txt").write_text("x")

    async def approve_callback(description: str) -> bool:
        return True

    tools.path_confirmation_callback = approve_callback

    result = await tools.execute_tool("list_directory", {"path": str(blocked_dir)})

    assert "file.txt" in result


# --- Phase 8: Persistent path allowlist ---


def test_add_permanent_allowed_path(tmp_path):
    """add_permanent_allowed_path persists path to JSON file"""
    config = AiAssistConfig(anthropic_api_key="test")
    tools = FilesystemTools(config)

    new_path = str(tmp_path / "new-allowed")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("ai_assist.filesystem_tools.get_config_dir", lambda: tmp_path)
        tools.add_permanent_allowed_path(new_path)

    from pathlib import Path

    assert Path(new_path).resolve() in tools.allowed_paths

    json_file = tmp_path / ALLOWED_PATHS_FILE
    data = json.loads(json_file.read_text())
    assert new_path in data


def test_add_permanent_allowed_path_no_duplicate(tmp_path):
    """Adding the same path twice does not create duplicates"""
    config = AiAssistConfig(anthropic_api_key="test")
    tools = FilesystemTools(config)

    new_path = str(tmp_path / "dup-path")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("ai_assist.filesystem_tools.get_config_dir", lambda: tmp_path)
        tools.add_permanent_allowed_path(new_path)
        tools.add_permanent_allowed_path(new_path)

    json_file = tmp_path / ALLOWED_PATHS_FILE
    data = json.loads(json_file.read_text())
    assert data.count(new_path) == 1


def test_load_user_allowed_paths(tmp_path):
    """Paths from persistent JSON file are loaded at init"""
    json_file = tmp_path / ALLOWED_PATHS_FILE
    json_file.write_text(json.dumps(["/opt/custom", "/data/shared"]))

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("ai_assist.filesystem_tools.get_config_dir", lambda: tmp_path)
        config = AiAssistConfig(anthropic_api_key="test")
        tools = FilesystemTools(config)

    from pathlib import Path

    assert Path("/opt/custom").resolve() in tools.allowed_paths
    assert Path("/data/shared").resolve() in tools.allowed_paths


def test_load_user_allowed_paths_no_file():
    """Missing JSON file does not cause errors"""
    config = AiAssistConfig(anthropic_api_key="test")
    tools = FilesystemTools(config)
    # Should not raise - the file simply doesn't exist
    assert len(tools.allowed_paths) > 0  # has defaults


def test_load_user_allowed_paths_corrupt_json(tmp_path):
    """Corrupt JSON file is silently ignored"""
    json_file = tmp_path / ALLOWED_PATHS_FILE
    json_file.write_text("not valid json {{{")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("ai_assist.filesystem_tools.get_config_dir", lambda: tmp_path)
        config = AiAssistConfig(anthropic_api_key="test")
        tools = FilesystemTools(config)

    # Should still have defaults, no crash
    assert len(tools.allowed_paths) > 0


@pytest.mark.asyncio
async def test_permanently_allowed_path_accessible(tmp_path):
    """A permanently added path is accessible without callback"""
    target_dir = tmp_path / "persistent-allowed"
    target_dir.mkdir()
    test_file = target_dir / "data.txt"
    test_file.write_text("persistent data")

    json_file = tmp_path / ALLOWED_PATHS_FILE
    json_file.write_text(json.dumps([str(target_dir)]))

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("ai_assist.filesystem_tools.get_config_dir", lambda: tmp_path)
        config = AiAssistConfig(
            anthropic_api_key="test",
            allowed_paths=[str(tmp_path / "other")],
        )
        tools = FilesystemTools(config)

    result = await tools.execute_tool("read_file", {"path": str(test_file)})
    assert "persistent data" in result


# --- Phase 9: Local skill paths auto-allowed ---


def test_local_skill_paths_added_to_allowed_paths(tmp_path):
    """Local skills have their paths automatically added to allowed_paths on startup"""

    from ai_assist.agent import AiAssistAgent
    from ai_assist.skills_manager import InstalledSkill

    config = AiAssistConfig(
        anthropic_api_key="test-key",
        model="claude-3-5-sonnet-20241022",
        mcp_servers={},
    )
    agent = AiAssistAgent(config)

    # Simulate a local skill in the installed list
    local_path = tmp_path / "my-local-skill"
    local_path.mkdir()
    agent.skills_manager.installed_skills = [
        InstalledSkill(
            name="test-local",
            source=str(local_path),
            source_type="local",
            branch="main",
            installed_at="2026-01-01T00:00:00",
            cache_path=str(local_path),
        ),
    ]

    agent._allow_local_skill_paths()

    assert local_path.resolve() in agent.filesystem_tools.allowed_paths


def test_git_skill_paths_not_added_to_allowed_paths(tmp_path):
    """Git skills (already under config dir) are not redundantly added"""
    from ai_assist.agent import AiAssistAgent
    from ai_assist.skills_manager import InstalledSkill

    config = AiAssistConfig(
        anthropic_api_key="test-key",
        model="claude-3-5-sonnet-20241022",
        mcp_servers={},
    )
    agent = AiAssistAgent(config)

    initial_count = len(agent.filesystem_tools.allowed_paths)

    agent.skills_manager.installed_skills = [
        InstalledSkill(
            name="some-git-skill",
            source="owner/repo",
            source_type="git",
            branch="main",
            installed_at="2026-01-01T00:00:00",
            cache_path=str(tmp_path / "cache"),
        ),
    ]

    agent._allow_local_skill_paths()

    assert len(agent.filesystem_tools.allowed_paths) == initial_count
