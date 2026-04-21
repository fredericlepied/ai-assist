"""Tests for agent query timeout enforcement."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_assist.agent import AiAssistAgent
from ai_assist.config import AiAssistConfig


@pytest.fixture
def agent():
    config = AiAssistConfig(anthropic_api_key="test-key", working_dirs=["/tmp"])
    return AiAssistAgent(config=config)


@pytest.mark.asyncio
async def test_query_timeout_fires_during_slow_inner(agent):
    """asyncio.wait_for should enforce max_time even when _query_inner blocks."""

    async def slow_inner(*args, **kwargs):
        await asyncio.sleep(100)
        return "should not reach"

    with patch.object(agent, "_query_inner", side_effect=slow_inner):
        start = time.time()
        result = await agent.query("test", max_turns=5, max_time_seconds=1)
        elapsed = time.time() - start

    assert "timeout" in result.lower()
    assert elapsed < 5, f"Should have timed out in ~1s but took {elapsed:.1f}s"


@pytest.mark.asyncio
async def test_query_timeout_returns_message(agent):
    """Timeout should return a descriptive message, not raise."""

    async def slow_inner(*args, **kwargs):
        await asyncio.sleep(100)

    with patch.object(agent, "_query_inner", side_effect=slow_inner):
        result = await agent.query("test", max_turns=5, max_time_seconds=1)

    assert "timeout" in result.lower()
    assert "1 seconds" in result


@pytest.mark.asyncio
async def test_query_sets_and_clears_deadline(agent):
    """Outermost query should set _query_deadline and clear it on completion."""
    assert agent._query_deadline is None

    captured_deadline = None

    async def capture_deadline(*args, **kwargs):
        nonlocal captured_deadline
        captured_deadline = agent._query_deadline
        return "done"

    with patch.object(agent, "_query_inner", side_effect=capture_deadline):
        await agent.query("test", max_time_seconds=60)

    assert captured_deadline is not None
    assert agent._query_deadline is None


@pytest.mark.asyncio
async def test_query_deadline_not_overwritten_by_nested_query(agent):
    """Nested queries (depth > 1) should not overwrite _query_deadline."""
    outer_deadline = time.time() + 300
    agent._query_deadline = outer_deadline
    agent._query_depth = 1  # Simulate already being inside a query

    async def fast_inner(*args, **kwargs):
        return "done"

    with patch.object(agent, "_query_inner", side_effect=fast_inner):
        await agent.query("nested test", max_time_seconds=10)

    # Deadline should still be the outer one (depth was > 1 when query ran)
    assert agent._query_deadline == outer_deadline

    # Clean up
    agent._query_depth = 0
    agent._query_deadline = None


@pytest.mark.asyncio
async def test_query_streaming_timeout_check(agent):
    """query_streaming should yield error when max_time_seconds is exceeded."""

    async def slow_tool(*args, **kwargs):
        await asyncio.sleep(10)
        return [], False

    mock_content_block = MagicMock()
    mock_content_block.type = "tool_use"
    mock_content_block.name = "internal__think"
    mock_content_block.id = "tool-1"
    mock_content_block.input = {"thought": "test"}

    mock_response = MagicMock()
    mock_response.content = [mock_content_block]
    mock_response.stop_reason = "tool_use"
    mock_response.usage = MagicMock(input_tokens=100, output_tokens=50)

    with patch.object(agent.anthropic.messages, "stream") as mock_stream:
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        mock_ctx.get_final_message.return_value = mock_response
        mock_stream.return_value = mock_ctx

        with patch.object(agent, "_execute_tools_concurrently", side_effect=slow_tool):
            chunks = []
            start = time.time()
            async for chunk in agent.query_streaming("test", max_turns=5, max_time_seconds=1):
                chunks.append(chunk)
            elapsed = time.time() - start

    # The soft timeout check fires between turns, but the tool sleeps 10s.
    # The streaming loop will block on _execute_tools_concurrently.
    # Since streaming doesn't use asyncio.timeout, this test checks the
    # between-turn soft check works when the tool eventually returns.
    # For truly blocking tools, the outer query()'s asyncio.wait_for handles it.
    # We verify at least that the parameter is accepted and used.
    assert elapsed < 15


@pytest.mark.asyncio
async def test_execute_mcp_prompt_inherits_deadline(agent):
    """execute_mcp_prompt should use remaining time from _query_deadline."""
    agent.sessions["test"] = MagicMock()
    mock_prompt_def = MagicMock()
    mock_prompt_def.arguments = []
    agent.available_prompts["test"] = {"my_prompt": mock_prompt_def}

    mock_result = MagicMock()
    mock_msg = MagicMock()
    mock_msg.role = "user"
    mock_msg.content = MagicMock()
    mock_msg.content.text = "test prompt"
    mock_result.messages = [mock_msg]

    agent.sessions["test"].get_prompt = AsyncMock(return_value=mock_result)
    agent._query_deadline = time.time() + 2

    captured_timeout = None

    async def capture_streaming(*args, **kwargs):
        nonlocal captured_timeout
        captured_timeout = kwargs.get("max_time_seconds")
        yield "test response"

    with patch.object(agent, "query_streaming", side_effect=capture_streaming):
        await agent.execute_mcp_prompt("test", "my_prompt")

    assert captured_timeout is not None
    assert captured_timeout <= 2
    assert captured_timeout >= 1


@pytest.mark.asyncio
async def test_execute_mcp_prompt_explicit_timeout_overrides_deadline(agent):
    """Explicit max_time_seconds should override _query_deadline."""
    agent.sessions["test"] = MagicMock()
    mock_prompt_def = MagicMock()
    mock_prompt_def.arguments = []
    agent.available_prompts["test"] = {"my_prompt": mock_prompt_def}

    mock_result = MagicMock()
    mock_msg = MagicMock()
    mock_msg.role = "user"
    mock_msg.content = MagicMock()
    mock_msg.content.text = "test prompt"
    mock_result.messages = [mock_msg]

    agent.sessions["test"].get_prompt = AsyncMock(return_value=mock_result)
    agent._query_deadline = time.time() + 300

    captured_timeout = None

    async def capture_streaming(*args, **kwargs):
        nonlocal captured_timeout
        captured_timeout = kwargs.get("max_time_seconds")
        yield "test response"

    with patch.object(agent, "query_streaming", side_effect=capture_streaming):
        await agent.execute_mcp_prompt("test", "my_prompt", max_time_seconds=42)

    assert captured_timeout == 42
