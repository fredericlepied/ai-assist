"""Tests for TUI interactive mode"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from boss.tui_interactive import (
    tui_interactive_mode,
    handle_status_command,
    handle_history_command,
    handle_clear_cache_command,
    handle_help_command
)
from boss.agent import BossAgent
from boss.state import StateManager


@pytest.fixture
def mock_agent():
    """Create a mock agent"""
    agent = AsyncMock(spec=BossAgent)
    agent.query = AsyncMock(return_value="Test response")

    # Mock streaming query to yield text and done signal
    async def mock_query_streaming(prompt, progress_callback=None):
        if progress_callback:
            progress_callback("thinking", 0, 10, None)
            progress_callback("calling_claude", 1, 10, None)
            progress_callback("complete", 1, 10, None)
        yield "Test response"
        yield {"type": "done", "turns": 1}

    agent.query_streaming = mock_query_streaming
    return agent


@pytest.fixture
def mock_state_manager():
    """Create a mock state manager"""
    manager = MagicMock(spec=StateManager)
    manager.get_stats = MagicMock(return_value={"cache_entries": 10, "monitors": 2})
    manager.get_history = MagicMock(return_value=[{"timestamp": "2026-02-05"}])
    manager.cleanup_expired_cache = MagicMock(return_value=5)
    manager.save_conversation_context = MagicMock()
    return manager


@pytest.mark.asyncio
async def test_status_command(mock_state_manager):
    """Test /status command displays statistics"""
    from rich.console import Console
    from io import StringIO

    output = StringIO()
    console = Console(file=output, force_terminal=True)

    await handle_status_command(mock_state_manager, console)

    mock_state_manager.get_stats.assert_called_once()
    output_text = output.getvalue()
    assert "State Statistics" in output_text


@pytest.mark.asyncio
async def test_history_command(mock_state_manager):
    """Test /history command displays recent checks"""
    from rich.console import Console
    from io import StringIO

    output = StringIO()
    console = Console(file=output, force_terminal=True)

    await handle_history_command(mock_state_manager, console)

    mock_state_manager.get_history.assert_called_once_with("jira_monitor", limit=5)
    output_text = output.getvalue()
    assert "Recent Jira checks" in output_text


@pytest.mark.asyncio
async def test_clear_cache_command(mock_state_manager):
    """Test /clear-cache command clears cache"""
    from rich.console import Console
    from io import StringIO

    output = StringIO()
    console = Console(file=output, force_terminal=False)  # Disable colors for testing

    await handle_clear_cache_command(mock_state_manager, console)

    mock_state_manager.cleanup_expired_cache.assert_called_once()
    output_text = output.getvalue()
    assert "Cleared 5 cache entries" in output_text


@pytest.mark.asyncio
async def test_help_command():
    """Test /help command displays help text"""
    from rich.console import Console
    from io import StringIO

    output = StringIO()
    console = Console(file=output, force_terminal=True)

    await handle_help_command(console)

    output_text = output.getvalue()
    assert "BOSS Interactive Mode Help" in output_text
    assert "/status" in output_text
    assert "/history" in output_text


@pytest.mark.asyncio
async def test_tui_mode_initializes(mock_agent, mock_state_manager):
    """Test TUI mode initializes without errors"""
    with patch('boss.tui_interactive.PromptSession') as mock_session_class:
        # Simulate user typing /exit
        mock_session = AsyncMock()
        mock_session.prompt_async = AsyncMock(side_effect=["/exit"])
        mock_session_class.return_value = mock_session

        await tui_interactive_mode(mock_agent, mock_state_manager)

        # Verify session was created
        mock_session_class.assert_called_once()
        # Verify conversation was saved
        mock_state_manager.save_conversation_context.assert_called_once()


@pytest.mark.asyncio
async def test_multiline_input_handling(mock_state_manager):
    """Test multi-line input is parsed correctly"""
    # Create mock agent with streaming support
    agent = AsyncMock(spec=BossAgent)
    streaming_called = []

    async def mock_streaming(prompt, progress_callback=None):
        streaming_called.append(prompt)
        yield "Response to: " + prompt
        yield {"type": "done", "turns": 1}

    agent.query_streaming = mock_streaming

    with patch('boss.tui_interactive.PromptSession') as mock_session_class:
        # Simulate multi-line input then exit
        mock_session = AsyncMock()
        mock_session.prompt_async = AsyncMock(side_effect=[
            "Line 1\nLine 2\nLine 3",
            "/exit"
        ])
        mock_session_class.return_value = mock_session

        await tui_interactive_mode(agent, mock_state_manager)

        # Verify agent was called with multi-line input
        assert len(streaming_called) == 1
        assert streaming_called[0] == "Line 1\nLine 2\nLine 3"


@pytest.mark.asyncio
async def test_empty_input_ignored(mock_agent, mock_state_manager):
    """Test empty input is ignored"""
    with patch('boss.tui_interactive.PromptSession') as mock_session_class:
        mock_session = AsyncMock()
        mock_session.prompt_async = AsyncMock(side_effect=[
            "",  # Empty input
            "   ",  # Whitespace only
            "/exit"
        ])
        mock_session_class.return_value = mock_session

        await tui_interactive_mode(mock_agent, mock_state_manager)

        # Agent should not be called for empty inputs
        mock_agent.query.assert_not_called()


@pytest.mark.asyncio
async def test_conversation_tracking(mock_state_manager):
    """Test conversation context is tracked"""
    # Create mock agent with streaming
    agent = AsyncMock(spec=BossAgent)

    async def mock_streaming(prompt, progress_callback=None):
        yield "Test response"
        yield {"type": "done", "turns": 1}

    agent.query_streaming = mock_streaming

    with patch('boss.tui_interactive.PromptSession') as mock_session_class:
        mock_session = AsyncMock()
        mock_session.prompt_async = AsyncMock(side_effect=[
            "Test question",
            "/exit"
        ])
        mock_session_class.return_value = mock_session

        await tui_interactive_mode(agent, mock_state_manager)

        # Verify conversation was saved with messages
        mock_state_manager.save_conversation_context.assert_called_once()
        call_args = mock_state_manager.save_conversation_context.call_args
        assert call_args[0][0] == "last_interactive_session"
        messages = call_args[0][1]["messages"]
        assert len(messages) == 1
        assert messages[0]["user"] == "Test question"
        assert messages[0]["assistant"] == "Test response"


@pytest.mark.asyncio
async def test_keyboard_interrupt_handling(mock_agent, mock_state_manager):
    """Test KeyboardInterrupt is handled gracefully"""
    with patch('boss.tui_interactive.PromptSession') as mock_session_class:
        mock_session = AsyncMock()
        mock_session.prompt_async = AsyncMock(side_effect=KeyboardInterrupt)
        mock_session_class.return_value = mock_session

        await tui_interactive_mode(mock_agent, mock_state_manager)

        # Should save conversation before exiting
        mock_state_manager.save_conversation_context.assert_called_once()


@pytest.mark.asyncio
async def test_eoferror_handling(mock_agent, mock_state_manager):
    """Test EOFError (Ctrl-D) is handled gracefully"""
    with patch('boss.tui_interactive.PromptSession') as mock_session_class:
        mock_session = AsyncMock()
        mock_session.prompt_async = AsyncMock(side_effect=EOFError)
        mock_session_class.return_value = mock_session

        await tui_interactive_mode(mock_agent, mock_state_manager)

        # Should save conversation before exiting
        mock_state_manager.save_conversation_context.assert_called_once()


@pytest.mark.asyncio
async def test_progress_feedback_callback():
    """Test progress callback is invoked during query"""
    from boss.tui_interactive import query_with_feedback
    from rich.console import Console
    from io import StringIO

    output = StringIO()
    console = Console(file=output, force_terminal=False)

    # Create a mock agent with streaming
    mock_agent = AsyncMock(spec=BossAgent)

    async def mock_streaming(prompt, progress_callback=None):
        # Simulate calling the callback
        if progress_callback:
            progress_callback("thinking", 0, 10, None)
            progress_callback("calling_claude", 1, 10, None)
            progress_callback("executing_tool", 1, 10, "test_tool")
            progress_callback("complete", 1, 10, None)
        yield "Test response"
        yield {"type": "done", "turns": 1}

    mock_agent.query_streaming = mock_streaming

    result = await query_with_feedback(mock_agent, "test prompt", console)

    assert result == "Test response"
    # Check that response was output
    output_text = output.getvalue()
    assert "Test response" in output_text or "BOSS" in output_text


@pytest.mark.asyncio
async def test_feedback_with_tool_calls(mock_state_manager):
    """Test feedback shows tool calls"""
    # Create mock agent with streaming and tool calls
    agent = AsyncMock(spec=BossAgent)

    async def mock_streaming_with_tools(prompt, progress_callback=None):
        if progress_callback:
            progress_callback("thinking", 0, 10, None)
            progress_callback("calling_claude", 1, 10, None)
            progress_callback("executing_tool", 1, 10, "mcp__dci__search_dci_jobs")
            progress_callback("calling_claude", 2, 10, None)
            progress_callback("complete", 2, 10, None)
        # Simulate tool use and response
        yield {"type": "tool_use", "name": "mcp__dci__search_dci_jobs", "id": "1", "input": {}}
        yield "Found 5 failed jobs"
        yield {"type": "done", "turns": 2}

    agent.query_streaming = mock_streaming_with_tools

    with patch('boss.tui_interactive.PromptSession') as mock_session_class:
        mock_session = AsyncMock()
        mock_session.prompt_async = AsyncMock(side_effect=[
            "Find failed jobs",
            "/exit"
        ])
        mock_session_class.return_value = mock_session

        await tui_interactive_mode(agent, mock_state_manager)

        # Verify conversation was tracked
        mock_state_manager.save_conversation_context.assert_called()
        call_args = mock_state_manager.save_conversation_context.call_args
        messages = call_args[0][1]["messages"]
        assert len(messages) == 1
        assert messages[0]["user"] == "Find failed jobs"
        assert messages[0]["assistant"] == "Found 5 failed jobs"
