#!/usr/bin/env python3
"""Eval harness wrapper for ai-assist agent.

Bridges the agent-eval-harness CLI runner interface to ai-assist's agent API.
Reads input.yaml from workspace, runs a query, and writes structured output
(response, tool calls, metrics) to the output directory.
"""

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

import yaml


async def run(workspace: Path, output_dir: Path, model: str, timeout: int):
    # Isolate from the user's installed agent config
    eval_config_dir = workspace / ".ai-assist"
    eval_config_dir.mkdir(exist_ok=True)
    os.environ["AI_ASSIST_CONFIG_DIR"] = str(eval_config_dir)
    os.environ["AI_ASSIST_REPORTS_DIR"] = str(workspace / "reports")

    from ai_assist.agent import AiAssistAgent
    from ai_assist.config import AiAssistConfig
    from ai_assist.knowledge_graph import KnowledgeGraph

    # Read input
    input_file = workspace / "input.yaml"
    if not input_file.exists():
        print(f"ERROR: {input_file} not found", file=sys.stderr)
        sys.exit(1)

    with open(input_file) as f:
        input_data = yaml.safe_load(f)
    prompt = input_data.get("prompt", "")
    if not prompt:
        print("ERROR: input.yaml has no 'prompt' field", file=sys.stderr)
        sys.exit(1)

    # Create temporary KG in workspace for isolation
    kg_path = str(workspace / "knowledge_graph.db")
    kg = KnowledgeGraph(db_path=kg_path)

    # Minimal config: internal tools only, no MCP servers
    config = AiAssistConfig(model=model, mcp_servers={})
    agent = AiAssistAgent(config, knowledge_graph=kg)

    # Register internal tools (connect_to_servers populates available_tools)
    await agent.connect_to_servers()

    # Run query
    start_time = time.time()
    response = await agent.query(prompt, max_time_seconds=timeout)

    # Capture trace (must happen before clear_tool_calls)
    trace = agent.capture_trace(prompt, response, start_time)

    # Extract tool calls with full detail
    tool_calls = [{"name": tc["tool_name"], "input": tc["arguments"]} for tc in agent.last_tool_calls]

    # Write outputs
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "response.txt").write_text(response)
    (output_dir / "tool_calls.json").write_text(json.dumps(tool_calls, indent=2, default=str))

    metrics = {
        "token_usage": {
            "input": trace.total_input_tokens,
            "output": trace.total_output_tokens,
        },
        "num_turns": trace.turn_count,
        "model": trace.model,
    }
    (output_dir / "metrics.json").write_text(json.dumps(metrics))

    # Print response to stdout (captured by harness)
    print(response)

    # Clean up KG
    kg.conn.close()


def main():
    parser = argparse.ArgumentParser(description="ai-assist eval wrapper")
    parser.add_argument("--workspace", required=True, help="Workspace directory")
    parser.add_argument("--output-dir", required=True, help="Output directory")
    parser.add_argument("--model", default="claude-sonnet-4-6", help="Model to use")
    parser.add_argument("--timeout", type=int, default=120, help="Timeout in seconds")
    args = parser.parse_args()

    asyncio.run(
        run(
            workspace=Path(args.workspace),
            output_dir=Path(args.output_dir),
            model=args.model,
            timeout=args.timeout,
        )
    )


if __name__ == "__main__":
    main()
