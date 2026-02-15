"""Filesystem tools for ai-assist agent"""

import json
import re
import shlex
import subprocess
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from .config import AiAssistConfig, get_config_dir

ALLOWED_COMMANDS_FILE = "allowed_commands.json"


class FilesystemTools:
    """Internal filesystem tools for the agent"""

    def __init__(self, config: AiAssistConfig):
        """Initialize filesystem tools

        Args:
            config: AiAssistConfig instance for security settings
        """
        self.allowed_commands = list(config.allowed_commands)
        self._load_user_allowed_commands()
        self.allowed_paths = [Path(p).expanduser().resolve() for p in config.allowed_paths if p]
        self.confirm_tools = config.confirm_tools
        self.confirmation_callback: Callable[[str], Awaitable[bool]] | None = None

    def _load_user_allowed_commands(self):
        """Load user-added allowed commands from persistent file."""
        path = get_config_dir() / ALLOWED_COMMANDS_FILE
        if not path.exists():
            return
        try:
            with open(path) as f:
                commands = json.load(f)
            for cmd in commands:
                if cmd not in self.allowed_commands:
                    self.allowed_commands.append(cmd)
        except (json.JSONDecodeError, OSError):
            pass

    def add_permanent_allowed_command(self, cmd_name: str):
        """Add a command to the persistent allowlist."""
        if cmd_name not in self.allowed_commands:
            self.allowed_commands.append(cmd_name)

        path = get_config_dir() / ALLOWED_COMMANDS_FILE
        try:
            existing: list[str] = []
            if path.exists():
                with open(path) as f:
                    existing = json.load(f)
        except (json.JSONDecodeError, OSError):
            existing = []

        if cmd_name not in existing:
            existing.append(cmd_name)
            with open(path, "w") as f:
                json.dump(existing, f, indent=2)

    def _validate_path(self, path_str: str) -> str | None:
        """Validate that a path is within allowed directories.

        Returns:
            Error message if path is not allowed, None if validation passes
        """
        if not self.allowed_paths:
            return None

        resolved = Path(path_str).expanduser().resolve()

        for allowed in self.allowed_paths:
            try:
                resolved.relative_to(allowed)
                return None
            except ValueError:
                continue

        allowed_list = ", ".join(str(p) for p in self.allowed_paths)
        return f"Error: Path '{resolved}' is outside allowed directories: {allowed_list}. Not allowed."

    def get_tool_definitions(self) -> list[dict]:
        """Get tool definitions for the agent

        Returns:
            List of tool definitions in Anthropic tool format
        """
        return [
            {
                "name": "internal__read_file",
                "description": "Read the contents of a file from the filesystem. Can read the entire file (up to 15KB) or specific line ranges. For large files, use line_start and line_end to read only relevant sections. Use search_in_file first to find line numbers of interest.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Absolute path to the file to read"},
                        "line_start": {
                            "type": "integer",
                            "description": "Starting line number (1-indexed). If specified, reads from this line.",
                            "default": None,
                        },
                        "line_end": {
                            "type": "integer",
                            "description": "Ending line number (1-indexed). If specified with line_start, reads only this range.",
                            "default": None,
                        },
                        "max_lines": {
                            "type": "integer",
                            "description": "Maximum number of lines to read (default: unlimited, but subject to 15KB total limit)",
                            "default": None,
                        },
                    },
                    "required": ["path"],
                },
                "_server": "internal",
                "_original_name": "read_file",
            },
            {
                "name": "internal__search_in_file",
                "description": "Search for a regex pattern in a file. Returns matching lines with line numbers. Use this to find specific patterns, errors, or keywords in log files.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Absolute path to the file to search"},
                        "pattern": {"type": "string", "description": "Regex pattern to search for"},
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of matching lines to return (default: 100)",
                            "default": 100,
                        },
                    },
                    "required": ["path", "pattern"],
                },
                "_server": "internal",
                "_original_name": "search_in_file",
            },
            {
                "name": "internal__create_directory",
                "description": "Create a directory (and parent directories if needed). Use this to create directories for storing reports, logs, or downloaded files.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Absolute path to the directory to create"}
                    },
                    "required": ["path"],
                },
                "_server": "internal",
                "_original_name": "create_directory",
            },
            {
                "name": "internal__list_directory",
                "description": "List files and directories in a directory. Returns a list of names with file/directory indicators.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Absolute path to the directory to list"},
                        "pattern": {
                            "type": "string",
                            "description": "Optional glob pattern to filter results (e.g., '*.log')",
                            "default": "*",
                        },
                    },
                    "required": ["path"],
                },
                "_server": "internal",
                "_original_name": "list_directory",
            },
            {
                "name": "internal__execute_command",
                "description": "Execute a command and return the output. Commands are checked against an allowlist. Non-allowlisted commands require user approval in interactive mode. Be careful with commands that might take a long time or produce large output.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "The command to execute"},
                        "working_directory": {
                            "type": "string",
                            "description": "Optional working directory for the command (default: current directory)",
                            "default": None,
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "Timeout in seconds (default: 30, max: 300)",
                            "default": 30,
                        },
                    },
                    "required": ["command"],
                },
                "_server": "internal",
                "_original_name": "execute_command",
            },
        ]

    async def execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """Execute a filesystem tool

        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments

        Returns:
            Tool result as string
        """
        if tool_name == "read_file":
            return await self._read_file(arguments)
        elif tool_name == "search_in_file":
            return await self._search_in_file(arguments)
        elif tool_name == "create_directory":
            return await self._create_directory(arguments)
        elif tool_name == "list_directory":
            return await self._list_directory(arguments)
        elif tool_name == "execute_command":
            return await self._execute_command(arguments)
        else:
            return f"Error: Unknown filesystem tool: {tool_name}"

    async def _check_confirmation(self, tool_full_name: str, description: str) -> str | None:
        """Check if a tool requires confirmation and prompt the user.

        Args:
            tool_full_name: Full tool name (e.g. "internal__create_directory")
            description: Human-readable description of the action

        Returns:
            Error message if rejected/blocked, None if approved
        """
        if tool_full_name not in self.confirm_tools:
            return None

        if self.confirmation_callback is None:
            return None

        approved = await self.confirmation_callback(description)
        if not approved:
            return f"Error: Action rejected by user: {description}"

        return None

    async def _read_file(self, args: dict) -> str:
        """Read a file from the filesystem"""
        path = args.get("path")
        line_start = args.get("line_start")
        line_end = args.get("line_end")
        max_lines = args.get("max_lines")

        if not path:
            return "Error: path parameter is required"

        path_error = self._validate_path(path)
        if path_error:
            return path_error

        try:
            path_obj = Path(path).expanduser()

            if not path_obj.exists():
                return f"Error: File not found: {path}"

            if not path_obj.is_file():
                return f"Error: Not a file: {path}"

            with open(path_obj, encoding="utf-8", errors="replace") as f:
                if line_start is not None or line_end is not None or max_lines is not None:
                    lines: list[str] = []
                    start = line_start if line_start else 1
                    end = line_end if line_end else float("inf")
                    limit = max_lines if max_lines else float("inf")

                    for line_num, line in enumerate(f, 1):
                        if line_num < start:
                            continue
                        if line_num > end:
                            break
                        if len(lines) >= limit:
                            break
                        lines.append(f"{line_num}: {line.rstrip()}")

                    content = "\n".join(lines)

                    max_size = 15000
                    if len(content) > max_size:
                        content = content[:max_size] + f"\n\n... (truncated at {max_size} chars)"

                    range_info = f"lines {start}"
                    if line_end:
                        range_info = f"lines {start}-{line_end}"
                    elif max_lines:
                        range_info += f" (max {max_lines} lines)"

                    return f"File contents ({path_obj.name}, {range_info}, {len(lines)} lines, {len(content)} chars):\n\n{content}"

                else:
                    content = f.read()
                    max_size = 15000
                    if len(content) > max_size:
                        return f"File contents (first {max_size} chars, total {len(content)} chars):\n\n{content[:max_size]}\n\n... (truncated - use line_start/line_end to read specific sections or search_in_file to find patterns)"

                    return f"File contents ({len(content)} chars):\n\n{content}"

        except Exception as e:
            return f"Error reading file: {str(e)}"

    async def _search_in_file(self, args: dict) -> str:
        """Search for a pattern in a file"""
        path = args.get("path")
        pattern = args.get("pattern")
        max_results = args.get("max_results", 100)

        if not path or not pattern:
            return "Error: path and pattern parameters are required"

        path_error = self._validate_path(path)
        if path_error:
            return path_error

        try:
            path_obj = Path(path).expanduser()

            if not path_obj.exists():
                return f"Error: File not found: {path}"

            if not path_obj.is_file():
                return f"Error: Not a file: {path}"

            try:
                regex = re.compile(pattern)
            except re.error as e:
                return f"Error: Invalid regex pattern: {e}"

            matches = []
            with open(path_obj, encoding="utf-8", errors="replace") as f:
                for line_num, line in enumerate(f, 1):
                    if regex.search(line):
                        matches.append(f"{line_num}: {line.rstrip()}")
                        if len(matches) >= max_results:
                            break

            if not matches:
                return f"No matches found for pattern: {pattern}"

            result = f"Found {len(matches)} match(es) for pattern '{pattern}':\n\n"
            result += "\n".join(matches)

            if len(matches) >= max_results:
                result += f"\n\n... (limited to {max_results} results)"

            return result

        except Exception as e:
            return f"Error searching file: {str(e)}"

    async def _create_directory(self, args: dict) -> str:
        """Create a directory"""
        path = args.get("path")
        if not path:
            return "Error: path parameter is required"

        path_error = self._validate_path(path)
        if path_error:
            return path_error

        confirm_error = await self._check_confirmation("internal__create_directory", f"Create directory: {path}")
        if confirm_error:
            return confirm_error

        try:
            path_obj = Path(path).expanduser()

            path_obj.mkdir(parents=True, exist_ok=True)

            return f"Directory created: {path_obj}"

        except Exception as e:
            return f"Error creating directory: {str(e)}"

    async def _list_directory(self, args: dict) -> str:
        """List files and directories"""
        path = args.get("path")
        pattern = args.get("pattern", "*")

        if not path:
            return "Error: path parameter is required"

        path_error = self._validate_path(path)
        if path_error:
            return path_error

        try:
            path_obj = Path(path).expanduser()

            if not path_obj.exists():
                return f"Error: Directory not found: {path}"

            if not path_obj.is_dir():
                return f"Error: Not a directory: {path}"

            items = list(path_obj.glob(pattern))
            items.sort()

            if not items:
                return f"No items found matching pattern '{pattern}' in {path}"

            result = f"Contents of {path_obj} (pattern: {pattern}):\n\n"

            for item in items:
                if item.is_dir():
                    result += f"  [DIR]  {item.name}/\n"
                else:
                    size = item.stat().st_size
                    result += f"  [FILE] {item.name} ({size} bytes)\n"

            return result

        except Exception as e:
            return f"Error listing directory: {str(e)}"

    async def _check_command_allowed(self, cmd_token: str, full_command: str) -> str | None:
        """Check if a command is allowed, prompting for confirmation if needed.

        Returns:
            Error message if blocked, None if allowed
        """
        cmd_name = Path(cmd_token).name
        if cmd_name in self.allowed_commands:
            return None

        if self.confirmation_callback is not None:
            approved = await self.confirmation_callback(full_command)
            if approved:
                return None
            return f"Error: Command '{full_command}' was rejected by the user. Try a different approach or use only allowed commands: {', '.join(self.allowed_commands)}."

        allowed_list = ", ".join(self.allowed_commands)
        return f"Error: Command '{cmd_name}' is not in the allowed commands list: {allowed_list}. Not allowed."

    async def _execute_command(self, args: dict) -> str:
        """Execute a command with allowlist enforcement"""
        command = args.get("command")
        working_dir = args.get("working_directory")
        timeout = args.get("timeout", 30)

        if not command:
            return "Error: command parameter is required"

        # In interactive mode (confirmation_callback set), no timeout -- the user
        # can press Escape to interrupt like any normal interaction.
        # In non-interactive mode, enforce a timeout to prevent runaway commands.
        if self.confirmation_callback is not None:
            timeout = None
        else:
            timeout = min(timeout, 300)  # Max 5 minutes

        try:
            cmd_parts = shlex.split(command)
        except ValueError as e:
            return f"Error: Invalid command syntax: {e}"

        if not cmd_parts:
            return "Error: Empty command"

        error = await self._check_command_allowed(cmd_parts[0], command)
        if error:
            return error

        try:
            cwd = None
            if working_dir:
                cwd = Path(working_dir).expanduser()
                if not cwd.exists() or not cwd.is_dir():
                    return f"Error: Invalid working directory: {working_dir}"

            result = subprocess.run(
                command, shell=True, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False
            )

            output = f"Command: {command}\n"
            if working_dir:
                output += f"Working directory: {cwd}\n"
            output += f"Exit code: {result.returncode}\n\n"

            if result.stdout:
                output += f"STDOUT:\n{result.stdout}\n"

            if result.stderr:
                output += f"STDERR:\n{result.stderr}\n"

            if result.returncode != 0:
                output += f"\nCommand failed with exit code {result.returncode}"

            max_size = 15000
            if len(output) > max_size:
                output = (
                    output[:max_size]
                    + f"\n\n... (truncated, total {len(output)} chars - pipe to file or use smaller commands)"
                )

            return output

        except subprocess.TimeoutExpired:
            return f"Error: Command timed out after {timeout} seconds. Use interactive mode for long-running commands."
        except Exception as e:
            return f"Error executing command: {str(e)}"
