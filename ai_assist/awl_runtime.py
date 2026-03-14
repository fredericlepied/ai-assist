"""AWL runtime engine - executes AWL ASTs via agent reasoning"""

import json
import re
from dataclasses import dataclass, field
from typing import Any

from .awl_ast import (
    ASTNode,
    FailNode,
    IfNode,
    LoopNode,
    ReturnNode,
    SetNode,
    TaskNode,
    WorkflowNode,
)
from .awl_expressions import AWLExpressionEvaluator


class AWLRuntimeError(Exception):
    pass


class _ReturnSignal(Exception):
    def __init__(self, value: Any):
        self.value = value


@dataclass
class TaskOutcome:
    status: str
    summary: str
    exposed: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowResult:
    success: bool
    return_value: Any = None
    variables: dict[str, Any] = field(default_factory=dict)
    task_outcomes: list[TaskOutcome] = field(default_factory=list)


@dataclass
class RuntimeLimits:
    max_steps: int = 50
    max_tool_calls: int = 100
    timeout: float = 300.0


class AWLRuntime:
    def __init__(self, agent: Any, limits: RuntimeLimits | None = None):
        self._agent = agent
        self._limits = limits or RuntimeLimits()
        self._variables: dict[str, Any] = {}
        self._expr = AWLExpressionEvaluator()
        self._steps = 0
        self._task_outcomes: list[TaskOutcome] = []

    async def execute(self, workflow: WorkflowNode, variables: dict[str, Any] | None = None) -> WorkflowResult:
        self._variables = dict(variables) if variables else {}
        self._steps = 0
        self._task_outcomes = []
        return_value = None

        try:
            await self._execute_body(workflow.body)
        except _ReturnSignal as ret:
            return_value = ret.value

        all_succeeded = all(o.status == "success" for o in self._task_outcomes)
        return WorkflowResult(
            success=all_succeeded,
            return_value=return_value,
            variables=dict(self._variables),
            task_outcomes=list(self._task_outcomes),
        )

    async def _execute_body(self, body: list[ASTNode]):
        for node in body:
            await self._execute_node(node)

    async def _execute_node(self, node: ASTNode):
        self._steps += 1
        if self._steps > self._limits.max_steps:
            raise AWLRuntimeError(f"Exceeded max_steps ({self._limits.max_steps})")

        if isinstance(node, TaskNode):
            await self._execute_task(node)
        elif isinstance(node, SetNode):
            self._execute_set(node)
        elif isinstance(node, IfNode):
            await self._execute_if(node)
        elif isinstance(node, LoopNode):
            await self._execute_loop(node)
        elif isinstance(node, ReturnNode):
            self._execute_return(node)
        elif isinstance(node, FailNode):
            raise AWLRuntimeError(node.message)

    async def _execute_task(self, task: TaskNode):
        prompt = self._build_task_prompt(task)

        if "no-kg" in task.hints:
            prompt = "@no-kg " + prompt

        print(f"  > task '{task.task_id}' ...", flush=True)
        try:
            response = await self._agent.query(prompt, max_turns=self._limits.max_tool_calls)
            exposed = self._extract_exposed(response, task.expose)
            self._variables.update(exposed)
            outcome = TaskOutcome(status="success", summary=response[:200], exposed=exposed)
            self._task_outcomes.append(outcome)
            if exposed:
                for key, val in exposed.items():
                    val_str = str(val)
                    if len(val_str) > 200:
                        val_str = val_str[:200] + "..."
                    print(f"    [+] {key} = {val_str}")
            else:
                print("    [+] success")
        except Exception as e:
            outcome = TaskOutcome(status="failed", summary=str(e))
            self._task_outcomes.append(outcome)
            print(f"    [-] failed: {e}")

    def _execute_set(self, node: SetNode):
        self._variables[node.variable] = self._expr.interpolate(node.value, self._variables)

    async def _execute_if(self, node: IfNode):
        value = self._expr.evaluate(node.expression, self._variables)
        if self._expr.is_truthy(value):
            await self._execute_body(node.then_body)
        else:
            await self._execute_body(node.else_body)

    async def _execute_loop(self, node: LoopNode):
        collection = self._variables.get(node.collection, [])
        if not isinstance(collection, list | tuple):
            return

        items = collection
        if node.limit is not None:
            items = items[: node.limit]

        collected: list[dict[str, Any]] = []

        for i, item in enumerate(items, 1):
            print(f"  loop {node.collection} [{i}/{len(items)}]: {node.item_var} = {item}")
            self._variables[node.item_var] = item
            outcomes_before = len(self._task_outcomes)
            await self._execute_body(node.body)

            if node.collect is not None:
                new_outcomes = self._task_outcomes[outcomes_before:]
                all_succeeded = all(o.status == "success" for o in new_outcomes)
                if all_succeeded and new_outcomes:
                    iteration_exposed: dict[str, Any] = {}
                    for outcome in new_outcomes:
                        iteration_exposed.update(outcome.exposed)
                    if iteration_exposed:
                        if node.collect_fields:
                            iteration_exposed = {k: v for k, v in iteration_exposed.items() if k in node.collect_fields}
                        if iteration_exposed:
                            collected.append(iteration_exposed)

        if node.collect is not None:
            self._variables[node.collect] = collected

    def _execute_return(self, node: ReturnNode):
        value = self._expr.evaluate(node.expression, self._variables)
        raise _ReturnSignal(value)

    def _build_task_prompt(self, task: TaskNode) -> str:
        interp = self._expr.interpolate
        v = self._variables

        parts = [f"You are executing task '{task.task_id}'."]
        parts.append(f"\nGoal: {interp(task.goal, v)}")

        if task.context:
            parts.append(f"Context: {interp(task.context, v)}")
        if task.constraints:
            parts.append(f"Constraints: {interp(task.constraints, v)}")
        if task.success:
            parts.append(f"\nSuccess criteria: {interp(task.success, v)}")

        if task.expose:
            keys = ", ".join(task.expose)
            example = ", ".join(f'"{k}": "<value>"' for k in task.expose)
            parts.append(f"\nWhen complete, output results as JSON with these keys: {keys}")
            parts.append(f"Example: {{{example}}}")

        return "\n".join(parts)

    def _extract_exposed(self, response: str, expose_vars: list[str]) -> dict[str, Any]:
        if not expose_vars:
            return {}

        json_blocks = re.findall(r"```(?:json)?\s*\n?(.*?)\n?```", response, re.DOTALL)
        for block in json_blocks:
            try:
                data = json.loads(block.strip())
                if isinstance(data, dict):
                    return {k: data[k] for k in expose_vars if k in data}
            except json.JSONDecodeError:
                continue

        try:
            data = json.loads(response.strip())
            if isinstance(data, dict):
                return {k: data[k] for k in expose_vars if k in data}
        except json.JSONDecodeError:
            pass

        json_match = re.search(r"\{[^{}]*\}", response)
        if json_match:
            try:
                data = json.loads(json_match.group())
                if isinstance(data, dict):
                    return {k: data[k] for k in expose_vars if k in data}
            except json.JSONDecodeError:
                pass

        return {}
