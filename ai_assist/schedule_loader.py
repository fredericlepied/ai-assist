"""Load schedules from JSON file"""

import json
from pathlib import Path

from .tasks import MonitorDefinition, TaskDefinition


class ScheduleLoader:
    """Load monitor and task schedules from JSON file"""

    def __init__(self, json_file: Path):
        """Initialize loader

        Args:
            json_file: Path to schedules.json file
        """
        self.json_file = Path(json_file)

    def load_monitors(self) -> list[MonitorDefinition]:
        """Load monitor definitions from JSON file

        Returns:
            List of MonitorDefinition objects
        """
        data = self._load_json()
        monitors = []

        for monitor_data in data.get("monitors", []):
            try:
                monitor = MonitorDefinition(
                    name=monitor_data["name"],
                    prompt=monitor_data["prompt"],
                    interval=monitor_data["interval"],
                    description=monitor_data.get("description"),
                    enabled=monitor_data.get("enabled", True),
                    conditions=monitor_data.get("conditions", []),
                    knowledge_graph=monitor_data.get("knowledge_graph"),
                )
                monitor.validate()
                monitors.append(monitor)
            except (KeyError, ValueError) as e:
                print(f"Warning: Skipping invalid monitor '{monitor_data.get('name', 'unknown')}': {e}")

        return monitors

    def load_tasks(self) -> list[TaskDefinition]:
        """Load task definitions from JSON file

        Returns:
            List of TaskDefinition objects
        """
        data = self._load_json()
        tasks = []

        for task_data in data.get("tasks", []):
            try:
                task = TaskDefinition(
                    name=task_data["name"],
                    prompt=task_data["prompt"],
                    interval=task_data["interval"],
                    description=task_data.get("description"),
                    enabled=task_data.get("enabled", True),
                    conditions=task_data.get("conditions", []),
                )
                task.validate()
                tasks.append(task)
            except (KeyError, ValueError) as e:
                print(f"Warning: Skipping invalid task '{task_data.get('name', 'unknown')}': {e}")

        return tasks

    def _load_json(self) -> dict:
        """Load and parse JSON file

        Returns:
            Parsed JSON data or empty structure if file doesn't exist
        """
        if not self.json_file.exists():
            return {"version": "1.0", "monitors": [], "tasks": []}

        try:
            with open(self.json_file) as f:
                data = json.load(f)

            # Ensure required keys exist
            if "monitors" not in data:
                data["monitors"] = []
            if "tasks" not in data:
                data["tasks"] = []

            return data

        except json.JSONDecodeError as e:
            print(f"Error: Failed to parse {self.json_file}: {e}")
            print("Returning empty schedules")
            return {"version": "1.0", "monitors": [], "tasks": []}
