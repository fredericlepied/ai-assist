"""Tests for schedule recalculation and missed run detection."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from ai_assist.schedule_recalculator import ScheduleRecalculator


@pytest.mark.asyncio
async def test_time_based_missed_run_detected():
    """Test that missed time-based runs are detected after suspension."""
    recalculator = ScheduleRecalculator()

    # Create mock monitor with time-based schedule (9:00 AM daily)
    monitor = MagicMock()
    monitor.schedule = "9:00 on weekdays"
    monitor.is_time_based = True
    monitor.execute = AsyncMock()

    # Simulate: it's now 10:00 AM, system was suspended for 2 hours
    # System went to sleep at 8:00 AM, woke at 10:00 AM
    # Scheduled run at 9:00 AM was missed
    now = datetime(2026, 2, 6, 10, 0, 0)  # Friday Feb 6, 10:00 AM
    wall_jump_seconds = 2 * 3600  # 2 hour suspension

    monitors = [monitor]

    await recalculator.handle_wake_event(wall_jump_seconds, monitors, now)

    # Should have executed the missed run
    monitor.execute.assert_called_once()


@pytest.mark.asyncio
async def test_time_based_no_missed_run():
    """Test that no execution happens if scheduled time not in suspension window."""
    recalculator = ScheduleRecalculator()

    monitor = MagicMock()
    monitor.schedule = "9:00 on weekdays"
    monitor.is_time_based = True
    monitor.execute = AsyncMock()

    # Simulate: it's now 8:00 AM, system was suspended for 1 hour
    # System went to sleep at 7:00 AM, woke at 8:00 AM
    # Scheduled run at 9:00 AM was NOT missed (still in future)
    now = datetime(2026, 2, 6, 8, 0, 0)  # Friday Feb 6, 8:00 AM
    wall_jump_seconds = 1 * 3600  # 1 hour suspension

    monitors = [monitor]

    await recalculator.handle_wake_event(wall_jump_seconds, monitors, now)

    # Should NOT have executed
    monitor.execute.assert_not_called()


@pytest.mark.asyncio
async def test_interval_based_continues_from_now():
    """Test that interval-based schedules continue from wake time."""
    recalculator = ScheduleRecalculator()

    monitor = MagicMock()
    monitor.schedule = "every 30m"
    monitor.is_time_based = False
    monitor.execute = AsyncMock()

    now = datetime(2026, 2, 6, 10, 0, 0)  # Friday Feb 6
    wall_jump_seconds = 2 * 3600  # 2 hour suspension

    monitors = [monitor]

    await recalculator.handle_wake_event(wall_jump_seconds, monitors, now)

    # Should NOT execute (interval-based don't catch up)
    monitor.execute.assert_not_called()


@pytest.mark.asyncio
async def test_multiple_monitors_mixed_types():
    """Test handling multiple monitors with different schedule types."""
    recalculator = ScheduleRecalculator()

    # Time-based that was missed
    monitor1 = MagicMock()
    monitor1.schedule = "9:00 on weekdays"
    monitor1.is_time_based = True
    monitor1.execute = AsyncMock()

    # Time-based that was NOT missed
    monitor2 = MagicMock()
    monitor2.schedule = "11:00 on weekdays"
    monitor2.is_time_based = True
    monitor2.execute = AsyncMock()

    # Interval-based
    monitor3 = MagicMock()
    monitor3.schedule = "every 30m"
    monitor3.is_time_based = False
    monitor3.execute = AsyncMock()

    # It's now 10:00 AM, suspended for 2 hours (8:00 AM -> 10:00 AM)
    # monitor1 (9:00) was missed
    # monitor2 (11:00) was not missed
    # monitor3 (interval) doesn't catch up
    now = datetime(2026, 2, 6, 10, 0, 0)  # Friday Feb 6, 10:00 AM
    wall_jump_seconds = 2 * 3600

    monitors = [monitor1, monitor2, monitor3]

    await recalculator.handle_wake_event(wall_jump_seconds, monitors, now)

    # Only monitor1 should have executed
    monitor1.execute.assert_called_once()
    monitor2.execute.assert_not_called()
    monitor3.execute.assert_not_called()


@pytest.mark.asyncio
async def test_weekend_schedule_not_triggered_on_friday():
    """Test that weekend schedules don't trigger on weekdays."""
    recalculator = ScheduleRecalculator()

    monitor = MagicMock()
    monitor.schedule = "9:00 on weekends"
    monitor.is_time_based = True
    monitor.execute = AsyncMock()

    # Friday 10:00 AM, suspended through 9:00 AM
    now = datetime(2026, 2, 6, 10, 0, 0)  # Friday Feb 6
    wall_jump_seconds = 2 * 3600

    monitors = [monitor]

    await recalculator.handle_wake_event(wall_jump_seconds, monitors, now)

    # Should NOT execute (not a weekend)
    monitor.execute.assert_not_called()


