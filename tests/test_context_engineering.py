"""Tests for context engineering improvements"""

from unittest.mock import MagicMock, patch

from ai_assist.agent import AiAssistAgent
from ai_assist.config import AiAssistConfig
from ai_assist.context import ConversationMemory


class TestTokenBudgetMonitoring:
    """Tests for token usage tracking"""

    def test_model_context_window_known_model(self):
        """Known models return correct context window size"""
        config = AiAssistConfig(anthropic_api_key="test-key", mcp_servers={})
        agent = AiAssistAgent(config)
        # Default model contains "sonnet-4-5"
        assert agent.get_context_window_size() == 200000

    def test_model_context_window_unknown_model(self):
        """Unknown models return default context window"""
        config = AiAssistConfig(anthropic_api_key="test-key", mcp_servers={})
        agent = AiAssistAgent(config)
        agent.config.model = "unknown-model-v1"
        assert agent.get_context_window_size() == 200000

    def test_track_token_usage_basic(self):
        """Token usage is recorded from API response"""
        config = AiAssistConfig(anthropic_api_key="test-key", mcp_servers={})
        agent = AiAssistAgent(config)

        mock_response = MagicMock()
        mock_response.usage.input_tokens = 5000
        mock_response.usage.output_tokens = 1000
        # No cache fields
        del mock_response.usage.cache_creation_input_tokens
        del mock_response.usage.cache_read_input_tokens

        agent._track_token_usage(mock_response, turn=0)

        usage = agent.get_token_usage()
        assert len(usage) == 1
        assert usage[0]["turn"] == 0
        assert usage[0]["input_tokens"] == 5000
        assert usage[0]["output_tokens"] == 1000

    def test_track_token_usage_with_cache(self):
        """Cache metrics are recorded when available"""
        config = AiAssistConfig(anthropic_api_key="test-key", mcp_servers={})
        agent = AiAssistAgent(config)

        mock_response = MagicMock()
        mock_response.usage.input_tokens = 5000
        mock_response.usage.output_tokens = 1000
        mock_response.usage.cache_creation_input_tokens = 2000
        mock_response.usage.cache_read_input_tokens = 3000

        agent._track_token_usage(mock_response, turn=0)

        usage = agent.get_token_usage()
        assert usage[0]["cache_creation_input_tokens"] == 2000
        assert usage[0]["cache_read_input_tokens"] == 3000

    def test_track_token_usage_warns_at_threshold(self):
        """Warning is logged when token usage exceeds threshold"""
        config = AiAssistConfig(anthropic_api_key="test-key", mcp_servers={})
        agent = AiAssistAgent(config)

        mock_response = MagicMock()
        mock_response.usage.input_tokens = 170000  # 85% of 200K
        mock_response.usage.output_tokens = 1000
        del mock_response.usage.cache_creation_input_tokens
        del mock_response.usage.cache_read_input_tokens

        with patch("logging.warning") as mock_warn:
            agent._track_token_usage(mock_response, turn=0)
            mock_warn.assert_called_once()
            assert "Context budget warning" in mock_warn.call_args[0][0]

    def test_track_token_usage_no_warn_below_threshold(self):
        """No warning when token usage is below threshold"""
        config = AiAssistConfig(anthropic_api_key="test-key", mcp_servers={})
        agent = AiAssistAgent(config)

        mock_response = MagicMock()
        mock_response.usage.input_tokens = 100000  # 50% of 200K
        mock_response.usage.output_tokens = 1000
        del mock_response.usage.cache_creation_input_tokens
        del mock_response.usage.cache_read_input_tokens

        with patch("logging.warning") as mock_warn:
            agent._track_token_usage(mock_response, turn=0)
            mock_warn.assert_not_called()

    def test_get_token_usage_returns_copy(self):
        """get_token_usage returns a copy, not the original list"""
        config = AiAssistConfig(anthropic_api_key="test-key", mcp_servers={})
        agent = AiAssistAgent(config)

        mock_response = MagicMock()
        mock_response.usage.input_tokens = 5000
        mock_response.usage.output_tokens = 1000
        del mock_response.usage.cache_creation_input_tokens
        del mock_response.usage.cache_read_input_tokens

        agent._track_token_usage(mock_response, turn=0)

        usage1 = agent.get_token_usage()
        usage2 = agent.get_token_usage()
        assert usage1 is not usage2

    def test_track_token_usage_no_usage_field(self):
        """Handles response without usage field gracefully"""
        config = AiAssistConfig(anthropic_api_key="test-key", mcp_servers={})
        agent = AiAssistAgent(config)

        mock_response = MagicMock(spec=[])  # No usage attribute

        agent._track_token_usage(mock_response, turn=0)
        assert len(agent.get_token_usage()) == 0


