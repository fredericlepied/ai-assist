"""User-defined task definitions and YAML loader"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from datetime import time as dt_time
from pathlib import Path
from typing import Any

import yaml


@dataclass
class TaskDefinition:
    """Definition of a user-defined periodic task"""

    name: str
    prompt: str
    interval: str  # e.g., "5m", "1h", "morning on weekdays", "9:00 on monday,friday"
    description: str | None = None
    enabled: bool = True
    conditions: list[dict] = field(default_factory=list)
    prompt_arguments: dict[str, Any] | None = None
    max_turns: int = 100  # Maximum agentic turns (safety limit, loop detection usually triggers first)

    # Notification configuration
    notify: bool = False
    notification_channels: list[str] = field(default_factory=lambda: ["console"])

    @property
    def interval_seconds(self) -> int:
        """Convert interval string to seconds (for simple intervals)"""
        return TaskLoader.parse_interval(self.interval)

    @property
    def is_time_based(self) -> bool:
        """Check if this is a time-based schedule"""
        return " on " in self.interval.lower()

    @property
    def is_mcp_prompt(self) -> bool:
        """Check if prompt is an MCP prompt reference"""
        return self.prompt.startswith("mcp://")

    def parse_mcp_prompt(self) -> tuple[str, str]:
        """Parse 'mcp://server/prompt' into (server, prompt)

        Raises:
            ValueError: If format is invalid
        """
        if not self.is_mcp_prompt:
            raise ValueError("Not an MCP prompt reference")

        # Remove mcp:// prefix
        ref = self.prompt[6:]

        # Split server/prompt
        if "/" not in ref:
            raise ValueError("MCP prompt must be 'mcp://server/prompt'")

        parts = ref.split("/", 1)
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise ValueError("MCP prompt must be 'mcp://server/prompt'")

        return parts[0], parts[1]

    @classmethod
    def from_dict(cls, task_data: dict[str, Any]) -> "TaskDefinition":
        """Create a TaskDefinition from a dictionary, using defaults for missing optional fields."""
        return cls(
            name=task_data["name"],
            prompt=task_data["prompt"],
            interval=task_data["interval"],
            description=task_data.get("description"),
            enabled=task_data.get("enabled", True),
            conditions=task_data.get("conditions", []),
            prompt_arguments=task_data.get("prompt_arguments"),
            notify=task_data.get("notify", False),
            notification_channels=task_data.get("notification_channels", ["console"]),
        )

    def validate(self):
        """Validate task definition"""
        if not self.name:
            raise ValueError("Task name is required")
        if not self.prompt:
            raise ValueError("Task prompt is required")
        if not self.interval:
            raise ValueError("Task interval is required")

        # Validate MCP prompt format if applicable
        if self.is_mcp_prompt:
            try:
                self.parse_mcp_prompt()
            except ValueError as e:
                raise ValueError(f"Invalid MCP prompt reference: {e}") from e

        # Validate interval format
        try:
            if self.is_time_based:
                TaskLoader.parse_time_schedule(self.interval)
            else:
                # Validate interval_seconds can be computed
                _ = self.interval_seconds
        except ValueError as e:
            raise ValueError(f"Invalid interval '{self.interval}': {e}") from e


class TaskLoader:
    """Load and parse task definitions from YAML"""

    # Time presets
    TIME_PRESETS = {
        "morning": "9:00",
        "afternoon": "14:00",
        "evening": "18:00",
        "night": "22:00",
    }

    # Day groups
    DAY_GROUPS = {
        "weekdays": [0, 1, 2, 3, 4],  # Monday-Friday
        "weekends": [5, 6],  # Saturday-Sunday
    }

    @staticmethod
    def parse_time_schedule(schedule_str: str) -> dict:
        """Parse time-based schedule string

        Formats:
        - "morning on weekdays" -> 9:00 AM Monday-Friday
        - "9:00 on weekdays" -> 9:00 Monday-Friday
        - "14:30 on monday,wednesday,friday" -> 2:30 PM on specific days

        Returns:
            dict with 'time' (datetime.time) and 'days' (list of weekday numbers)
        """
        schedule_str = schedule_str.strip().lower()

        if " on " not in schedule_str:
            raise ValueError(
                f"Time-based schedule must include 'on': '{schedule_str}'. "
                "Examples: 'morning on weekdays', '9:00 on monday,friday'"
            )

        time_part, days_part = schedule_str.split(" on ", 1)
        time_part = time_part.strip()
        days_part = days_part.strip()

        # Parse time
        if time_part in TaskLoader.TIME_PRESETS:
            time_str = TaskLoader.TIME_PRESETS[time_part]
        else:
            time_str = time_part

        # Parse time string (HH:MM format)
        try:
            hour, minute = map(int, time_str.split(":"))
            if not (0 <= hour < 24 and 0 <= minute < 60):
                raise ValueError("Time out of range")
            schedule_time = dt_time(hour, minute)
        except (ValueError, AttributeError) as e:
            raise ValueError(
                f"Invalid time format: '{time_part}'. "
                "Use HH:MM (24-hour) or presets: morning, afternoon, evening, night"
            ) from e

        # Parse days
        if days_part in TaskLoader.DAY_GROUPS:
            days = TaskLoader.DAY_GROUPS[days_part]
        else:
            # Parse individual days
            day_names = {
                "monday": 0,
                "mon": 0,
                "tuesday": 1,
                "tue": 1,
                "wednesday": 2,
                "wed": 2,
                "thursday": 3,
                "thu": 3,
                "friday": 4,
                "fri": 4,
                "saturday": 5,
                "sat": 5,
                "sunday": 6,
                "sun": 6,
            }

            day_parts = [d.strip() for d in days_part.split(",")]
            days = []
            for day in day_parts:
                if day in day_names:
                    days.append(day_names[day])
                else:
                    raise ValueError(
                        f"Invalid day: '{day}'. " "Use day names (monday, tuesday, etc.) or groups (weekdays, weekends)"
                    )

            if not days:
                raise ValueError("At least one day must be specified")

        return {"time": schedule_time, "days": sorted(set(days))}

    @staticmethod
    def calculate_next_run(schedule: dict, from_time: datetime | None = None) -> datetime:
        """Calculate next run time for a time-based schedule

        Args:
            schedule: Dict with 'time' and 'days'
            from_time: Calculate from this time (default: now)

        Returns:
            Next datetime when task should run
        """
        if from_time is None:
            from_time = datetime.now()

        schedule_time = schedule["time"]
        allowed_days = set(schedule["days"])

        # Start from the same day at the scheduled time
        next_run = datetime.combine(from_time.date(), schedule_time)

        # If time has passed today, start from tomorrow
        if next_run <= from_time:
            next_run += timedelta(days=1)

        # Find next allowed day
        max_attempts = 7  # Don't loop forever
        attempts = 0
        while next_run.weekday() not in allowed_days and attempts < max_attempts:
            next_run += timedelta(days=1)
            attempts += 1

        if attempts >= max_attempts:
            raise ValueError(f"Could not find next run time for schedule: {schedule}")

        return next_run

    @staticmethod
    def parse_interval(interval_str: str) -> int:
        """Convert interval string to seconds

        Supported formats:
        - "30s" -> 30 seconds
        - "5m" -> 300 seconds
        - "1h" -> 3600 seconds
        - "2h30m" -> 9000 seconds
        """
        if not interval_str:
            raise ValueError("Interval cannot be empty")

        interval_str = interval_str.strip().lower()
        total_seconds = 0

        # Parse hours
        hours_match = re.search(r"(\d+)h", interval_str)
        if hours_match:
            total_seconds += int(hours_match.group(1)) * 3600

        # Parse minutes
        minutes_match = re.search(r"(\d+)m", interval_str)
        if minutes_match:
            total_seconds += int(minutes_match.group(1)) * 60

        # Parse seconds
        seconds_match = re.search(r"(\d+)s", interval_str)
        if seconds_match:
            total_seconds += int(seconds_match.group(1))

        if total_seconds == 0:
            raise ValueError(
                f"Invalid interval format: '{interval_str}'. " "Use formats like '30s', '5m', '1h', or '2h30m'"
            )

        return total_seconds

    def load_from_yaml(self, path: Path) -> list[TaskDefinition]:
        """Load task definitions from YAML file"""
        if not path.exists():
            return []

        try:
            with open(path) as f:
                data = yaml.safe_load(f)

            if not data or "tasks" not in data:
                return []

            tasks = []
            for task_data in data["tasks"]:
                task = TaskDefinition.from_dict(task_data)
                task.validate()
                tasks.append(task)

            return tasks

        except yaml.YAMLError as e:
            raise ValueError(f"YAML parsing error: {e}") from e
        except KeyError as e:
            raise ValueError(f"Missing required field in task definition: {e}") from e

    def load_from_yaml_string(self, yaml_content: str) -> list[TaskDefinition]:
        """Load task definitions from YAML string (for testing)"""
        try:
            data = yaml.safe_load(yaml_content)

            if not data or "tasks" not in data:
                return []

            tasks = []
            for task_data in data["tasks"]:
                task = TaskDefinition.from_dict(task_data)
                task.validate()
                tasks.append(task)

            return tasks

        except yaml.YAMLError as e:
            raise ValueError(f"YAML parsing error: {e}") from e
        except KeyError as e:
            raise ValueError(f"Missing required field in task definition: {e}") from e
