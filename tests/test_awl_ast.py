"""Tests for AWL AST node construction"""

from ai_assist.awl_ast import (
    IfNode,
    LoopNode,
    ReturnNode,
    SetNode,
    TaskNode,
    WorkflowNode,
)


def test_workflow_node():
    node = WorkflowNode(body=[])
    assert node.body == []


def test_task_node_minimal():
    node = TaskNode(task_id="find_server", goal="Find the HTTP server.")
    assert node.task_id == "find_server"
    assert node.goal == "Find the HTTP server."
    assert node.hints == []
    assert node.context is None
    assert node.constraints is None
    assert node.success is None
    assert node.expose == []


def test_task_node_full():
    node = TaskNode(
        task_id="analyze",
        hints=["no-history", "no-kg"],
        goal="Analyze handlers.",
        context="Focus on HTTP.",
        constraints="Only source code.",
        success="List all handlers.",
        expose=["handlers", "count"],
    )
    assert node.hints == ["no-history", "no-kg"]
    assert node.context == "Focus on HTTP."
    assert node.constraints == "Only source code."
    assert node.success == "List all handlers."
    assert node.expose == ["handlers", "count"]


def test_set_node():
    node = SetNode(variable="target", value="HTTP server")
    assert node.variable == "target"
    assert node.value == "HTTP server"


def test_if_node():
    node = IfNode(expression="handlers", then_body=[], else_body=[])
    assert node.expression == "handlers"
    assert node.then_body == []
    assert node.else_body == []


def test_loop_node():
    node = LoopNode(collection="handlers", item_var="handler", body=[])
    assert node.collection == "handlers"
    assert node.item_var == "handler"
    assert node.limit is None
    assert node.body == []


def test_loop_node_with_limit():
    node = LoopNode(collection="handlers", item_var="handler", limit=5, body=[])
    assert node.limit == 5


def test_loop_node_with_collect():
    node = LoopNode(collection="handlers", item_var="handler", collect="results", body=[])
    assert node.collect == "results"
    assert node.collect_fields == []


def test_loop_node_with_collect_fields():
    node = LoopNode(collection="handlers", item_var="handler", collect="results", collect_fields=["summary"], body=[])
    assert node.collect == "results"
    assert node.collect_fields == ["summary"]


def test_loop_node_collect_default_none():
    node = LoopNode(collection="handlers", item_var="handler", body=[])
    assert node.collect is None
    assert node.collect_fields == []


def test_return_node():
    node = ReturnNode(expression="handlers")
    assert node.expression == "handlers"


def test_workflow_with_nested_nodes():
    task = TaskNode(task_id="t1", goal="Do something.", expose=["result"])
    ret = ReturnNode(expression="result")
    workflow = WorkflowNode(body=[task, ret])
    assert len(workflow.body) == 2
    assert isinstance(workflow.body[0], TaskNode)
    assert isinstance(workflow.body[1], ReturnNode)
