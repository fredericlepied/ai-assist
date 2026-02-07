"""Code watching for auto-reload in development mode

This module provides code file watching that automatically restarts
the process when Python files change during development.
"""

import os
import sys
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer


class CodeWatcher:
    """Watch Python code files and restart process on changes

    This watcher is intended for development mode only. It monitors
    all .py files in the specified directory tree and automatically
    restarts the process when changes are detected.

    Attributes:
        watch_dir: Directory to watch recursively
        observer: Watchdog observer instance
    """

    def __init__(self, watch_dir: Path):
        """Initialize code watcher

        Args:
            watch_dir: Directory to watch for .py file changes
        """
        self.watch_dir = watch_dir
        self.observer: Observer | None = None

    def start(self):
        """Start watching code files for changes"""
        handler = _ChangeHandler(self._restart)
        self.observer = Observer()
        self.observer.schedule(handler, str(self.watch_dir), recursive=True)
        self.observer.start()
        print(f"🔧 Dev mode: Watching {self.watch_dir} for code changes")

    def _restart(self, filepath: str):
        """Restart the process when code changes

        Args:
            filepath: Path to the file that changed
        """
        print(f"\n🔄 Code changed: {filepath}")
        print("🔄 Restarting...")

        # Use os.execv to replace current process with new one
        # This preserves the same PID and command line arguments
        os.execv(sys.executable, [sys.executable] + sys.argv)

    def stop(self):
        """Stop watching code files"""
        if self.observer:
            self.observer.stop()
            self.observer.join(timeout=2.0)


class _ChangeHandler(FileSystemEventHandler):
    """Internal handler for code file change events"""

    def __init__(self, callback):
        """Initialize change handler

        Args:
            callback: Function to call when .py file changes
        """
        super().__init__()
        self.callback = callback

    def on_modified(self, event: FileSystemEvent):
        """Handle file modification events

        Args:
            event: File system event
        """
        if event.is_directory:
            return

        # Only react to .py file changes
        if event.src_path.endswith(".py"):
            self.callback(event.src_path)