@pytest.mark.asyncio
async def test_short_suspension_no_missed_runs():
    """Test that short suspensions don't trigger false positives."""
    recalculator = ScheduleRecalculator()

    monitor = MagicMock()
    monitor.schedule = "9:00 on weekdays"
    monitor.is_time_based = True
    monitor.execute = AsyncMock()

    # 10:00 AM, very short suspension (5 minutes)
    now = datetime(2026, 2, 6, 10, 0, 0)  # Friday Feb 6
    wall_jump_seconds = 5 * 60  # 5 minutes

    monitors = [monitor]

    await recalculator.handle_wake_event(wall_jump_seconds, monitors, now)

    # Should NOT execute (9:00 AM not in suspension window)
    monitor.execute.assert_not_called()


def test_is_time_based_schedule_detection():
    """Test detection of time-based vs interval-based schedules."""
    recalculator = ScheduleRecalculator()

    # Time-based patterns
    assert recalculator.is_time_based_schedule("9:00 on weekdays")
    assert recalculator.is_time_based_schedule("14:30 daily")
    assert recalculator.is_time_based_schedule("8:00 on monday")
    assert recalculator.is_time_based_schedule("10:00 on weekends")

    # Interval-based patterns
    assert not recalculator.is_time_based_schedule("every 30m")
    assert not recalculator.is_time_based_schedule("every 2h")
    assert not recalculator.is_time_based_schedule("every 1d")


def test_parse_time_from_schedule():
    """Test parsing time from time-based schedules."""
    recalculator = ScheduleRecalculator()

    assert recalculator.parse_time_from_schedule("9:00 on weekdays") == (9, 0)
    assert recalculator.parse_time_from_schedule("14:30 daily") == (14, 30)
    assert recalculator.parse_time_from_schedule("8:15 on monday") == (8, 15)
    assert recalculator.parse_time_from_schedule("23:45 on weekends") == (23, 45)

    # Invalid schedules
    assert recalculator.parse_time_from_schedule("every 30m") is None
    assert recalculator.parse_time_from_schedule("invalid") is None


def test_was_in_suspension_window():
    """Test checking if time was in suspension window."""
    recalculator = ScheduleRecalculator()

    now = datetime(2026, 2, 6, 10, 0, 0)  # Friday Feb 6, 10:00 AM
    wall_jump_seconds = 2 * 3600  # 2 hour suspension (8:00 AM -> 10:00 AM)

    # Time at 9:00 AM (during suspension)
    scheduled_time = datetime(2026, 2, 6, 9, 0, 0)
    assert recalculator.was_in_suspension_window(scheduled_time, now, wall_jump_seconds)

    # Time at 7:00 AM (before suspension)
    scheduled_time = datetime(2026, 2, 6, 7, 0, 0)
    assert not recalculator.was_in_suspension_window(scheduled_time, now, wall_jump_seconds)

    # Time at 11:00 AM (after wake)
    scheduled_time = datetime(2026, 2, 6, 11, 0, 0)
    assert not recalculator.was_in_suspension_window(scheduled_time, now, wall_jump_seconds)
