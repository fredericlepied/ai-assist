"""TUI components for ai-assist"""

from prompt_toolkit.completion import Completer, Completion


class AiAssistCompleter(Completer):
    """Command completer for ai-assist interactive mode"""

    def __init__(self):
        self.commands = [
            "/status",
            "/history",
            "/clear-cache",
            "/clear",
            "/kg-save",
            "/search",
            "/exit",
            "/quit",
            "/help"
        ]

    def get_completions(self, document, complete_event):
        """Get completions for the current input"""
        text = document.text_before_cursor

        # Only complete if line starts with /
        if text.startswith("/"):
            word = text  # Keep the full text including /
            for cmd in self.commands:
                if cmd.startswith(word.lower()):
                    # Yield the remainder of the command
                    yield Completion(
                        cmd,
                        start_position=-len(word),
                        display=cmd,
                        display_meta=self._get_command_description(cmd)
                    )

    def _get_command_description(self, command: str) -> str:
        """Get description for a command"""
        descriptions = {
            "/status": "Show state statistics",
            "/history": "Show recent monitoring history",
            "/clear-cache": "Clear expired cache",
            "/clear": "Clear conversation memory",
            "/kg-save": "Toggle knowledge graph auto-save",
            "/search": "Search conversation history",
            "/exit": "Exit interactive mode",
            "/quit": "Exit interactive mode",
            "/help": "Show help message"
        }
        return descriptions.get(command, "")
