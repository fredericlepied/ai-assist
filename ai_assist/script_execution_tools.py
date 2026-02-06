"""Script execution tools for Agent Skills with security controls"""

import os
import subprocess
from pathlib import Path


class ScriptExecutionTools:
    """Internal script execution tools for Agent Skills

    Provides secure script execution with multiple layers of protection:
    - Disabled by default (opt-in via config)
    - Permission enforcement (allowed-tools field)
    - Path validation (prevents directory traversal)
    - Environment filtering (removes secrets)
    - Resource limits (timeout, output size)
    """

    def __init__(self, skills_manager, config):
        """Initialize script execution tools

        Args:
            skills_manager: SkillsManager instance
            config: AiAssistConfig instance
        """
        self.skills_manager = skills_manager
        self.enabled = config.allow_skill_script_execution

    def get_tool_definitions(self) -> list[dict]:
        """Return tool definitions if enabled

        Returns:
            List of tool definitions, empty if disabled
        """
        if not self.enabled:
            return []

        return [
            {
                "name": "internal__execute_skill_script",
                "description": "Execute a script from an installed Agent Skill",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "skill_name": {
                            "type": "string",
                            "description": "Name of the skill containing the script",
                        },
                        "script_name": {
                            "type": "string",
                            "description": "Name of the script file (e.g., 'check_fillable_fields.py')",
                        },
                        "args": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional command-line arguments to pass to the script",
                        },
                    },
                    "required": ["skill_name", "script_name"],
                },
                "_server": "internal",
                "_original_name": "execute_skill_script",
            }
        ]

    async def execute_tool(self, tool_name: str, arguments: dict) -> str:
        """Execute script with validation

        Args:
            tool_name: Name of the tool being executed
            arguments: Tool arguments (skill_name, script_name, args)

        Returns:
            Script output or error message
        """
        if not self.enabled:
            return "Error: Script execution is disabled. Enable with allow_skill_script_execution=true"

        skill_name = arguments.get("skill_name")
        script_name = arguments.get("script_name")
        args = arguments.get("args", [])

        try:
            # 1. Validate script path
            script_path = self._validate_script_path(skill_name, script_name)

            # 2. Check allowed-tools permission
            if not self._check_permission(skill_name):
                return f"Error: Skill '{skill_name}' not allowed to execute scripts (missing 'internal__execute_skill_script' in allowed-tools)"

            # 3. Execute with security controls
            return await self._execute_script_safely(script_path, args)

        except ValueError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error: Unexpected error during script execution: {e}"

    def _validate_script_path(self, skill_name: str, script_name: str) -> Path:
        """Validate script path against directory traversal

        Args:
            skill_name: Name of the skill
            script_name: Name of the script

        Returns:
            Validated Path to script

        Raises:
            ValueError: If validation fails
        """
        skill = self.skills_manager.loaded_skills.get(skill_name)
        if not skill:
            raise ValueError(f"Skill '{skill_name}' not installed")

        if script_name not in skill.scripts:
            available = ", ".join(skill.scripts.keys()) if skill.scripts else "none"
            raise ValueError(f"Script '{script_name}' not found in skill. Available scripts: {available}")

        script_path = skill.scripts[script_name]

        # Validate path is within skill directory (prevent directory traversal)
        skill_dir = skill.metadata.skill_path.resolve()
        script_resolved = script_path.resolve()

        if not str(script_resolved).startswith(str(skill_dir)):
            raise ValueError("Path traversal attempt blocked")

        if not script_path.exists():
            raise ValueError(f"Script file not found: {script_path}")

        return script_path

    def _check_permission(self, skill_name: str) -> bool:
        """Check if skill allows script execution

        Args:
            skill_name: Name of the skill

        Returns:
            True if skill has permission, False otherwise
        """
        skill = self.skills_manager.loaded_skills.get(skill_name)
        if not skill:
            return False

        allowed = skill.metadata.allowed_tools

        # If skill explicitly declares allowed-tools, check it
        if allowed:
            return "internal__execute_skill_script" in allowed or "*" in allowed

        # If no allowed-tools declared but skill has scripts, allow execution
        # (since global script execution is already enabled if we got here)
        return bool(skill.scripts)

    async def _execute_script_safely(self, script_path: Path, args: list[str]) -> str:
        """Execute script with security controls

        Args:
            script_path: Path to the script
            args: Command-line arguments

        Returns:
            Script output or error message
        """
        # Build command (no shell injection)
        # Use appropriate interpreter for Python scripts
        if script_path.suffix == ".py":
            cmd = ["python3", str(script_path)] + args
        else:
            # For shell scripts and others, execute directly
            cmd = [str(script_path)] + args

        # Filter environment
        safe_env = self._get_safe_environment()

        try:
            # Execute with timeout
            result = subprocess.run(
                cmd,
                shell=False,  # CRITICAL: prevents shell injection
                cwd=script_path.parent,
                env=safe_env,
                capture_output=True,
                text=True,
                timeout=30,  # 30 second default
            )

            # Limit output size
            output = result.stdout
            if len(output) > 20000:  # 20KB
                output = output[:20000] + "\n... [output truncated at 20KB limit]"

            if result.returncode != 0:
                stderr = result.stderr[:500] if result.stderr else "No error output"
                return (
                    f"Script failed with exit code {result.returncode}:\n\n"
                    f"{stderr}\n\n"
                    f"Check the skill's SKILL.md for required dependencies."
                )

            return output if output else "(Script completed successfully with no output)"

        except subprocess.TimeoutExpired:
            return "Error: Script execution timed out after 30 seconds"
        except FileNotFoundError as e:
            return (
                f"Error: Could not execute script - {e}\n\n"
                f"The script may require dependencies to be installed or execution permissions.\n"
                f"Check the skill's SKILL.md for installation instructions."
            )
        except PermissionError:
            return (
                f"Error: Permission denied when executing script.\n\n"
                f"The script may not have execute permissions. Try:\n"
                f"  chmod +x {script_path}"
            )

    def _get_safe_environment(self) -> dict:
        """Filter environment variables to remove sensitive data

        Returns:
            Filtered environment dict
        """
        SENSITIVE_PATTERNS = [
            "API_KEY",
            "TOKEN",
            "SECRET",
            "PASSWORD",
            "ANTHROPIC_",
            "GOOGLE_",
            "AWS_",
            "AZURE_",
            "GITHUB_TOKEN",
            "JIRA_",
        ]

        safe_env = {}
        for key, value in os.environ.items():
            # Skip if key contains any sensitive pattern
            if not any(pattern in key.upper() for pattern in SENSITIVE_PATTERNS):
                safe_env[key] = value

        # Ensure PATH is available
        safe_env["PATH"] = os.environ.get("PATH", "/usr/bin:/bin")

        return safe_env
