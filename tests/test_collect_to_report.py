"""Tests for __collect_to_report auto-paginated data collection."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from ai_assist.agent import AiAssistAgent, _extract_data_items, _resolve_dotpath
from ai_assist.config import AiAssistConfig, MCPServerConfig, PaginationConfig
from ai_assist.report_tools import ReportTools

# --- _parse_collect_param tests ---


def test_parse_collect_param_name_and_format():
    assert AiAssistAgent._parse_collect_param("my-data:jsonl") == ("my-data", "jsonl", None)


def test_parse_collect_param_with_limit():
    assert AiAssistAgent._parse_collect_param("my-data:jsonl:50") == ("my-data", "jsonl", 50)


def test_parse_collect_param_name_only():
    assert AiAssistAgent._parse_collect_param("my-data") == ("my-data", "jsonl", None)


def test_parse_collect_param_invalid_format():
    with pytest.raises(ValueError, match="Unsupported format"):
        AiAssistAgent._parse_collect_param("data:xml")


def test_parse_collect_param_empty_name():
    with pytest.raises(ValueError, match="cannot be empty"):
        AiAssistAgent._parse_collect_param(":jsonl")


# --- _resolve_dotpath tests ---


def test_resolve_dotpath_simple():
    assert _resolve_dotpath({"count": 42}, "count") == 42


def test_resolve_dotpath_nested():
    assert _resolve_dotpath({"_meta": {"count": 150}}, "_meta.count") == 150


def test_resolve_dotpath_elasticsearch_total():
    data = {"total": {"value": 100, "relation": "gte"}}
    assert _resolve_dotpath(data, "total") == 100


def test_resolve_dotpath_missing():
    assert _resolve_dotpath({"a": 1}, "b.c") is None


# --- _extract_data_items tests ---


def test_extract_data_items_auto():
    data = {"_meta": {"count": 3}, "components": [1, 2, 3]}
    assert _extract_data_items(data, "auto") == [1, 2, 3]


def test_extract_data_items_explicit():
    data = {"hits": [{"id": 1}], "total": 1}
    assert _extract_data_items(data, "hits") == [{"id": 1}]


def test_extract_data_items_raw_list():
    assert _extract_data_items([1, 2, 3], "auto") == [1, 2, 3]


def test_extract_data_items_auto_skips_underscore():
    data = {"_meta": [1, 2], "items": [3, 4]}
    assert _extract_data_items(data, "auto") == [3, 4]


# --- Fixtures ---


def _make_mcp_result(text: str):
    mock = MagicMock()
    mock.content = [MagicMock(text=text)]
    return mock


@pytest.fixture
def pagination_config():
    return PaginationConfig(
        offset_param="offset",
        limit_param="limit",
        default_page_size=2,
        total_field="_meta.count",
        data_field="auto",
    )


@pytest.fixture
def agent_with_pagination(tmp_path, pagination_config):
    config = AiAssistConfig(
        anthropic_api_key="test-key",
        working_dirs=["/tmp"],
        mcp_servers={
            "test": MCPServerConfig(command="echo", pagination=pagination_config),
        },
    )
    agent = AiAssistAgent(config=config)
    agent.report_tools = ReportTools(reports_dir=tmp_path / "reports")

    mock_session = AsyncMock()
    agent.sessions = {"test": mock_session}
    return agent


# --- Integration tests ---


@pytest.mark.asyncio
async def test_collect_single_page(agent_with_pagination, tmp_path):
    """Single page: total <= page_size."""
    session = agent_with_pagination.sessions["test"]
    session.call_tool.return_value = _make_mcp_result(
        json.dumps({"items": [{"id": 1}, {"id": 2}], "_meta": {"count": 2}})
    )

    result = await agent_with_pagination._execute_tool(
        "test__some_tool",
        {"query": "test", "__collect_to_report": "single:jsonl"},
    )

    assert "2 items" in result
    assert "1 page" in result
    report = (tmp_path / "reports" / "single.jsonl").read_text()
    lines = [json.loads(line) for line in report.strip().splitlines()]
    assert len(lines) == 2
    assert lines[0]["id"] == 1


@pytest.mark.asyncio
async def test_collect_multi_page(agent_with_pagination, tmp_path):
    """Multiple pages: total > page_size."""
    session = agent_with_pagination.sessions["test"]

    page1 = json.dumps({"items": [{"id": 1}, {"id": 2}], "_meta": {"count": 3}})
    page2 = json.dumps({"items": [{"id": 3}], "_meta": {"count": 3}})
    session.call_tool.side_effect = [_make_mcp_result(page1), _make_mcp_result(page2)]

    result = await agent_with_pagination._execute_tool(
        "test__some_tool",
        {"query": "test", "__collect_to_report": "multi:jsonl"},
    )

    assert "3 items" in result
    assert "2 pages" in result
    report = (tmp_path / "reports" / "multi.jsonl").read_text()
    lines = [json.loads(line) for line in report.strip().splitlines()]
    assert len(lines) == 3


@pytest.mark.asyncio
async def test_collect_with_max_items(agent_with_pagination, tmp_path):
    """Max items limits collection."""
    session = agent_with_pagination.sessions["test"]

    page1 = json.dumps({"items": [{"id": 1}, {"id": 2}], "_meta": {"count": 100}})
    session.call_tool.return_value = _make_mcp_result(page1)

    result = await agent_with_pagination._execute_tool(
        "test__some_tool",
        {"query": "test", "__collect_to_report": "limited:jsonl:2"},
    )

    assert "2 items" in result
    report = (tmp_path / "reports" / "limited.jsonl").read_text()
    lines = [json.loads(line) for line in report.strip().splitlines()]
    assert len(lines) == 2
    # Should only call once since first page already has enough
    assert session.call_tool.call_count == 1


@pytest.mark.asyncio
async def test_collect_no_pagination_config(tmp_path):
    """Without pagination config, falls back to single write."""
    config = AiAssistConfig(
        anthropic_api_key="test-key",
        working_dirs=["/tmp"],
        mcp_servers={"test": MCPServerConfig(command="echo")},
    )
    agent = AiAssistAgent(config=config)
    agent.report_tools = ReportTools(reports_dir=tmp_path / "reports")

    session = AsyncMock()
    session.call_tool.return_value = _make_mcp_result('{"data": [1, 2, 3]}')
    agent.sessions = {"test": session}

    result = await agent._execute_tool(
        "test__some_tool",
        {"query": "test", "__collect_to_report": "fallback:jsonl"},
    )

    assert "no pagination config" in result.lower() or "1 page" in result.lower()
    report_file = tmp_path / "reports" / "fallback.jsonl"
    assert report_file.exists()


@pytest.mark.asyncio
async def test_collect_tool_overrides(tmp_path):
    """Tool overrides change pagination field names."""
    pagination = PaginationConfig(
        offset_param="offset",
        limit_param="limit",
        default_page_size=2,
        total_field="_meta.count",
        data_field="auto",
        tool_overrides={
            "search_jobs": {
                "total_field": "total",
                "data_field": "hits",
                "limit_param": "max_results",
            }
        },
    )
    config = AiAssistConfig(
        anthropic_api_key="test-key",
        working_dirs=["/tmp"],
        mcp_servers={"test": MCPServerConfig(command="echo", pagination=pagination)},
    )
    agent = AiAssistAgent(config=config)
    agent.report_tools = ReportTools(reports_dir=tmp_path / "reports")

    session = AsyncMock()
    session.call_tool.return_value = _make_mcp_result(json.dumps({"hits": [{"id": "a"}, {"id": "b"}], "total": 2}))
    agent.sessions = {"test": session}

    result = await agent._execute_tool(
        "test__search_jobs",
        {"query": "test", "__collect_to_report": "overridden:jsonl"},
    )

    assert "2 items" in result
    # Verify the overridden limit_param was used
    call_args = session.call_tool.call_args
    assert "max_results" in call_args[0][1]
