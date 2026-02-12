"""Tests for TUI components"""

from unittest.mock import MagicMock

from prompt_toolkit.document import Document

from ai_assist.tui import AiAssistCompleter, format_tool_args, format_tool_display_name


def test_ai_assist_completer_initialization():
    """Test AiAssistCompleter initializes with commands"""
    completer = AiAssistCompleter()

    assert len(completer.commands) > 0
    assert "/status" in completer.commands
    assert "/help" in completer.commands


def test_command_completion_prefix():
    """Test completion works with command prefix"""
    completer = AiAssistCompleter()

    # Create a document with /st
    document = Document("/st", cursor_position=3)

    completions = list(completer.get_completions(document, None))

    assert len(completions) == 1
    assert completions[0].text == "/status"
    assert str(completions[0].display) == "/status" or "/status" in str(completions[0].display)


def test_command_completion_multiple_matches():
    """Test completion with multiple matches"""
    completer = AiAssistCompleter()

    # Create a document with /
    document = Document("/", cursor_position=1)

    completions = list(completer.get_completions(document, None))

    # Should return all commands
    assert len(completions) == len(completer.commands)


def test_command_completion_no_prefix():
    """Test no completion without / prefix"""
    completer = AiAssistCompleter()

    # Create a document without /
    document = Document("status", cursor_position=6)

    completions = list(completer.get_completions(document, None))

    # Should return no completions
    assert len(completions) == 0


def test_command_completion_exact_match():
    """Test completion for exact match"""
    completer = AiAssistCompleter()

    # Create a document with /exit
    document = Document("/exit", cursor_position=5)

    completions = list(completer.get_completions(document, None))

    # Should return /exit
    assert len(completions) == 1
    assert completions[0].text == "/exit"


def test_command_completion_case_insensitive():
    """Test completion is case insensitive"""
    completer = AiAssistCompleter()

    # Create a document with /ST
    document = Document("/ST", cursor_position=3)

    completions = list(completer.get_completions(document, None))

    assert len(completions) == 1
    assert completions[0].text == "/status"


def test_command_description_provided():
    """Test completion includes descriptions"""
    completer = AiAssistCompleter()

    document = Document("/st", cursor_position=3)

    completions = list(completer.get_completions(document, None))

    assert len(completions) == 1
    assert completions[0].display_meta is not None
    assert "statistics" in str(completions[0].display_meta).lower()


def test_completion_quit_commands():
    """Test completion for quit/exit commands"""
    completer = AiAssistCompleter()

    # Test /q
    document = Document("/q", cursor_position=2)
    completions = list(completer.get_completions(document, None))

    assert len(completions) == 1
    assert completions[0].text == "/quit"


def test_completion_help_command():
    """Test completion for help command"""
    completer = AiAssistCompleter()

    document = Document("/h", cursor_position=2)
    completions = list(completer.get_completions(document, None))

    assert any(c.text == "/help" for c in completions)


def test_completion_clear_cache_command():
    """Test completion for clear commands"""
    completer = AiAssistCompleter()

    document = Document("/clear", cursor_position=6)
    completions = list(completer.get_completions(document, None))

    # Should have both /clear and /clear-cache
    assert len(completions) == 2
    completion_texts = {c.text for c in completions}
    assert "/clear" in completion_texts
    assert "/clear-cache" in completion_texts


def _make_agent_with_prompts():
    """Helper to create a mock agent with available_prompts."""
    agent = MagicMock()
    rca_prompt = MagicMock()
    rca_prompt.description = "Root cause analysis"
    report_prompt = MagicMock()
    report_prompt.description = "Generate a report"
    agent.available_prompts = {
        "dci": {
            "rca": rca_prompt,
            "report": report_prompt,
        }
    }
    return agent


def test_mid_sentence_mcp_prompt_completion():
    """Test MCP prompt completion works mid-sentence"""
    agent = _make_agent_with_prompts()
    completer = AiAssistCompleter(agent=agent)

    document = Document("analyze with /dci/r", cursor_position=19)
    completions = list(completer.get_completions(document, None))

    texts = [c.text for c in completions]
    assert "/dci/rca" in texts
    assert "/dci/report" in texts


def test_mid_sentence_server_completion():
    """Test server name completion works mid-sentence"""
    agent = _make_agent_with_prompts()
    completer = AiAssistCompleter(agent=agent)

    document = Document("run /dc", cursor_position=7)
    completions = list(completer.get_completions(document, None))

    texts = [c.text for c in completions]
    assert "/dci/" in texts


def test_mid_sentence_no_builtin_commands():
    """Test that built-in commands are NOT suggested mid-sentence"""
    agent = _make_agent_with_prompts()
    completer = AiAssistCompleter(agent=agent)

    document = Document("check /st", cursor_position=9)
    completions = list(completer.get_completions(document, None))

    texts = [c.text for c in completions]
    assert "/status" not in texts


def test_mid_sentence_no_completion_without_slash():
    """Test no completion when last word doesn't start with /"""
    agent = _make_agent_with_prompts()
    completer = AiAssistCompleter(agent=agent)

    document = Document("hello world", cursor_position=11)
    completions = list(completer.get_completions(document, None))

    assert len(completions) == 0


def test_format_tool_display_name():
    """Test format_tool_display_name converts internal names to user-friendly display"""
    assert format_tool_display_name("mcp__dci__search") == "dci → search"
    assert format_tool_display_name("mcp__dci__search_dci_jobs") == "dci → search dci jobs"
    assert format_tool_display_name("internal__write_report") == "internal → write report"
    assert format_tool_display_name("simple_tool") == "simple tool"


def test_format_tool_args():
    """Test format_tool_args formats and truncates arguments"""
    # Simple args
    result = format_tool_args({"query": "test", "limit": 10})
    assert result == "query=test, limit=10"

    # Truncation at 100 chars
    long_value = "x" * 150
    result = format_tool_args({"data": long_value})
    assert result == f"data={'x' * 100}..."
    assert len(result) < 150

    # Empty dict
    assert format_tool_args({}) == ""

    # Custom max_len
    result = format_tool_args({"key": "abcdefghij"}, max_len=5)
    assert result == "key=abcde..."
