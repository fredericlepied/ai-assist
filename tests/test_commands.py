"""Tests for command validation utilities"""

import pytest
from ai_assist.commands import (
    is_valid_interactive_command,
    is_valid_cli_command,
    get_command_suggestion,
    INTERACTIVE_COMMANDS,
    CLI_COMMANDS
)


class TestInteractiveCommandValidation:
    """Tests for interactive command validation"""

    def test_valid_interactive_commands(self):
        """Test that valid interactive commands are recognized"""
        for cmd in INTERACTIVE_COMMANDS:
            assert is_valid_interactive_command(cmd)

    def test_invalid_interactive_command(self):
        """Test that invalid commands starting with / are rejected"""
        assert not is_valid_interactive_command("/invalid")
        assert not is_valid_interactive_command("/unknown-command")

    def test_non_command_input_is_valid(self):
        """Test that input without / is considered valid (for agent)"""
        assert is_valid_interactive_command("what is the weather?")
        assert is_valid_interactive_command("hello")
        assert is_valid_interactive_command("analyze DCI jobs")

    def test_command_with_arguments(self):
        """Test that commands with arguments are validated by base command"""
        assert is_valid_interactive_command("/kg-save on")
        assert is_valid_interactive_command("/kg-save off")
        assert not is_valid_interactive_command("/invalid argument")


class TestCLICommandValidation:
    """Tests for CLI command validation"""

    def test_valid_cli_commands(self):
        """Test that valid CLI commands are recognized"""
        valid_commands = [
            "monitor", "query", "interactive", "status", "clear-cache",
            "identity-show", "identity-init", "kg-stats", "kg-asof",
            "kg-late", "kg-changes", "kg-show", "help"
        ]
        for cmd in valid_commands:
            assert is_valid_cli_command(cmd), f"Command {cmd} should be valid"

    def test_invalid_cli_command(self):
        """Test that invalid CLI commands are rejected"""
        assert not is_valid_cli_command("invalid")
        assert not is_valid_cli_command("unknown-command")


class TestCommandSuggestion:
    """Tests for command suggestion messages"""

    def test_interactive_suggestion_shows_available_commands(self):
        """Test that interactive suggestion shows available commands"""
        msg = get_command_suggestion("/invalid", is_interactive=True)
        assert "Unknown command '/invalid'" in msg
        assert "Available commands:" in msg
        assert "/help" in msg
        assert "/exit" in msg

    def test_interactive_suggestion_mentions_asking_without_slash(self):
        """Test that interactive suggestion mentions asking without slash"""
        msg = get_command_suggestion("/invalid", is_interactive=True)
        assert "type a question without the / prefix" in msg.lower()

    def test_cli_suggestion_directs_to_help(self):
        """Test that CLI suggestion directs to help command"""
        msg = get_command_suggestion("/invalid", is_interactive=False)
        assert "Unknown command '/invalid'" in msg
        assert "ai-assist /help" in msg

    def test_suggestion_formats_command_correctly(self):
        """Test that suggestions format commands correctly"""
        msg = get_command_suggestion("/test", is_interactive=True)
        assert "/test" in msg
