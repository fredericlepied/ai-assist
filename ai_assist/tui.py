"""TUI components for ai-assist"""

from prompt_toolkit.completion import Completer, Completion


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
            "/prompts",
            "/search",
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

            # Check if this looks like a prompt command (has a slash in it)
            parts = word.lstrip("/").split("/")

            # Completing MCP prompts: /server/prompt
            if len(parts) == 2 and self.agent:
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

    def _get_command_description(self, command: str) -> str:
        """Get description for a command"""
        descriptions = {
            "/status": "Show state statistics",
            "/history": "Show recent monitoring history",
            "/clear-cache": "Clear expired cache",
            "/clear": "Clear conversation memory",
            "/kg-save": "Toggle knowledge graph auto-save",
            "/prompts": "List available MCP prompts",
            "/search": "Search conversation history",
            "/exit": "Exit interactive mode",
            "/quit": "Exit interactive mode",
            "/help": "Show help message",
        }
        return descriptions.get(command, "")
