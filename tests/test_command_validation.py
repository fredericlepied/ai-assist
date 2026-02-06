"""Tests for command validation in main.py"""

import subprocess
import sys


def test_unknown_command_exits_with_error():
    """Test that unknown commands exit with error message"""
    result = subprocess.run(
        [sys.executable, "-m", "ai_assist.main", "/unknown-command"], capture_output=True, text=True
    )

    assert result.returncode == 1
    output = result.stdout + result.stderr
    assert "Unknown command '/unknown-command'" in output
    assert "ai-assist /help" in output


def test_command_without_slash_gives_helpful_error():
    """Test that commands without / get a helpful error"""
    result = subprocess.run([sys.executable, "-m", "ai_assist.main", "help"], capture_output=True, text=True)

    assert result.returncode == 1
    output = result.stdout + result.stderr
    assert "Commands must start with /" in output
    assert "Did you mean: /help?" in output


def test_help_command_works():
    """Test that /help command works"""
    result = subprocess.run([sys.executable, "-m", "ai_assist.main", "/help"], capture_output=True, text=True)

    assert result.returncode == 0
    assert "Available commands:" in result.stdout
    assert "/monitor" in result.stdout
    assert "/query" in result.stdout


def test_unknown_command_does_not_initialize_agent():
    """Test that unknown commands don't initialize agent or connect to MCP servers"""
    result = subprocess.run([sys.executable, "-m", "ai_assist.main", "/invalid"], capture_output=True, text=True)

    output = result.stdout + result.stderr

    # Should not see any agent initialization messages
    assert "Using Vertex AI" not in output
    assert "Connected to" not in output

    # Should see the error message immediately
    assert "Unknown command '/invalid'" in output
    assert result.returncode == 1
