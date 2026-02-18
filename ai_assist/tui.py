"""TUI components for ai-assist"""

from prompt_toolkit.completion import Completer, Completion


def format_tool_display_name(tool_name: str) -> str:
    """Format a tool name for user-friendly display.

    Converts internal tool names like 'mcp__dci__search' to 'dci → search'.
    """
    return tool_name.replace("mcp__", "").replace("__", " → ").replace("_", " ")


def format_tool_args(input_dict: dict, max_len: int = 100) -> str:
    """Format tool arguments for display, truncating long values."""
    args_display = []
    for key, value in input_dict.items():
        value_str = str(value)
        if len(value_str) > max_len:
            value_str = value_str[:max_len] + "..."
        args_display.append(f"{key}={value_str}")
    return ", ".join(args_display)


class AiAssistCompleter(Completer):
    """Command completer for ai-assist interactive mode"""

    def __init__(self, agent=None):
        self.agent = agent
        self.commands = [
            "/status",
            "/history",
            "/clear-cache",
            "/clear",
            "/kg-save",
            "/kg-viz",
            "/prompts",
            "/search",
            "/skill/install",
            "/skill/uninstall",
            "/skill/list",
            "/skill/search",
            "/mcp/restart",
            "/exit",
            "/quit",
            "/help",
        ]

    def get_completions(self, document, complete_event):
        """Get completions for the current input"""
        text = document.text_before_cursor

        # Only complete if line starts with /
        if text.startswith("/"):
            word = text  # Keep the full text including /

            # Special handling for skill commands with arguments (space-separated)
            if text.startswith("/skill/uninstall ") and self.agent:
                # Complete with installed skill names
                prefix = text.split(" ", 1)[1] if " " in text else ""
                for skill in self.agent.skills_manager.installed_skills:
                    if skill.name.startswith(prefix.lower()):
                        full_command = f"/skill/uninstall {skill.name}"
                        yield Completion(
                            full_command,
                            start_position=-len(text),
                            display=full_command,
                            display_meta=f"{skill.source}",
                        )
                return  # Don't continue to other completions

            if text.startswith("/mcp/restart ") and self.agent:
                # Complete with configured MCP server names
                prefix = text.split(" ", 1)[1] if " " in text else ""
                for server_name in self.agent.config.mcp_servers.keys():
                    if server_name.startswith(prefix):
                        full_command = f"/mcp/restart {server_name}"
                        yield Completion(
                            full_command,
                            start_position=-len(text),
                            display=full_command,
                            display_meta="MCP server",
                        )
                return  # Don't continue to other completions

            if text.startswith("/skill/install "):
                # Suggest example patterns
                prefix = text.split(" ", 1)[1] if " " in text else ""
                examples = [
                    ("clawhub:skill-slug", "Install from ClawHub registry"),
                    ("anthropics/skills/skills/pdf@main", "Official PDF skill from Anthropic"),
                    ("anthropics/skills/skills/docx@main", "Official DOCX skill from Anthropic"),
                    ("/path/to/skill@main", "Local skill path example"),
                ]
                for example, description in examples:
                    if example.startswith(prefix):
                        full_command = f"/skill/install {example}"
                        yield Completion(
                            full_command,
                            start_position=-len(text),
                            display=full_command,
                            display_meta=description,
                        )
                return  # Don't continue to other completions

            # Check if this looks like a prompt command (has a slash in it)
            parts = word.lstrip("/").split("/")

            # Completing MCP prompts: /server/prompt
            if len(parts) == 2 and self.agent and parts[0] != "skill":
                server_name, prompt_prefix = parts

                # If we have prompts from this server
                if server_name in self.agent.available_prompts:
                    for prompt_name, prompt in self.agent.available_prompts[server_name].items():
                        if prompt_name.startswith(prompt_prefix.lower()):
                            full_command = f"/{server_name}/{prompt_name}"
                            yield Completion(
                                full_command,
                                start_position=-len(word),
                                display=full_command,
                                display_meta=prompt.description[:60] if prompt.description else "MCP prompt",
                            )

            # Completing server names: /server
            elif len(parts) == 1 and self.agent and self.agent.available_prompts:
                # Suggest server names that have prompts
                for server_name in self.agent.available_prompts.keys():
                    server_cmd = f"/{server_name}/"
                    if server_cmd.startswith(word.lower()):
                        yield Completion(
                            server_cmd,
                            start_position=-len(word),
                            display=server_cmd,
                            display_meta=f"MCP server ({len(self.agent.available_prompts[server_name])} prompts)",
                        )

            # Standard command completion
            for cmd in self.commands:
                if cmd.startswith(word.lower()):
                    # Yield the remainder of the command
                    yield Completion(
                        cmd, start_position=-len(word), display=cmd, display_meta=self._get_command_description(cmd)
                    )
        else:
            # Mid-sentence: check if cursor is on a /server/prompt token
            words = text.split()
            if not words:
                return
            last_word = words[-1]
            if not last_word.startswith("/"):
                return
            # Only complete MCP prompts mid-sentence, not built-in commands
            if not self.agent or not self.agent.available_prompts:
                return

            parts = last_word.lstrip("/").split("/")

            if len(parts) == 2 and parts[0] != "skill":
                server_name, prompt_prefix = parts
                if server_name in self.agent.available_prompts:
                    for prompt_name, prompt in self.agent.available_prompts[server_name].items():
                        if prompt_name.startswith(prompt_prefix.lower()):
                            full_token = f"/{server_name}/{prompt_name}"
                            yield Completion(
                                full_token,
                                start_position=-len(last_word),
                                display=full_token,
                                display_meta=prompt.description[:60] if prompt.description else "MCP prompt",
                            )
            elif len(parts) == 1:
                for server_name in self.agent.available_prompts.keys():
                    server_cmd = f"/{server_name}/"
                    if server_cmd.startswith(last_word.lower()):
                        yield Completion(
                            server_cmd,
                            start_position=-len(last_word),
                            display=server_cmd,
                            display_meta=f"MCP server ({len(self.agent.available_prompts[server_name])} prompts)",
                        )

    def _get_command_description(self, command: str) -> str:
        """Get description for a command"""
        descriptions = {
            "/status": "Show state statistics",
            "/history": "Show recent monitoring history",
            "/clear-cache": "Clear expired cache",
            "/clear": "Clear conversation memory",
            "/kg-save": "Toggle knowledge graph auto-save",
            "/kg-viz": "Visualize knowledge graph in browser",
            "/prompts": "List available MCP prompts",
            "/search": "Search conversation history",
            "/skill/install": "Install an Agent Skill from git, local path, or ClawHub",
            "/skill/uninstall": "Uninstall an installed Agent Skill",
            "/skill/list": "List all installed Agent Skills",
            "/skill/search": "Search ClawHub and skills.sh for skills",
            "/mcp/restart": "Restart an MCP server",
            "/exit": "Exit interactive mode",
            "/quit": "Exit interactive mode",
            "/help": "Show help message",
        }
        return descriptions.get(command, "")
