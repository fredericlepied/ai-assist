"""Tests for AWL runtime engine"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from ai_assist.awl_ast import (
    FailNode,
    GoalNode,
    IfNode,
    LoopNode,
    ReturnNode,
    SetNode,
    TaskNode,
    WorkflowNode,
)
from ai_assist.awl_runtime import AWLRuntime, AWLRuntimeError, RuntimeLimits


@pytest.fixture
def mock_agent():
    agent = MagicMock()
    agent.query = AsyncMock()
    return agent


@pytest.fixture
def runtime(mock_agent):
    return AWLRuntime(mock_agent)


@pytest.mark.asyncio
async def test_execute_single_task(mock_agent, runtime):
    mock_agent.query.return_value = 'Found the server.\n```json\n{"server_file": "cmd/server/main.go"}\n```'
    workflow = WorkflowNode(
        body=[
            TaskNode(
                task_id="find_server",
                goal="Find the HTTP server.",
                success="Identify the file.",
                expose=["server_file"],
            ),
        ]
    )
    result = await runtime.execute(workflow)
    assert result.success is True
    assert result.variables["server_file"] == "cmd/server/main.go"
    assert len(result.task_outcomes) == 1
    assert result.task_outcomes[0].status == "success"


@pytest.mark.asyncio
async def test_execute_task_with_return(mock_agent, runtime):
    mock_agent.query.return_value = '```json\n{"server_file": "main.go"}\n```'
    workflow = WorkflowNode(
        body=[
            TaskNode(task_id="t1", goal="Find server.", expose=["server_file"]),
            ReturnNode(expression="server_file"),
        ]
    )
    result = await runtime.execute(workflow)
    assert result.return_value == "main.go"


@pytest.mark.asyncio
async def test_execute_set_and_interpolation(mock_agent, runtime):
    mock_agent.query.return_value = '```json\n{"target_file": "main.go"}\n```'
    workflow = WorkflowNode(
        body=[
            SetNode(variable="target", value="HTTP server"),
            TaskNode(task_id="find", goal="Find ${target}.", expose=["target_file"]),
        ]
    )
    result = await runtime.execute(workflow)
    assert result.variables["target"] == "HTTP server"
    assert "HTTP server" in mock_agent.query.call_args[1].get("prompt", mock_agent.query.call_args[0][0])


@pytest.mark.asyncio
async def test_execute_if_true_branch(mock_agent, runtime):
    mock_agent.query.return_value = '```json\n{"analysis": "done"}\n```'
    workflow = WorkflowNode(
        body=[
            IfNode(
                expression="handlers",
                then_body=[TaskNode(task_id="analyze", goal="Analyze.", expose=["analysis"])],
                else_body=[TaskNode(task_id="search", goal="Search.", expose=["found"])],
            ),
        ]
    )
    result = await runtime.execute(workflow, variables={"handlers": ["a", "b"]})
    assert result.variables.get("analysis") == "done"
    assert "found" not in result.variables


@pytest.mark.asyncio
async def test_execute_if_false_branch(mock_agent, runtime):
    mock_agent.query.return_value = '```json\n{"found": "yes"}\n```'
    workflow = WorkflowNode(
        body=[
            IfNode(
                expression="handlers",
                then_body=[TaskNode(task_id="analyze", goal="Analyze.", expose=["analysis"])],
                else_body=[TaskNode(task_id="search", goal="Search.", expose=["found"])],
            ),
        ]
    )
    result = await runtime.execute(workflow, variables={"handlers": []})
    assert result.variables.get("found") == "yes"
    assert "analysis" not in result.variables


@pytest.mark.asyncio
async def test_execute_loop(mock_agent, runtime):
    call_count = 0

    async def mock_query(prompt, **kwargs):
        nonlocal call_count
        call_count += 1
        return f'{{"handler_summary": "summary_{call_count}"}}'

    mock_agent.query = AsyncMock(side_effect=mock_query)
    workflow = WorkflowNode(
        body=[
            LoopNode(
                collection="handlers",
                item_var="handler",
                limit=None,
                body=[TaskNode(task_id="inspect", goal="Inspect ${handler}.", expose=["handler_summary"])],
            ),
        ]
    )
    await runtime.execute(workflow, variables={"handlers": ["h1", "h2", "h3"]})
    assert mock_agent.query.call_count == 3


@pytest.mark.asyncio
async def test_execute_loop_with_limit(mock_agent, runtime):
    mock_agent.query.return_value = '{"handler_summary": "done"}'
    workflow = WorkflowNode(
        body=[
            LoopNode(
                collection="handlers",
                item_var="handler",
                limit=2,
                body=[TaskNode(task_id="inspect", goal="Inspect ${handler}.", expose=["handler_summary"])],
            ),
        ]
    )
    await runtime.execute(workflow, variables={"handlers": ["h1", "h2", "h3", "h4", "h5"]})
    assert mock_agent.query.call_count == 2


@pytest.mark.asyncio
async def test_execute_loop_collect(mock_agent, runtime):
    call_count = 0

    async def mock_query(prompt, **kwargs):
        nonlocal call_count
        call_count += 1
        return f'{{"summary": "summary_{call_count}", "priority": "p{call_count}"}}'

    mock_agent.query = AsyncMock(side_effect=mock_query)
    workflow = WorkflowNode(
        body=[
            LoopNode(
                collection="items",
                item_var="item",
                collect="results",
                body=[TaskNode(task_id="analyze", goal="Analyze ${item}.", expose=["summary", "priority"])],
            ),
        ]
    )
    result = await runtime.execute(workflow, variables={"items": ["a", "b", "c"]})
    assert "results" in result.variables
    results = result.variables["results"]
    assert len(results) == 3
    assert results[0] == {"summary": "summary_1", "priority": "p1"}
    assert results[1] == {"summary": "summary_2", "priority": "p2"}
    assert results[2] == {"summary": "summary_3", "priority": "p3"}


@pytest.mark.asyncio
async def test_execute_loop_collect_with_limit(mock_agent, runtime):
    mock_agent.query.return_value = '{"summary": "done"}'
    workflow = WorkflowNode(
        body=[
            LoopNode(
                collection="items",
                item_var="item",
                limit=2,
                collect="results",
                body=[TaskNode(task_id="analyze", goal="Analyze ${item}.", expose=["summary"])],
            ),
        ]
    )
    result = await runtime.execute(workflow, variables={"items": ["a", "b", "c", "d"]})
    assert len(result.variables["results"]) == 2


@pytest.mark.asyncio
async def test_execute_loop_collect_fields(mock_agent, runtime):
    call_count = 0

    async def mock_query(prompt, **kwargs):
        nonlocal call_count
        call_count += 1
        return f'{{"summary": "summary_{call_count}", "priority": "p{call_count}", "extra": "ignore"}}'

    mock_agent.query = AsyncMock(side_effect=mock_query)
    workflow = WorkflowNode(
        body=[
            LoopNode(
                collection="items",
                item_var="item",
                collect="results",
                collect_fields=["summary"],
                body=[TaskNode(task_id="analyze", goal="Analyze ${item}.", expose=["summary", "priority", "extra"])],
            ),
        ]
    )
    result = await runtime.execute(workflow, variables={"items": ["a", "b"]})
    results = result.variables["results"]
    assert len(results) == 2
    assert results[0] == {"summary": "summary_1"}
    assert results[1] == {"summary": "summary_2"}


@pytest.mark.asyncio
async def test_execute_loop_collect_skips_failed_tasks(mock_agent, runtime):
    call_count = 0

    async def mock_query(prompt, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise Exception("API Error")
        return f'{{"summary": "ok_{call_count}"}}'

    mock_agent.query = AsyncMock(side_effect=mock_query)
    workflow = WorkflowNode(
        body=[
            LoopNode(
                collection="items",
                item_var="item",
                collect="results",
                body=[TaskNode(task_id="analyze", goal="Analyze ${item}.", expose=["summary"])],
            ),
        ]
    )
    result = await runtime.execute(workflow, variables={"items": ["a", "b", "c"]})
    results = result.variables["results"]
    assert len(results) == 2
    assert results[0] == {"summary": "ok_1"}
    assert results[1] == {"summary": "ok_3"}


@pytest.mark.asyncio
async def test_task_failure_marks_workflow_failed(mock_agent, runtime):
    mock_agent.query.side_effect = Exception("API Error")
    workflow = WorkflowNode(
        body=[TaskNode(task_id="failing", goal="This will fail.", expose=["result"])],
    )
    result = await runtime.execute(workflow)
    assert result.success is False
    assert result.task_outcomes[0].status == "failed"


@pytest.mark.asyncio
async def test_max_steps_exceeded(mock_agent):
    mock_agent.query.return_value = '{"r": "ok"}'
    runtime = AWLRuntime(mock_agent, limits=RuntimeLimits(max_steps=2))
    workflow = WorkflowNode(
        body=[
            TaskNode(task_id="t1", goal="Step 1.", expose=["r"]),
            TaskNode(task_id="t2", goal="Step 2.", expose=["r"]),
            TaskNode(task_id="t3", goal="Step 3.", expose=["r"]),
        ]
    )
    with pytest.raises(AWLRuntimeError, match="max_steps"):
        await runtime.execute(workflow)


@pytest.mark.asyncio
async def test_task_no_expose(mock_agent, runtime):
    mock_agent.query.return_value = "Task completed successfully."
    workflow = WorkflowNode(
        body=[TaskNode(task_id="simple", goal="Just do it.")],
    )
    result = await runtime.execute(workflow)
    assert result.success is True
    assert result.task_outcomes[0].status == "success"


@pytest.mark.asyncio
async def test_no_kg_hint(mock_agent, runtime):
    mock_agent.query.return_value = '{"result": "found"}'
    workflow = WorkflowNode(
        body=[TaskNode(task_id="t1", hints=["no-kg"], goal="Find something.", expose=["result"])],
    )
    await runtime.execute(workflow)
    prompt = mock_agent.query.call_args[0][0]
    assert prompt.startswith("@no-kg")


@pytest.mark.asyncio
async def test_if_with_none_comparison_no_crash(mock_agent, runtime):
    """@if count > 0 should not crash when count is undefined (None)."""
    mock_agent.query.return_value = '{"r": "ok"}'
    workflow = WorkflowNode(
        body=[
            IfNode(
                expression="count > 0",
                then_body=[TaskNode(task_id="t1", goal="Do.", expose=["r"])],
            ),
        ]
    )
    result = await runtime.execute(workflow)
    assert result.success is True
    assert mock_agent.query.call_count == 0


@pytest.mark.asyncio
async def test_fail_directive_raises(runtime):
    workflow = WorkflowNode(body=[FailNode(message="Jira is down")])
    with pytest.raises(AWLRuntimeError, match="Jira is down"):
        await runtime.execute(workflow)


@pytest.mark.asyncio
async def test_fail_inside_if_aborts(runtime):
    workflow = WorkflowNode(
        body=[
            IfNode(
                expression="not jira_report",
                then_body=[FailNode(message="Jira unavailable")],
                else_body=[],
            )
        ]
    )
    with pytest.raises(AWLRuntimeError, match="Jira unavailable"):
        await runtime.execute(workflow)


@pytest.mark.asyncio
async def test_fail_not_reached_when_condition_false(runtime):
    workflow = WorkflowNode(
        body=[
            SetNode(variable="jira_report", value="report.jsonl"),
            IfNode(
                expression="not jira_report",
                then_body=[FailNode(message="should not fail")],
                else_body=[],
            ),
            ReturnNode(expression="jira_report"),
        ]
    )
    result = await runtime.execute(workflow)
    assert result.success is True
    assert result.return_value == "report.jsonl"


@pytest.mark.asyncio
async def test_if_with_out_of_range_index_no_crash(mock_agent, runtime):
    """@if handlers[99] should not crash when index is out of range."""
    mock_agent.query.return_value = '{"r": "ok"}'
    workflow = WorkflowNode(
        body=[
            IfNode(
                expression="handlers[99]",
                then_body=[TaskNode(task_id="t1", goal="Do.", expose=["r"])],
            ),
        ]
    )
    result = await runtime.execute(workflow, variables={"handlers": ["a"]})
    assert result.success is True
    assert mock_agent.query.call_count == 0


@pytest.mark.asyncio
async def test_loop_with_json_string_variable(mock_agent, runtime):
    """Test that @loop parses JSON string variables into lists"""
    mock_agent.query = AsyncMock(return_value='{"summary": "done"}')
    workflow = WorkflowNode(
        body=[
            LoopNode(
                collection="jobs",
                item_var="job",
                body=[TaskNode(task_id="process", goal="Process ${job}.", expose=["summary"])],
            ),
        ]
    )
    # Pass jobs as a JSON string (as agent might expose it)
    result = await runtime.execute(workflow, variables={"jobs": '[{"id": "a"}, {"id": "b"}]'})
    assert result.success is True
    assert mock_agent.query.call_count == 2  # 2 items in the JSON array


@pytest.mark.asyncio
async def test_loop_with_single_dict_wraps_in_list(mock_agent, runtime):
    """Test that @loop wraps a single dict in a list"""
    mock_agent.query = AsyncMock(return_value='{"summary": "done"}')
    workflow = WorkflowNode(
        body=[
            LoopNode(
                collection="job",
                item_var="j",
                body=[TaskNode(task_id="process", goal="Process ${j}.", expose=["summary"])],
            ),
        ]
    )
    result = await runtime.execute(workflow, variables={"job": {"id": "abc", "name": "test"}})
    assert result.success is True
    assert mock_agent.query.call_count == 1  # Single dict wrapped in list = 1 iteration


@pytest.mark.asyncio
async def test_loop_with_python_repr_string(mock_agent, runtime):
    """Test that @loop parses Python-repr strings (single quotes)"""
    mock_agent.query = AsyncMock(return_value='{"summary": "done"}')
    workflow = WorkflowNode(
        body=[
            LoopNode(
                collection="jobs",
                item_var="job",
                body=[TaskNode(task_id="process", goal="Process ${job}.", expose=["summary"])],
            ),
        ]
    )
    result = await runtime.execute(workflow, variables={"jobs": "[{'id': 'a'}, {'id': 'b'}]"})
    assert result.success is True
    assert mock_agent.query.call_count == 2


# ── @goal directive runtime tests ────────────────────────────────


@pytest.mark.asyncio
async def test_execute_goal_runs_body(mock_agent, runtime):
    """Test that @goal executes its body tasks"""
    call_count = 0

    async def mock_query(prompt, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return '```json\n{"failure_rate": 5}\n```'
        # Success evaluation
        return '```json\n{"success_met": false, "reason": "still monitoring"}\n```'

    mock_agent.query = AsyncMock(side_effect=mock_query)
    workflow = WorkflowNode(
        body=[
            GoalNode(
                goal_id="test_goal",
                success_criteria="Failure rate below 10%",
                body=[
                    TaskNode(task_id="check", goal="Check rate.", expose=["failure_rate"]),
                ],
            ),
        ]
    )
    result = await runtime.execute(workflow)
    assert result.success is True
    assert result.variables["failure_rate"] == 5
    assert result.variables.get("_goal_success_met") is False


@pytest.mark.asyncio
async def test_execute_goal_success_met(mock_agent, runtime):
    """Test that success evaluation sets _goal_success_met"""
    call_count = 0

    async def mock_query(prompt, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return '```json\n{"failure_rate": 2}\n```'
        # Success evaluation
        return '```json\n{"success_met": true, "reason": "Rate is 2%, well below 10%"}\n```'

    mock_agent.query = AsyncMock(side_effect=mock_query)
    workflow = WorkflowNode(
        body=[
            GoalNode(
                goal_id="test_goal",
                success_criteria="Failure rate below 10%",
                body=[
                    TaskNode(task_id="check", goal="Check rate.", expose=["failure_rate"]),
                ],
            ),
        ]
    )
    result = await runtime.execute(workflow)
    assert result.variables["_goal_success_met"] is True
    assert "2%" in result.variables["_goal_success_reason"]


@pytest.mark.asyncio
async def test_execute_goal_max_actions_limit(mock_agent):
    """Test that max_actions limits tool calls within the goal body"""
    runtime = AWLRuntime(mock_agent, limits=RuntimeLimits(max_tool_calls=100))
    mock_agent.query = AsyncMock(return_value='```json\n{"r": "ok"}\n```')

    workflow = WorkflowNode(
        body=[
            GoalNode(
                goal_id="limited",
                success_criteria="Done",
                max_actions=2,
                body=[
                    TaskNode(task_id="t1", goal="Task 1.", expose=["r"]),
                ],
            ),
        ]
    )
    r = await runtime.execute(workflow)
    # Task should execute with max_turns=2 (from max_actions)
    assert r.success is True


@pytest.mark.asyncio
async def test_execute_goal_with_conditional_body(mock_agent, runtime):
    """Test @goal with @if inside body"""
    call_count = 0

    async def mock_query(prompt, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return '```json\n{"failure_rate": 15}\n```'
        elif call_count == 2:
            return "Alert created."
        # Success evaluation
        return '```json\n{"success_met": false, "reason": "rate still high"}\n```'

    mock_agent.query = AsyncMock(side_effect=mock_query)
    workflow = WorkflowNode(
        body=[
            GoalNode(
                goal_id="test_cond",
                success_criteria="Failure rate below 10%",
                body=[
                    TaskNode(task_id="check", goal="Check rate.", expose=["failure_rate"]),
                    IfNode(
                        expression="failure_rate > 10",
                        then_body=[TaskNode(task_id="alert", goal="Create alert.")],
                    ),
                ],
            ),
        ]
    )
    await runtime.execute(workflow, variables={"failure_rate": 0})
    # Both tasks should have executed (check + alert)
    assert mock_agent.query.call_count == 3  # check + alert + success eval
