"""Config file watching for auto-reload

This module provides shared configuration file watching used by both
monitor mode and interactive mode.
"""

from .config import get_config_dir
from .file_watchdog import FileWatchdog


class ConfigWatcher:
    """Watch config files and trigger callbacks on changes

    This class watches multiple configuration files and triggers
    appropriate reload callbacks when they change.

    Attributes:
        agent: The AiAssistAgent instance
        watchers: List of active FileWatchdog instances
    """

    def __init__(self, agent):
        """Initialize config watcher

        Args:
            agent: The AiAssistAgent instance to reload configs for
        """
        self.agent = agent
        self.watchers = []

    async def start(self):
        """Start watching all config files"""
        config_dir = get_config_dir()

        # Watch mcp_servers.yaml
        mcp_file = config_dir / "mcp_servers.yaml"
        if mcp_file.exists():
            watcher = FileWatchdog(mcp_file, self._on_mcp_change, debounce_seconds=1.0)
            await watcher.start()
            self.watchers.append(watcher)
            print(f"Watching {mcp_file} for changes")

        # Watch identity.yaml
        identity_file = config_dir / "identity.yaml"
        if identity_file.exists():
            watcher = FileWatchdog(identity_file, self._on_identity_change, debounce_seconds=1.0)
            await watcher.start()
            self.watchers.append(watcher)
            print(f"Watching {identity_file} for changes")

        # Watch installed-skills.json
        skills_file = config_dir / "installed-skills.json"
        if skills_file.exists():
            watcher = FileWatchdog(skills_file, self._on_skills_change, debounce_seconds=1.0)
            await watcher.start()
            self.watchers.append(watcher)
            print(f"Watching {skills_file} for changes")

    async def _on_mcp_change(self):
        """Callback when mcp_servers.yaml changes"""
        try:
            await self.agent.reload_mcp_servers()
        except Exception as e:
            print(f"❌ Failed to reload MCP servers: {e}")

    async def _on_identity_change(self):
        """Callback when identity.yaml changes"""
        try:
            from .identity import get_identity

            self.agent.identity = get_identity(reload=True)
            print("✅ Identity reloaded")
        except Exception as e:
            print(f"❌ Failed to reload identity: {e}")

    async def _on_skills_change(self):
        """Callback when installed-skills.json changes"""
        try:
            self.agent.skills_manager.load_installed_skills()
            print("✅ Skills reloaded")
        except Exception as e:
            print(f"❌ Failed to reload skills: {e}")

    async def stop(self):
        """Stop all watchers"""
        for watcher in self.watchers:
            await watcher.stop()
