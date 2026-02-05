"""File watcher for hot-reloading schedule definitions"""

import asyncio
from pathlib import Path
from typing import Callable, Optional


class TaskFileWatcher:
    """Watch a file for changes and trigger reload"""

    def __init__(self, task_file: Path, callback: Callable):
        """Initialize file watcher

        Args:
            task_file: Path to the file to watch (e.g., schedules.json)
            callback: Async function to call when file changes
        """
        self.task_file = task_file
        self.callback = callback
        self.last_modified: Optional[float] = None
        self.running = False

    async def watch(self, check_interval: int = 5):
        """Watch file for changes

        Args:
            check_interval: How often to check for changes (seconds)
        """
        self.running = True

        # Initialize last_modified time
        if self.task_file.exists():
            self.last_modified = self.task_file.stat().st_mtime

        while self.running:
            try:
                if self._file_changed():
                    print(f"\n🔄 Detected changes in {self.task_file}")
                    try:
                        await self.callback()
                    except Exception as e:
                        print(f"Error reloading tasks: {e}")
                        print("Tasks not reloaded due to error")

            except Exception as e:
                print(f"Error in file watcher: {e}")

            await asyncio.sleep(check_interval)

    def _file_changed(self) -> bool:
        """Check if file was modified since last check"""
        if not self.task_file.exists():
            # File was deleted
            if self.last_modified is not None:
                self.last_modified = None
                return True
            return False

        mtime = self.task_file.stat().st_mtime

        # First check or file was modified
        if self.last_modified is None or mtime != self.last_modified:
            self.last_modified = mtime
            # Don't trigger on first check
            if self.last_modified is not None:
                return True

        return False

    def stop(self):
        """Stop watching the file"""
        self.running = False