class TestToolResultTruncation:
    """Tests for _truncate_tool_result"""

    def test_short_result_unchanged(self):
        """Results under max_size are returned as-is"""
        result = "Short result"
        assert AiAssistAgent._truncate_tool_result(result) == result

    def test_long_result_truncated(self):
        """Results over max_size are truncated with message"""
        result = "x" * 25000
        truncated = AiAssistAgent._truncate_tool_result(result)
        assert len(truncated) < len(result)
        assert "Result truncated" in truncated
        assert "25000 chars total" in truncated

    def test_custom_max_size(self):
        """Custom max_size is respected"""
        result = "x" * 500
        truncated = AiAssistAgent._truncate_tool_result(result, max_size=100)
        assert len(truncated) < 500
        assert "500 chars total" in truncated

    def test_exact_max_size(self):
        """Result exactly at max_size is not truncated"""
        result = "x" * 20000
        assert AiAssistAgent._truncate_tool_result(result) == result


class TestObservationMasking:
    """Tests for _mask_old_observations"""

    def test_no_tool_results(self):
        """Messages without tool results are untouched"""
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        original = [m.copy() for m in messages]
        AiAssistAgent._mask_old_observations(messages)
        assert messages == original

    def test_recent_results_preserved(self):
        """Most recent tool results are kept intact"""
        messages = [
            {"role": "user", "content": "question"},
            {"role": "assistant", "content": [{"type": "tool_use", "id": "1", "name": "t1", "input": {}}]},
            {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "1", "content": "result1"}],
            },
            {"role": "assistant", "content": [{"type": "tool_use", "id": "2", "name": "t2", "input": {}}]},
            {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "2", "content": "result2"}],
            },
        ]
        AiAssistAgent._mask_old_observations(messages, keep_recent=2)
        # Both should be preserved (only 2 tool result rounds, keep_recent=2)
        assert messages[2]["content"][0]["content"] == "result1"
        assert messages[4]["content"][0]["content"] == "result2"

    def test_old_results_masked(self):
        """Old tool results beyond keep_recent are replaced with placeholder"""
        messages = [
            {"role": "user", "content": "question"},
            {"role": "assistant", "content": [{"type": "tool_use", "id": "1", "name": "t1", "input": {}}]},
            {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "1", "content": "old result data"}],
            },
            {"role": "assistant", "content": [{"type": "tool_use", "id": "2", "name": "t2", "input": {}}]},
            {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "2", "content": "mid result"}],
            },
            {"role": "assistant", "content": [{"type": "tool_use", "id": "3", "name": "t3", "input": {}}]},
            {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "3", "content": "recent result"}],
            },
        ]
        AiAssistAgent._mask_old_observations(messages, keep_recent=2)

        # First tool result should be masked
        assert "Previous tool result" in messages[2]["content"][0]["content"]
        # Last two should be preserved
        assert messages[4]["content"][0]["content"] == "mid result"
        assert messages[6]["content"][0]["content"] == "recent result"

    def test_tool_use_id_preserved(self):
        """Tool use IDs are preserved during masking"""
        messages = [
            {"role": "user", "content": "q"},
            {"role": "assistant", "content": [{"type": "tool_use", "id": "abc", "name": "t", "input": {}}]},
            {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "abc", "content": "big result"}],
            },
            {"role": "assistant", "content": [{"type": "tool_use", "id": "def", "name": "t", "input": {}}]},
            {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "def", "content": "newer"}],
            },
            {"role": "assistant", "content": [{"type": "tool_use", "id": "ghi", "name": "t", "input": {}}]},
            {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "ghi", "content": "newest"}],
            },
        ]
        AiAssistAgent._mask_old_observations(messages, keep_recent=2)
        assert messages[2]["content"][0]["tool_use_id"] == "abc"

    def test_multiple_tool_results_in_one_message(self):
        """Multiple tool results in a single message are all masked when old"""
        messages = [
            {"role": "user", "content": "q"},
            {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "1", "name": "t1", "input": {}},
                    {"type": "tool_use", "id": "2", "name": "t2", "input": {}},
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "1", "content": "r1"},
                    {"type": "tool_result", "tool_use_id": "2", "content": "r2"},
                ],
            },
            {"role": "assistant", "content": [{"type": "tool_use", "id": "3", "name": "t3", "input": {}}]},
            {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "3", "content": "recent"}],
            },
            {"role": "assistant", "content": [{"type": "tool_use", "id": "4", "name": "t4", "input": {}}]},
            {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "4", "content": "latest"}],
            },
        ]
        AiAssistAgent._mask_old_observations(messages, keep_recent=2)
        # Both results in the first tool results message should be masked
        assert "Previous tool result" in messages[2]["content"][0]["content"]
        assert "Previous tool result" in messages[2]["content"][1]["content"]

    def test_empty_messages(self):
        """Empty messages list is handled gracefully"""
        messages = []
        AiAssistAgent._mask_old_observations(messages)
        assert messages == []


