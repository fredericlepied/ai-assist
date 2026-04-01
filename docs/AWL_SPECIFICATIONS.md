# Agent Workflow Language (AWL) Specification

## Overview

The **Agent Workflow Language (AWL)** is a lightweight scripting language used to orchestrate AI agent workflows.

AWL focuses on **intent-driven orchestration** rather than explicit tool invocation.

Instead of specifying which tools to call, AWL scripts define:

- goals
- workflow structure
- conditions
- loops
- variable propagation

The **agent remains responsible for selecting tools and strategies** to accomplish each task.

This design keeps AWL:

- human readable
- LLM-friendly
- flexible
- safe

---

# Design Principles

## Intent-driven workflows

Scripts describe **what must be achieved**, not **how to implement it**.

## Agent autonomy

The agent determines:

- which tools to use
- how to search or analyze
- when a task is complete

## Minimal syntax

The language remains simple so that both humans and LLMs can easily produce and edit scripts.

## Deterministic structure

Although the agent reasons dynamically, the workflow structure is deterministic and validated by the runtime.

---

# Script Structure

An AWL script begins with `@start` and ends with `@end`.

Example:

@start

@task find_server
Goal: Find where the HTTP server is initialized.
Success: Identify the file and function responsible for startup.
Expose: server_file, server_function
@end

@end

---

# Directives

AWL defines the following directives.

| Directive | Description |
|---|---|
| @start | start workflow |
| @end | end block |
| @task | define agent task |
| @set | assign variable |
| @if | conditional execution |
| @else | alternate branch |
| @loop | iterate collection |
| @return | return workflow result |
| @goal | autonomous goal pursuit |

---

# Task Hints

Tasks may include **execution hints** placed after the task name.

Hints influence the **context available to the agent**, but do not prescribe specific tools.

Example:

@task fresh_search @no-history @no-kg
Goal: Re-evaluate where the HTTP server is initialized.
Success: Identify the startup path using only repository evidence.
Expose: server_file, server_function
@end

---

# Supported Hints

## @no-history

The agent must ignore prior conversation history and previous reasoning context.

This ensures that the task is evaluated with a **fresh reasoning context**.

Example:

@task fresh_analysis @no-history
Goal: Analyze the repository structure without using previous conclusions.
@end

---

## @no-kg

The agent must not consult the external knowledge graph or knowledge base.

Only live data sources such as repository inspection or runtime tools may be used.

Example:

@task repository_only @no-kg
Goal: Determine how the system initializes using only source code evidence.
@end

---

# Tasks

Tasks represent **objectives for the agent**.

Syntax:

@task <task_id> [hints...]
...
@end

Example:

@task locate_config
Goal: Find where the server configuration is loaded.
Context: Focus on startup code and configuration parsing.
Success: Identify the entrypoint and parser.
Expose: config_entrypoint, config_parser
@end

---

# Task Fields

Inside a task block the following fields may appear.

| Field | Purpose |
|---|---|
| Goal | task objective |
| Context | additional context |
| Constraints | optional limitations |
| Success | completion criteria |
| Expose | variables produced |

---

# Variables

Variables can be defined using `@set`.

Example:

@set target = "HTTP server"

Variables can be referenced using interpolation:

${target}

Example:

Goal: Find where ${target} is initialized.

## Initial Variables

Variables can be injected before the script runs, without needing `@set`.

**From the CLI:**

```bash
ai-assist /run workflow.awl target="HTTP server" days=7
```

**From an agent prompt:** ask the agent to run a `.awl` file and it will call the
`introspection__execute_awl_script` tool with the variables you specify.

Injected variables are available from the first node, just like `@set` variables.

---

# Failure Handling

## @fail

Aborts the workflow immediately with an error message.

Syntax:

@fail <message>

Example — abort unconditionally:

@fail Jira server is in maintenance

Example — abort when a task did not produce the expected result:

@if not jira_report
  @fail Jira collection failed - aborting quarterly review
@end

The error is reported to the caller. Combine with `@if`/`@else` for conditional
abort vs. alternative path.

**Agent guidance**: When a task's upstream service is unavailable or returns an
error, do NOT expose the expected variables — leave them unset. The script can
then detect the failure with `@if not <variable>` and abort with `@fail`.

---

# Conditional Execution

Syntax:

@if <expression>
...
@else
...
@end

Example:

@if handlers

@task analyze_handlers
Goal: Understand the detected handlers.
Expose: handler_summaries
@end

@else

@task search_handlers
Goal: Search more broadly for request entry points.
Expose: handlers
@end

@end

---

# Expressions

Expressions are intentionally simple.

Supported operations:

| Expression | Example |
|---|---|
| variable | handlers |
| negation | not report_exists |
| property | config.entrypoint |
| index | handlers[0] |
| length | len(handlers) |
| comparison | len(handlers) > 0 |

---

# Loops

Loops iterate over collections.

Syntax:

@loop <collection> as <item> [limit=N] [collect=<var>[(<fields>)]]
...
@end

The optional `limit=N` parameter caps the number of iterations.

## Collecting Results

