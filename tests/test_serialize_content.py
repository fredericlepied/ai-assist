"""Tests for _serialize_content helper that strips extra SDK fields."""

from anthropic.types import TextBlock, ToolUseBlock

from ai_assist.agent import _serialize_content


class TestSerializeContent:
    def test_strips_extra_fields_from_tool_use(self):
        block = ToolUseBlock(id="t1", input={"x": 1}, name="my_tool", type="tool_use")
        block.__pydantic_extra__["caller"] = {"type": "direct"}
        result = _serialize_content([block])
        assert len(result) == 1
        assert "caller" not in result[0]
        assert result[0] == {"type": "tool_use", "id": "t1", "name": "my_tool", "input": {"x": 1}}

    def test_strips_extra_fields_from_text(self):
        block = TextBlock(text="hello", type="text")
        block.__pydantic_extra__["unknown_field"] = "value"
        result = _serialize_content([block])
        assert len(result) == 1
        assert "unknown_field" not in result[0]
        assert result[0] == {"type": "text", "text": "hello"}

    def test_preserves_known_fields(self):
        blocks = [
            TextBlock(text="thinking...", type="text"),
            ToolUseBlock(id="t1", input={"q": "test"}, name="search", type="tool_use"),
        ]
        result = _serialize_content(blocks)
        assert result[0]["text"] == "thinking..."
        assert result[1]["name"] == "search"
        assert result[1]["input"] == {"q": "test"}

    def test_handles_plain_dicts(self):
        result = _serialize_content([{"type": "text", "text": "hi"}])
        assert result == [{"type": "text", "text": "hi"}]

    def test_handles_empty_list(self):
        assert _serialize_content([]) == []
