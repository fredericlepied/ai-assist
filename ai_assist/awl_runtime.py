"""AWL runtime engine - executes AWL ASTs via agent reasoning"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from .awl_ast import (
    ASTNode,
    FailNode,
    GoalNode,
    IfNode,
    LoopNode,
    ReturnNode,
    SetNode,
    TaskNode,
    WorkflowNode,
)
from .awl_expressions import AWLExpressionEvaluator

logger = logging.getLogger(__name__)


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
    def __init__(self, agent: Any, limits: RuntimeLimits | None = None, verbose: bool = False):
        self._agent = agent
        self._limits = limits or RuntimeLimits()
        self._variables: dict[str, Any] = {}
        self._expr = AWLExpressionEvaluator()
        self._steps = 0
        self._task_outcomes: list[TaskOutcome] = []
        self._verbose = verbose

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
        elif isinstance(node, GoalNode):
            await self._execute_goal(node)
        elif isinstance(node, FailNode):
            raise AWLRuntimeError(node.message)

    async def _execute_task(self, task: TaskNode):
        prompt = self._build_task_prompt(task)

        if "no-kg" in task.hints:
            prompt = "@no-kg " + prompt

        logger.info("AWL task '%s' starting", task.task_id)
        print(f"  > task '{task.task_id}' ...", flush=True)
        try:
            callback = self._progress_callback if self._verbose else None
            # During AWL tasks, use renderer for inner execution (no noisy text)
            prev_inner = getattr(self._agent, "on_inner_execution", None)
            renderer = getattr(self._agent, "renderer", None)
            if self._verbose and renderer:
                self._agent.on_inner_execution = renderer.on_inner_execution
            else:
                self._agent.on_inner_execution = None
            try:
                response = await self._agent.query(
                    prompt, max_turns=self._limits.max_tool_calls, progress_callback=callback
                )
            finally:
                self._agent.on_inner_execution = prev_inner
            exposed = self._extract_exposed(response, task.expose)
            self._variables.update(exposed)
            outcome = TaskOutcome(status="success", summary=response[:200], exposed=exposed)
            self._task_outcomes.append(outcome)

            # Log exposed variables
            if task.expose:
                missing_vars = [v for v in task.expose if v not in exposed]
                if missing_vars:
                    logger.warning(
                        "AWL task '%s': expected exposed vars %s but got %s (missing: %s)",
                        task.task_id,
                        task.expose,
                        list(exposed.keys()),
                        missing_vars,
                    )
                    print(f"    [!] missing exposed vars: {missing_vars}")

            if exposed:
                for key, val in exposed.items():
                    val_str = str(val)
                    if len(val_str) > 200:
                        val_str = val_str[:200] + "..."
                    print(f"    [+] {key} = {val_str}")
                logger.info("AWL task '%s' succeeded, exposed: %s", task.task_id, list(exposed.keys()))
            else:
                print("    [+] success")
                logger.info("AWL task '%s' succeeded (no exposed vars)", task.task_id)
        except Exception as e:
            outcome = TaskOutcome(status="failed", summary=str(e))
            self._task_outcomes.append(outcome)
            logger.error("AWL task '%s' failed: %s", task.task_id, e)
            print(f"    [-] failed: {e}")

    def _execute_set(self, node: SetNode):
        self._variables[node.variable] = self._expr.interpolate(node.value, self._variables)

    async def _execute_if(self, node: IfNode):
        value = self._expr.evaluate(node.expression, self._variables)
        truthy = self._expr.is_truthy(value)
        logger.info("AWL @if '%s' evaluated to %s (raw: %s)", node.expression, truthy, value)
        if truthy:
            await self._execute_body(node.then_body)
        else:
            await self._execute_body(node.else_body)

    async def _execute_loop(self, node: LoopNode):
        collection = self._variables.get(node.collection, [])
        collection = self._coerce_to_list(collection, node.collection)
        if not isinstance(collection, list | tuple):
            raise AWLRuntimeError(
                f"@loop '{node.collection}' is not a list (got {type(collection).__name__}). "
                f"Ensure the task exposes it as a JSON array."
            )

        items = collection
        if node.limit is not None:
            items = items[: node.limit]

        logger.info(
            "AWL @loop '%s': %d items%s",
            node.collection,
            len(items),
            f" (collect={node.collect})" if node.collect else "",
        )

        collected: list[dict[str, Any]] = []

        for i, item in enumerate(items, 1):
            item_full = str(item)
            item_short = item_full[:100] + "..." if len(item_full) > 100 else item_full
            print(f"  loop {node.collection} [{i}/{len(items)}]: {node.item_var} = {item_short}")
            logger.info("AWL @loop iteration %d/%d: %s = %s", i, len(items), node.item_var, item_full)
            self._variables[node.item_var] = item
            outcomes_before = len(self._task_outcomes)
            await self._execute_body(node.body)

            if node.collect is not None:
                new_outcomes = self._task_outcomes[outcomes_before:]
                all_succeeded = all(o.status == "success" for o in new_outcomes)
                if not new_outcomes:
                    logger.warning("AWL @loop collect: iteration %d produced no outcomes", i)
                elif not all_succeeded:
                    failed = [o for o in new_outcomes if o.status != "success"]
                    logger.warning("AWL @loop collect: iteration %d had %d failed task(s), skipping", i, len(failed))
                    print(f"    [!] iteration {i} failed, skipping collect")
                else:
                    iteration_exposed: dict[str, Any] = {}
                    for outcome in new_outcomes:
                        iteration_exposed.update(outcome.exposed)
                    if not iteration_exposed:
                        # Task succeeded but no vars extracted -- still include with item context
                        logger.warning(
                            "AWL @loop collect: iteration %d succeeded but no exposed vars extracted, "
                            "including with _item only",
                            i,
                        )
                        print(f"    [!] iteration {i}: no exposed vars, including with _item")
                        iteration_exposed = {"_item": item}
                    if node.collect_fields:
                        iteration_exposed = {k: v for k, v in iteration_exposed.items() if k in node.collect_fields}
                    collected.append(iteration_exposed)

        if node.collect is not None:
            self._variables[node.collect] = collected
            logger.info("AWL @loop collected %d/%d items into '%s'", len(collected), len(items), node.collect)
            if len(collected) < len(items):
                print(f"  [!] collect: {len(collected)}/{len(items)} iterations produced results")
                logger.warning(
                    "AWL @loop '%s' collect: only %d/%d iterations produced results",
                    node.collection,
                    len(collected),
                    len(items),
                )

    def _progress_callback(self, status: str, turn: int, max_turns: int, tool_name: str | None):
        """Print agent progress during task execution (verbose mode)."""
        if status == "executing_tool":
            print(f"    [{turn}/{max_turns}] calling {tool_name}", flush=True)
        elif status == "calling_claude":
            print(f"    [{turn}/{max_turns}] thinking...", flush=True)

    def _coerce_to_list(self, value: Any, var_name: str) -> Any:
        """Try to coerce a value to a list for @loop iteration.

        Handles: JSON strings, Python-repr strings, single dicts.
        """
        import ast

        # Already a list
        if isinstance(value, list | tuple):
            return value

        # Single dict → wrap in list
        if isinstance(value, dict):
            result = [value]
            self._variables[var_name] = result
            return result

        # String → try parsing as JSON, then Python literal
        if isinstance(value, str):
            # Try JSON first (double quotes)
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    self._variables[var_name] = parsed
                    return parsed
                if isinstance(parsed, dict):
                    result = [parsed]
                    self._variables[var_name] = result
                    return result
            except (json.JSONDecodeError, ValueError):
                pass

            # Try Python literal (single quotes)
            try:
                parsed = ast.literal_eval(value)
                if isinstance(parsed, list):
                    self._variables[var_name] = parsed
                    return parsed
                if isinstance(parsed, dict):
                    result = [parsed]
                    self._variables[var_name] = result
                    return result
            except (ValueError, SyntaxError):
                pass

        return value

    def _execute_return(self, node: ReturnNode):
        value = self._expr.evaluate(node.expression, self._variables)
        raise _ReturnSignal(value)

    async def _execute_goal(self, goal: GoalNode):
        """Execute one cycle of a goal block."""
        saved_limit = self._limits.max_tool_calls
        self._limits.max_tool_calls = min(goal.max_actions, saved_limit)

        try:
            await self._execute_body(goal.body)
        finally:
            self._limits.max_tool_calls = saved_limit

        # Evaluate success criteria
        await self._evaluate_goal_success(goal)

    async def _evaluate_goal_success(self, goal: GoalNode):
        """Ask the agent whether the goal's success criterion is met."""
        var_summary = "\n".join(f"  {k} = {v}" for k, v in self._variables.items() if not k.startswith("_goal_"))
        prompt = (
            f"You are evaluating whether a goal's success criterion has been met.\n\n"
            f"Goal: {goal.goal_id}\n"
            f"Success criterion: {goal.success_criteria}\n\n"
            f"Current state after this cycle:\n{var_summary}\n\n"
            f"Has the success criterion been met? Respond with JSON:\n"
            f'{{"success_met": true/false, "reason": "brief explanation"}}'
        )
        response = await self._agent.query(prompt, max_turns=1)
        result = self._extract_exposed(response, ["success_met", "reason"])

        self._variables["_goal_success_met"] = result.get("success_met", False)
        self._variables["_goal_success_reason"] = result.get("reason", "")

    def _build_task_prompt(self, task: TaskNode) -> str:
        interp = self._expr.interpolate
        v = self._variables

        parts = [f"You are executing task '{task.task_id}'."]

        goal_text = interp(task.goal, v)
        parts.append(f"\nGoal: {goal_text}")

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

        # If the goal references an MCP prompt (e.g. /server/prompt), remind the agent
        # to use introspection__execute_mcp_prompt to run it.
        combined = goal_text + (" " + interp(task.context, v) if task.context else "")
        if re.search(r"/[A-Za-z0-9_-]+/[A-Za-z0-9_-]+", combined):
            parts.append(
                "\nNote: To run an MCP prompt referenced as /server/prompt_name, "
                "call the introspection__execute_mcp_prompt tool with the server and prompt name."
            )

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