class TestConversationCompaction:
    """Tests for ConversationMemory.compact()"""

    def test_needs_compaction_false_initially(self):
        """Fresh memory does not need compaction"""
        mem = ConversationMemory(max_exchanges=10, compaction_threshold=8)
        assert mem.needs_compaction() is False

    def test_needs_compaction_at_threshold(self):
        """Compaction is needed when threshold is reached"""
        mem = ConversationMemory(max_exchanges=10, compaction_threshold=3)
        mem.add_exchange("q1", "a1")
        mem.add_exchange("q2", "a2")
        mem.add_exchange("q3", "a3")
        assert mem.needs_compaction() is True

    def test_compact_below_keep_recent(self):
        """Compaction is skipped when exchanges <= keep_recent"""
        mem = ConversationMemory(max_exchanges=10)
        mem.add_exchange("q1", "a1")
        mem.add_exchange("q2", "a2")
        mock_client = MagicMock()
        assert mem.compact(mock_client, "test-model", keep_recent=4) is False
        mock_client.messages.create.assert_not_called()

    def test_compact_success(self):
        """Successful compaction replaces old exchanges with summary"""
        mem = ConversationMemory(max_exchanges=10)
        for i in range(8):
            mem.add_exchange(f"question {i}", f"answer {i}")

        # Mock the Claude API response
        mock_response = MagicMock()
        mock_block = MagicMock()
        mock_block.text = "Summary: 8 exchanges about various questions."
        mock_response.content = [mock_block]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        result = mem.compact(mock_client, "test-model", keep_recent=4)

        assert result is True
        # 1 summary + 4 recent = 5 exchanges
        assert len(mem.exchanges) == 5
        assert mem.exchanges[0]["user"] == "[Conversation summary]"
        assert "Summary" in mem.exchanges[0]["assistant"]
        # Recent exchanges preserved
        assert mem.exchanges[1]["user"] == "question 4"
        assert mem.exchanges[4]["user"] == "question 7"

    def test_compact_api_failure(self):
        """Compaction handles API failure gracefully"""
        mem = ConversationMemory(max_exchanges=10)
        for i in range(8):
            mem.add_exchange(f"q{i}", f"a{i}")

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("API error")

        result = mem.compact(mock_client, "test-model", keep_recent=4)

        assert result is False
        # Exchanges unchanged
        assert len(mem.exchanges) == 8

    def test_compact_empty_summary(self):
        """Compaction handles empty summary response gracefully"""
        mem = ConversationMemory(max_exchanges=10)
        for i in range(8):
            mem.add_exchange(f"q{i}", f"a{i}")

        mock_response = MagicMock()
        mock_block = MagicMock()
        mock_block.text = "   "  # Whitespace-only
        mock_response.content = [mock_block]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        result = mem.compact(mock_client, "test-model", keep_recent=4)

        assert result is False
        assert len(mem.exchanges) == 8

    def test_compaction_threshold_default(self):
        """Default compaction threshold is 8"""
        mem = ConversationMemory()
        assert mem.compaction_threshold == 8

    def test_compaction_threshold_custom(self):
        """Custom compaction threshold is respected"""
        mem = ConversationMemory(compaction_threshold=5)
        assert mem.compaction_threshold == 5


