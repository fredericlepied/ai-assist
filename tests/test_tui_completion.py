"""Tests for TUI completion with skills"""

from pathlib import Path

from prompt_toolkit.document import Document

from ai_assist.agent import AiAssistAgent
from ai_assist.config import AiAssistConfig
from ai_assist.tui import AiAssistCompleter


def test_skill_command_completion():
    """Test that skill commands appear in completion"""
    # Create agent without real MCP connections
    config = AiAssistConfig(
        anthropic_api_key="test-key",
        model="claude-3-5-sonnet-20241022",
        mcp_servers={},
    )
    agent = AiAssistAgent(config)

    completer = AiAssistCompleter(agent=agent)

    # Test /skill prefix completion
    doc = Document("/ski", cursor_position=4)
    completions = list(completer.get_completions(doc, None))

    # Should suggest skill commands
    commands = [c.text for c in completions]
    assert "/skill/install" in commands
    assert "/skill/uninstall" in commands
    assert "/skill/list" in commands


def test_skill_install_completion():
    """Test /skill/install shows examples"""
    config = AiAssistConfig(
        anthropic_api_key="test-key",
        model="claude-3-5-sonnet-20241022",
        mcp_servers={},
    )
    agent = AiAssistAgent(config)

    completer = AiAssistCompleter(agent=agent)

    # Test /skill/install completion
    doc = Document("/skill/install ", cursor_position=15)  # "/skill/install " is 15 chars
    completions = list(completer.get_completions(doc, None))

    # Should suggest example patterns
    commands = [c.text for c in completions]
    assert any("anthropics/skills" in cmd for cmd in commands)
    assert any("/path/to/skill" in cmd for cmd in commands)


def test_skill_uninstall_completion():
    """Test /skill/uninstall completes with installed skills"""
    config = AiAssistConfig(
        anthropic_api_key="test-key",
        model="claude-3-5-sonnet-20241022",
        mcp_servers={},
    )
    agent = AiAssistAgent(config)

    # Set test file for skills
    agent.skills_manager.installed_skills_file = Path("/tmp/test-completion-skills.json")

    # Install test skill
    agent.skills_manager.install_skill("/tmp/test-skills/hello@main")

    completer = AiAssistCompleter(agent=agent)

    # Test /skill/uninstall completion
    doc = Document("/skill/uninstall ", cursor_position=17)
    completions = list(completer.get_completions(doc, None))

    # Should suggest installed skill
    commands = [c.text for c in completions]
    assert any("hello" in cmd for cmd in commands)

    # Clean up
    agent.skills_manager.uninstall_skill("hello")
    Path("/tmp/test-completion-skills.json").unlink()


def test_skill_list_completion():
    """Test /skill/list completes"""
    config = AiAssistConfig(
        anthropic_api_key="test-key",
        model="claude-3-5-sonnet-20241022",
        mcp_servers={},
    )
    agent = AiAssistAgent(config)

    completer = AiAssistCompleter(agent=agent)

    # Test /skill/list completion
    doc = Document("/skill/lis", cursor_position=10)
    completions = list(completer.get_completions(doc, None))

    # Should suggest /skill/list
    commands = [c.text for c in completions]
    assert "/skill/list" in commands
