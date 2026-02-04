# MCP Integration Fix Summary

## Problem

BOSS was unable to connect to the dci-mcp-server (FastMCP-based server) via stdio transport. The connection would timeout during session initialization, even though the server was running correctly.

## Root Cause Analysis

Through systematic debugging, we discovered two critical issues:

### 1. MCP SDK Buffering Race Condition

The Python MCP SDK (version 1.26.0) uses unbuffered memory streams:
```python
# Original MCP SDK code
read_stream_writer, read_stream = anyio.create_memory_object_stream(0)  # Buffer size 0!
write_stream, write_stream_reader = anyio.create_memory_object_stream(0)
```

This caused a race condition where:
- The `stdout_reader` task starts but hasn't begun async iteration yet
- The FastMCP server immediately sends its initialize response
- The message is lost because no consumer is ready
- The client times out waiting for a response that was already sent

### 2. Missing ClientSession Context Manager

The ClientSession class must be used as an async context manager to start its internal `_receive_loop` task:
```python
# Original (incorrect) code
session = ClientSession(read_stream, write_stream)
await session.initialize()  # Hangs forever - no receive loop running!

# Fixed code
async with ClientSession(read_stream, write_stream) as session:
    await session.initialize()  # Works - receive loop processes messages
```

Without the context manager, the `_receive_loop` task never starts, so messages sent to `read_stream` are never processed.

## Solution

### Fix #1: Patched stdio_client with Buffer Size 10

Created `boss/mcp_stdio_fix.py` - a patched version of the MCP SDK's stdio_client:

```python
# FIXED: Use buffer size 10 instead of 0
read_stream_writer, read_stream = anyio.create_memory_object_stream(10)
write_stream, write_stream_reader = anyio.create_memory_object_stream(10)
```

This allows messages to queue if the receiver isn't immediately ready, eliminating the race condition.

### Fix #2: Use ClientSession as Async Context Manager

Modified `boss/agent.py` to properly use ClientSession:

```python
async with ClientSession(read_stream, write_stream) as session:
    await session.initialize()
    # ... use session ...
```

This ensures the `_receive_loop` background task starts and processes incoming messages.

### Fix #3: Filter Custom Tool Fields

The Anthropic API doesn't allow custom fields in tool definitions. We filter internal fields before sending:

```python
api_tools = [
    {
        "name": tool["name"],
        "description": tool["description"],
        "input_schema": tool["input_schema"],
        # _server and _original_name are kept in self.available_tools for routing
    }
    for tool in self.available_tools
]
```

## Configuration Changes

Updated `boss/config.py` to run the dci-mcp-server venv python directly:

```python
# Before (incorrect - mixed uv run with venv path)
command="uv",
args=["run", f"{dci_server_path}/.venv/bin/python", f"{dci_server_path}/main.py"],

# After (correct - direct venv execution)
command=f"{dci_server_path}/.venv/bin/python",
args=[f"{dci_server_path}/main.py"],
```

## Verification

```bash
$ uv run python test_query.py

======================================================================
Testing DCI MCP Integration with Query
======================================================================

Using Vertex AI: project=itpc-gcp-eco-eng-claude (default region)
Connecting to servers...
✓ Connected to dci MCP server with 15 tools

Available tools: 15
Tool names: ['dci__query_dci_components', 'dci__today', 'dci__now', 'dci__search_dci_jobs', 'dci__download_dci_file']

----------------------------------------------------------------------
Testing query: What is today's date?
----------------------------------------------------------------------

Response: Today's date is **2026-02-04** (February 4, 2026).

Test complete!
```

## Files Modified

1. **boss/mcp_stdio_fix.py** (created) - Patched stdio client with buffer size 10
2. **boss/agent.py** - Use ClientSession as async context manager + filter tool fields
3. **boss/config.py** - Use venv python directly instead of `uv run`

## Technical Details

### MCP Protocol Flow

1. Client sends `initialize` request with protocol version and capabilities
2. Server responds with `InitializeResult` (server info, capabilities, protocol version)
3. Client sends `notifications/initialized` notification
4. Server starts its main loop and keeps connection alive
5. Client can now call tools via `tools/list` and `tools/call`

### Why TypeScript MCP SDK Works

The user reported that the same dci-mcp-server command works with Claude Code, Cursor, and Gemini CLI. These tools likely use the TypeScript MCP SDK, which may:
- Use buffered streams by default
- Handle the async context manager pattern differently
- Have different timing that avoids the race condition

The Python MCP SDK has this specific issue with unbuffered streams.

## Lessons Learned

1. **Buffer size matters** - Even with async/await, unbuffered streams can cause race conditions
2. **Context managers are not optional** - Some async objects require `async with` to function correctly
3. **API schemas are strict** - Custom fields in tool definitions break the Anthropic API
4. **Protocol debugging tools are invaluable** - Raw stdio testing revealed the server was working correctly

## Future Improvements

1. Submit upstream fix to MCP SDK for the buffering issue
2. Add integration tests for MCP server connections
3. Add retry logic for transient connection failures
4. Support multiple MCP servers with different transports (stdio, SSE, WebSocket)
