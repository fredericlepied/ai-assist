"""Tests for TUI components"""

from prompt_toolkit.document import Document

from ai_assist.tui import AiAssistCompleter


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
