"""Tests for the think tool (agent planning/reasoning scratchpad)."""

import pytest

from ai_assist.think_tool import ThinkTool


class TestThinkToolDefinitions:
    """Test tool definition structure."""

    def test_get_tool_definitions_returns_one_tool(self):
        tool = ThinkTool()
        defs = tool.get_tool_definitions()
        assert len(defs) == 1

    def test_tool_name(self):
        tool = ThinkTool()
        defs = tool.get_tool_definitions()
        assert defs[0]["name"] == "internal__think"

    def test_tool_has_description(self):
        tool = ThinkTool()
        defs = tool.get_tool_definitions()
        assert "plan" in defs[0]["description"].lower() or "think" in defs[0]["description"].lower()

    def test_tool_has_input_schema(self):
        tool = ThinkTool()
        defs = tool.get_tool_definitions()
        schema = defs[0]["input_schema"]
        assert schema["type"] == "object"
        assert "thought" in schema["properties"]
        assert "thought" in schema["required"]

    def test_tool_server_is_internal(self):
        tool = ThinkTool()
        defs = tool.get_tool_definitions()
        assert defs[0]["_server"] == "internal"
        assert defs[0]["_original_name"] == "think"


class TestThinkToolExecution:
    """Test tool execution."""

    @pytest.mark.asyncio
    async def test_execute_returns_acknowledgement(self):
        tool = ThinkTool()
        result = await tool.execute_tool("think", {"thought": "I need to first get the job list, then check each one."})
        assert "thought" in result.lower() or "recorded" in result.lower() or "ok" in result.lower()

    @pytest.mark.asyncio
    async def test_execute_with_empty_thought(self):
        tool = ThinkTool()
        result = await tool.execute_tool("think", {"thought": ""})
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self):
        tool = ThinkTool()
        result = await tool.execute_tool("unknown", {"thought": "test"})
        assert "error" in result.lower() or "unknown" in result.lower()

    @pytest.mark.asyncio
    async def test_result_is_minimal(self):
        """The think tool should return a minimal response to not waste tokens."""
        tool = ThinkTool()
        result = await tool.execute_tool("think", {"thought": "A very long plan " * 100})
        # Response should be short regardless of input length
        assert len(result) < 100
