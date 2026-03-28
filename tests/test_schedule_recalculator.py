"""Tests for schedule recalculation and missed run detection."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from ai_assist.schedule_recalculator import ScheduleRecalculator


@pytest.mark.asyncio
async def test_time_based_missed_run_detected():
    """Test that missed time-based runs are detected after suspension."""
    recalculator = ScheduleRecalculator()

    monitor = MagicMock()
    monitor.schedule = "9:00 on weekdays"
    monitor.execute = AsyncMock()

    # It's 10:00 AM Friday; system suspended for 2 hours (8:00–10:00)
    # Scheduled run at 9:00 AM was missed
    now = datetime(2026, 2, 6, 10, 0, 0)  # Friday
    await recalculator.handle_wake_event(2 * 3600, [monitor], now)

    monitor.execute.assert_called_once()


@pytest.mark.asyncio
async def test_time_based_no_missed_run():
    """Test that no execution happens if scheduled time not in suspension window."""
    recalculator = ScheduleRecalculator()

    monitor = MagicMock()
    monitor.schedule = "9:00 on weekdays"
    monitor.execute = AsyncMock()

    # It's 8:00 AM Friday; system suspended for 1 hour (7:00–8:00)
    # Scheduled run at 9:00 AM was NOT missed (still in future)
    now = datetime(2026, 2, 6, 8, 0, 0)  # Friday
    await recalculator.handle_wake_event(1 * 3600, [monitor], now)

    monitor.execute.assert_not_called()


@pytest.mark.asyncio
async def test_interval_based_skipped():
    """Test that interval-based schedules are not caught up after suspension."""
    recalculator = ScheduleRecalculator()

    monitor = MagicMock()
    monitor.schedule = "every 30m"
    monitor.execute = AsyncMock()

    now = datetime(2026, 2, 6, 10, 0, 0)
    await recalculator.handle_wake_event(2 * 3600, [monitor], now)

    monitor.execute.assert_not_called()


@pytest.mark.asyncio
async def test_multiple_monitors_mixed_types():
    """Test handling multiple monitors with different schedule types."""
    recalculator = ScheduleRecalculator()

    # Time-based that was missed
    monitor1 = MagicMock()
    monitor1.schedule = "9:00 on weekdays"
    monitor1.execute = AsyncMock()

    # Time-based that was NOT missed
    monitor2 = MagicMock()
    monitor2.schedule = "11:00 on weekdays"
    monitor2.execute = AsyncMock()

    # Interval-based
    monitor3 = MagicMock()
    monitor3.schedule = "every 30m"
    monitor3.execute = AsyncMock()

    # It's 10:00 AM Friday; suspended 8:00–10:00
    now = datetime(2026, 2, 6, 10, 0, 0)
    await recalculator.handle_wake_event(2 * 3600, [monitor1, monitor2, monitor3], now)

    monitor1.execute.assert_called_once()
    monitor2.execute.assert_not_called()
    monitor3.execute.assert_not_called()


@pytest.mark.asyncio
async def test_weekend_schedule_not_triggered_on_friday():
    """Test that weekend schedules don't trigger on weekdays."""
    recalculator = ScheduleRecalculator()

    monitor = MagicMock()
    monitor.schedule = "9:00 on weekends"
    monitor.execute = AsyncMock()

    now = datetime(2026, 2, 6, 10, 0, 0)  # Friday
    await recalculator.handle_wake_event(2 * 3600, [monitor], now)

    monitor.execute.assert_not_called()


@pytest.mark.asyncio
async def test_short_suspension_no_missed_runs():
    """Test that short suspensions don't trigger false positives."""
    recalculator = ScheduleRecalculator()

    monitor = MagicMock()
    monitor.schedule = "9:00 on weekdays"
    monitor.execute = AsyncMock()

    # 10:00 AM, 5-minute suspension — 9:00 AM was not in the window
    now = datetime(2026, 2, 6, 10, 0, 0)
    await recalculator.handle_wake_event(5 * 60, [monitor], now)

    monitor.execute.assert_not_called()


@pytest.mark.asyncio
async def test_multi_day_schedule_triggered_on_any_listed_day():
    """Regression: schedules listing multiple days must fire on all of them."""
    recalculator = ScheduleRecalculator()

    monitor = MagicMock()
    monitor.schedule = "8:00 on monday,tuesday,wednesday,thursday,friday,saturday,sunday"
    monitor.execute = AsyncMock()

    # Saturday March 28 2026: slept at 7:30 AM, woke at 10:00 AM — 8:00 AM missed
    now = datetime(2026, 3, 28, 10, 0, 0)
    await recalculator.handle_wake_event(int(2.5 * 3600), [monitor], now)

    monitor.execute.assert_called_once()


@pytest.mark.asyncio
async def test_night_preset_schedule_caught_after_suspend():
    """Regression: 'night on weekdays' preset (22:00) must be caught after suspension."""
    recalculator = ScheduleRecalculator()

    monitor = MagicMock()
    monitor.schedule = "night on weekdays"  # resolves to 22:00
    monitor.execute = AsyncMock()

    # Friday 23:00, suspended for 2 hours through 22:00
    now = datetime(2026, 2, 6, 23, 0, 0)
    await recalculator.handle_wake_event(2 * 3600, [monitor], now)

    monitor.execute.assert_called_once()
