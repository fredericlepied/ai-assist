"""Schedule recalculation and missed run detection.

This module handles detecting and executing missed scheduled runs
after system suspension or clock changes.
"""

import re
from datetime import datetime, timedelta
from typing import Any


class ScheduleRecalculator:
    """Detects and handles missed scheduled runs after suspension.

    Implements catch-up logic for time-based schedules (e.g., "9:00 daily")
    while allowing interval-based schedules (e.g., "every 30m") to continue
    from current time.
    """

    async def handle_wake_event(
        self,
        wall_jump_seconds: float,
        monitors: list[Any],
        now: datetime | None = None,
    ) -> None:
        """Handle system wake event and execute missed runs.

        Args:
            wall_jump_seconds: How many seconds the wall clock jumped
                (positive for suspension, negative for clock adjustment)
            monitors: List of monitor objects with schedule and execute() method
            now: Current time (defaults to datetime.now() for testing)
        """
        if now is None:
            now = datetime.now()

        # Calculate suspension window
        before_suspend = now - timedelta(seconds=abs(wall_jump_seconds))

        for monitor in monitors:
            # Only handle time-based schedules
            if not self.is_time_based_schedule(monitor.schedule):
                continue

            # Check if this monitor has a missed run
            if await self._has_missed_run(monitor, before_suspend, now):
                # Missed run - execute immediately
                await monitor.execute()

    async def _has_missed_run(
        self,
        monitor: Any,
        before_suspend: datetime,
        now: datetime,
    ) -> bool:
        """Check if monitor has a missed run in suspension window.

        Args:
            monitor: Monitor object with schedule attribute
            before_suspend: Time when suspension started
            now: Current time (after wake)

        Returns:
            True if monitor had a scheduled run during suspension
        """
        # Parse scheduled time from schedule string
        time_tuple = self.parse_time_from_schedule(monitor.schedule)
        if time_tuple is None:
            return False

        hour, minute = time_tuple

        # We need to check if the scheduled time occurred during suspension
        # This could be either:
        # 1. Today (if schedule applies to today)
        # 2. Yesterday (if suspension crossed midnight)

        # Check today's scheduled time
        today_scheduled = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if self._schedule_applies_to_day(monitor.schedule, now):
            if self.was_in_suspension_window(today_scheduled, now, (now - before_suspend).total_seconds()):
                return True

        # Check yesterday's scheduled time (if suspension crossed midnight)
        yesterday = now - timedelta(days=1)
        yesterday_scheduled = yesterday.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if self._schedule_applies_to_day(monitor.schedule, yesterday):
            if before_suspend <= yesterday_scheduled <= now:
                return True

        return False

    def is_time_based_schedule(self, schedule: str) -> bool:
        """Check if schedule is time-based (vs interval-based).

        Args:
            schedule: Schedule string like "9:00 on weekdays" or "every 30m"

        Returns:
            True if time-based, False if interval-based
        """
        # Time-based patterns contain time like "HH:MM"
        time_pattern = r"\d{1,2}:\d{2}"
        return bool(re.search(time_pattern, schedule))

    def parse_time_from_schedule(self, schedule: str) -> tuple[int, int] | None:
        """Parse hour and minute from schedule string.

        Args:
            schedule: Schedule string like "9:00 on weekdays"

        Returns:
            Tuple of (hour, minute) or None if not parseable
        """
        match = re.search(r"(\d{1,2}):(\d{2})", schedule)
        if match:
            hour = int(match.group(1))
            minute = int(match.group(2))
            return (hour, minute)
        return None

    def was_in_suspension_window(
        self,
        scheduled_time: datetime,
        now: datetime,
        wall_jump_seconds: float,
    ) -> bool:
        """Check if scheduled time was during suspension.

        Args:
            scheduled_time: When the schedule should have run
            now: Current time (after wake)
            wall_jump_seconds: How long the suspension was

        Returns:
            True if scheduled_time was during suspension window
        """
        before_suspend = now - timedelta(seconds=abs(wall_jump_seconds))

        # Scheduled time must be:
        # 1. After suspension started
        # 2. Before/at current time (wake time)
        return before_suspend <= scheduled_time <= now

    def _schedule_applies_to_day(self, schedule: str, dt: datetime) -> bool:
        """Check if schedule applies to the given day.

        Args:
            schedule: Schedule string like "9:00 on weekdays"
            dt: Datetime to check

        Returns:
            True if schedule applies to this day
        """
        schedule_lower = schedule.lower()

        # Check for weekend patterns FIRST (more specific)
        if "weekend" in schedule_lower:
            return dt.weekday() >= 5  # Saturday=5, Sunday=6

        # Check for weekday patterns
        if "weekday" in schedule_lower:
            # Monday=0, Sunday=6
            return dt.weekday() < 5

        # Check for specific day names
        day_names = {
            "monday": 0,
            "tuesday": 1,
            "wednesday": 2,
            "thursday": 3,
            "friday": 4,
            "saturday": 5,
            "sunday": 6,
        }

        for day_name, day_num in day_names.items():
            if day_name in schedule_lower:
                return dt.weekday() == day_num

        # If no day restriction, applies to all days (e.g., "9:00 daily")
        return True