The optional `collect=<var>` parameter accumulates exposed variables from each successful iteration into a list.

Example:

@loop handlers as handler limit=5 collect=summaries

@task inspect_handler
Goal: Understand what ${handler} does.
Expose: handler_summary, handler_priority
@end

@end

After the loop, `summaries` contains:

[
  {"handler_summary": "...", "handler_priority": "high"},
  {"handler_summary": "...", "handler_priority": "low"}
]

To collect only specific fields, use parentheses:

@loop handlers as handler collect=summaries(handler_summary)

This produces:

[
  {"handler_summary": "..."},
  {"handler_summary": "..."}
]

Failed iterations are skipped and do not appear in the collected list.

## Basic Loop

Example without collect:

@loop handlers as handler limit=5

@task inspect_handler
Goal: Understand what ${handler} does.
Expose: handler_summary
@end

@end

---

# Return

Workflows can return a result.

@return handlers

---

# Example Workflow

@start

@task find_handlers @no-kg
Goal: Find HTTP handlers defined in the repository.
Expose: handlers
@end

@if len(handlers) > 0

@loop handlers as handler limit=5

@task inspect_handler @no-history
Goal: Understand what ${handler} does.
Expose: handler_summary
@end

@end

@else

@task fallback_search
Goal: Search more broadly for request entry points.
Expose: handlers
@end

@end

@return handlers

@end

---

# Runtime Architecture

The runtime contains four main components.

| Component | Responsibility |
|---|---|
| Workflow Engine | executes AWL scripts |
| Agent | performs reasoning |
| Tool Runtime | executes tools safely |
| Memory System | stores workflow state |

Execution pipeline:

AWL Script
↓
Parser
↓
Workflow AST
↓
Runtime Engine
↓
Agent reasoning loop
↓
Tool execution
↓
Memory updates

---

# Task Execution Model

Each task runs an **agent reasoning loop**.

Lifecycle:

task start
↓
build task context
↓
agent reasoning loop
↓
success detection
↓
store exposed variables
↓
task end

---

# Task Context

Before executing a task, the runtime builds a context object.

Example:

{
  "task_id": "find_server",
  "goal": "Find where the HTTP server is initialized.",
  "success": "Identify the file and function responsible for startup.",
  "expose": ["server_file","server_function"],
  "variables": {}
}

Hints such as `@no-history` and `@no-kg` are included in this context.

---

# Task Outcomes

A task may terminate with one of several outcomes.

| Status | Meaning |
|---|---|
| success | goal achieved |
| failed | task attempted but not successful |
| blocked | task cannot proceed due to missing dependency |
| aborted | execution intentionally stopped |

Example success result:

{
  "status": "success",
  "summary": "Server initialized in cmd/server/main.go",
  "exposed": {
    "server_file": "cmd/server/main.go"
  }
}

Example blocked result:

{
  "status": "blocked",
  "reason": "repository_not_loaded",
  "message": "Cannot analyze repository because none is loaded."
}

---

# Runtime Limits

Safety limits enforced by the runtime.

| Limit | Purpose |
|---|---|
| max_steps | maximum reasoning steps |
| max_tool_calls | maximum tool executions |
| timeout | maximum task duration |

Example configuration:

max_steps = 12
max_tool_calls = 20
timeout = 30s

---

# Goals

Goals enable **autonomous agent behavior** by scheduling periodic execution of an AWL body.

Syntax:

@goal <goal_id> [max_actions=<N>]
  Success: <natural language criterion>
  <body>
@end

Parameters:

| Parameter | Required | Description |
|---|---|---|
| max_actions | no | Max tool calls per cycle (default: 5) |

Scheduling is independent from the goal definition. Goals can be run:

- From the CLI: `ai-assist /run goal.awl`
- Via `schedules.json`: `{"prompt": "goals/track_failures.awl", "interval": "30m"}`
- As a one-shot scheduled action

The `Success:` field is mandatory. After each cycle, Claude evaluates whether the criterion is met. When met, the goal status is set to "completed" and scheduling stops.

## Variable Persistence

Variables exposed by tasks inside the goal body persist between cycles via a JSON sidecar file. This allows the goal to track state across executions.

## Example

@start

@goal track_failures max_actions=5
  Success: Failure rate stays below 10%

  @task check_status @no-history
  Goal: Check DCI failure rate for OCP 4.19.
  Expose: failure_rate, failures
  @end

  @if failure_rate > 10
    @task create_alert
    Goal: Write a failure report about ${failures}.
    @end
  @end

@end

@end

## Goal Files

Goal AWL scripts live in `~/.ai-assist/goals/`. The monitor mode scans this directory and schedules active goals. State is persisted in `~/.ai-assist/state/goal_<id>.json`.

## Goal Management

The agent can create, list, and update goals via built-in tools:

- `goal__create` -- generates a `.awl` file
- `goal__list` -- scans the goals directory
- `goal__update` -- changes goal status (pause, resume, cancel)

---

# Summary

The Agent Workflow Language enables structured orchestration of AI agents.

Key properties:

- intent-driven workflows
- agent autonomy
- task hints controlling context
- deterministic execution
- extensible architecture