class TestExtendedContext:
    """Tests for adaptive 1M extended context window"""

    def test_config_default_disabled(self):
        """Extended context is disabled by default"""
        config = AiAssistConfig(anthropic_api_key="test-key", mcp_servers={})
        assert config.allow_extended_context is False

    def test_config_enabled(self):
        """Extended context can be enabled via config"""
        config = AiAssistConfig(anthropic_api_key="test-key", mcp_servers={}, allow_extended_context=True)
        assert config.allow_extended_context is True

    def test_supports_extended_context_disabled(self):
        """Returns False when config disables extended context"""
        config = AiAssistConfig(anthropic_api_key="test-key", mcp_servers={}, allow_extended_context=False)
        agent = AiAssistAgent(config)
        assert agent._supports_extended_context() is False

    def test_supports_extended_context_enabled_supported_model(self):
        """Returns True for supported model with config enabled"""
        config = AiAssistConfig(anthropic_api_key="test-key", mcp_servers={}, allow_extended_context=True)
        agent = AiAssistAgent(config)
        # Default model is claude-sonnet-4-5 which is supported
        assert agent._supports_extended_context() is True

    def test_supports_extended_context_unsupported_model(self):
        """Returns False for unsupported model even with config enabled"""
        config = AiAssistConfig(
            anthropic_api_key="test-key", mcp_servers={}, allow_extended_context=True, model="claude-3-haiku-20240307"
        )
        agent = AiAssistAgent(config)
        assert agent._supports_extended_context() is False

    def test_needs_extended_context_no_usage(self):
        """Returns False when no token usage data exists"""
        config = AiAssistConfig(anthropic_api_key="test-key", mcp_servers={}, allow_extended_context=True)
        agent = AiAssistAgent(config)
        assert agent._needs_extended_context() is False

    def test_needs_extended_context_below_threshold(self):
        """Returns False when token usage is below activation threshold"""
        config = AiAssistConfig(anthropic_api_key="test-key", mcp_servers={}, allow_extended_context=True)
        agent = AiAssistAgent(config)
        agent._turn_token_usage = [{"turn": 0, "input_tokens": 100000, "output_tokens": 1000}]
        assert agent._needs_extended_context() is False

    def test_needs_extended_context_above_threshold(self):
        """Returns True when token usage exceeds activation threshold"""
        config = AiAssistConfig(anthropic_api_key="test-key", mcp_servers={}, allow_extended_context=True)
        agent = AiAssistAgent(config)
        agent._turn_token_usage = [{"turn": 0, "input_tokens": 160000, "output_tokens": 1000}]
        assert agent._needs_extended_context() is True

    def test_get_extra_headers_inactive(self):
        """Returns None when extended context is not active"""
        config = AiAssistConfig(anthropic_api_key="test-key", mcp_servers={})
        agent = AiAssistAgent(config)
        assert agent._get_extra_headers() is None

    def test_get_extra_headers_active(self):
        """Returns beta header when extended context is active"""
        config = AiAssistConfig(anthropic_api_key="test-key", mcp_servers={}, allow_extended_context=True)
        agent = AiAssistAgent(config)
        agent._extended_context_active = True
        headers = agent._get_extra_headers()
        assert headers is not None
        assert "anthropic-beta" in headers
        assert headers["anthropic-beta"] == "context-1m-2025-08-07"

    def test_context_window_size_default(self):
        """Context window is 200K when extended context is not active"""
        config = AiAssistConfig(anthropic_api_key="test-key", mcp_servers={})
        agent = AiAssistAgent(config)
        assert agent.get_context_window_size() == 200000

    def test_context_window_size_extended(self):
        """Context window is 1M when extended context is active"""
        config = AiAssistConfig(anthropic_api_key="test-key", mcp_servers={}, allow_extended_context=True)
        agent = AiAssistAgent(config)
        agent._extended_context_active = True
        assert agent.get_context_window_size() == 1000000

    def test_extended_context_not_active_initially(self):
        """Extended context starts inactive"""
        config = AiAssistConfig(anthropic_api_key="test-key", mcp_servers={}, allow_extended_context=True)
        agent = AiAssistAgent(config)
        assert agent._extended_context_active is False
