"""Integration tests for monitor suspension recovery."""

import asyncio
import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_assist.agent import AiAssistAgent
from ai_assist.monitors import MonitoringScheduler
from ai_assist.state import StateManager


@pytest.fixture
def mock_agent():
    """Create a mock agent for testing."""
    agent = MagicMock(spec=AiAssistAgent)
    agent.send_message = AsyncMock(return_value="Mock response")
    return agent


@pytest.fixture
def temp_schedule_file():
    """Create a temporary schedule file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        schedule = {
            "monitors": [
                {"name": "test_time_based", "enabled": True, "prompt": "Test query", "interval": "9:00 on weekdays"}
            ],
            "tasks": [],
        }
        json.dump(schedule, f)
        f.flush()
        yield Path(f.name)

    Path(f.name).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_suspension_triggers_missed_run(mock_agent, temp_schedule_file):
    """Test that suspension triggers execution of missed time-based schedule."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_manager = StateManager(Path(tmpdir))
        config = MagicMock()

        scheduler = MonitoringScheduler(
            agent=mock_agent, config=config, state_manager=state_manager, schedule_file=temp_schedule_file
        )

        # Verify monitor was loaded
        assert len(scheduler.monitors) == 1
        monitor = scheduler.monitors[0]

        # Mock the monitor's run method to track execution
        original_run = monitor.run
        monitor.run = AsyncMock(wraps=original_run)

        # Simulate wake event: Friday 10 AM, suspended for 2 hours
        # Scheduled time 9 AM was missed
        now = datetime(2026, 2, 6, 10, 0, 0)  # Friday Feb 6, 10:00 AM
        wall_jump_seconds = 2 * 3600  # 2 hour suspension

        await scheduler._handle_wake_event(wall_jump_seconds, now=now)

        # Monitor should have been executed for missed run
        monitor.run.assert_called_once()


@pytest.mark.asyncio
async def test_no_missed_run_if_not_in_window(mock_agent, temp_schedule_file):
    """Test that no execution happens if scheduled time not in suspension window."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_manager = StateManager(Path(tmpdir))
        config = MagicMock()

        scheduler = MonitoringScheduler(
            agent=mock_agent, config=config, state_manager=state_manager, schedule_file=temp_schedule_file
        )

        monitor = scheduler.monitors[0]
        monitor.run = AsyncMock()

        # Mock user tasks too (kg-synthesis default task)
        for task in scheduler.user_tasks:
            task.run = AsyncMock()

        # Simulate wake event: Friday 8 AM, suspended for 1 hour
        # Scheduled time 9 AM was NOT missed (still in future)
        now = datetime(2026, 2, 6, 8, 0, 0)  # Friday Feb 6, 8:00 AM
        wall_jump_seconds = 1 * 3600  # 1 hour suspension

        await scheduler._handle_wake_event(wall_jump_seconds, now=now)

        # Monitor should NOT have been executed
        monitor.run.assert_not_called()


@pytest.mark.asyncio
async def test_cache_ttl_with_monotonic_time():
    """Test that cache TTL works correctly with monotonic time."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_manager = StateManager(Path(tmpdir))

        # Mock time for both caching and retrieval
        with patch("ai_assist.state.time") as mock_time:
            # Initial time when caching
            mock_time.monotonic.return_value = 1000.0

            # Cache a result
            state_manager.cache_query_result("test_key", {"data": "value"}, ttl_seconds=10)

            # Immediately retrieve - should be cached (0 seconds elapsed)
            result = state_manager.get_cached_query("test_key")
            assert result == {"data": "value"}

            # Simulate time passing: monotonic time advanced 15 seconds (beyond 10s TTL)
            mock_time.monotonic.return_value = 1000.0 + 15.0

            result = state_manager.get_cached_query("test_key")
            # Should be expired
            assert result is None


@pytest.mark.asyncio
async def test_cache_backward_compatibility():
    """Test that old cache entries (without cached_at_mono) still work."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_manager = StateManager(Path(tmpdir))

        # Manually create old-format cache entry
        cache_file = state_manager.cache_dir / "test_key.json"
        old_cache = {
            "result": {"data": "old_value"},
            "timestamp": datetime.now().isoformat(),
            "ttl_seconds": 300,
            # Note: no "cached_at_mono" field
        }
        with open(cache_file, "w") as f:
            json.dump(old_cache, f)

        # Should still be retrievable
        result = state_manager.get_cached_query("test_key")
        assert result == {"data": "old_value"}


@pytest.mark.asyncio
async def test_suspend_detector_integration(mock_agent):
    """Test that suspend detector is initialized and running."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_manager = StateManager(Path(tmpdir))
        config = MagicMock()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            schedule = {"monitors": [], "tasks": []}
            json.dump(schedule, f)
            f.flush()
            schedule_file = Path(f.name)

        try:
            scheduler = MonitoringScheduler(
                agent=mock_agent, config=config, state_manager=state_manager, schedule_file=schedule_file
            )

            # Start scheduler in background
            start_task = asyncio.create_task(scheduler.start())

            # Give it time to initialize
            await asyncio.sleep(0.2)

            # Verify suspend detector was created
            assert scheduler.suspend_detector is not None
            assert scheduler.suspend_detector.suspend_threshold_seconds == 30.0

            # Stop scheduler
            await scheduler.stop()
            start_task.cancel()
            try:
                await start_task
            except asyncio.CancelledError:
                pass

        finally:
            schedule_file.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_file_watchdog_integration(mock_agent, temp_schedule_file):
    """Test that file watchdog is initialized and watching."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_manager = StateManager(Path(tmpdir))
        config = MagicMock()

        scheduler = MonitoringScheduler(
            agent=mock_agent, config=config, state_manager=state_manager, schedule_file=temp_schedule_file
        )

        # Start scheduler in background
        start_task = asyncio.create_task(scheduler.start())

        # Give it time to initialize
        await asyncio.sleep(0.2)

        # Verify file watchdog was created
        assert scheduler.file_watchdog is not None
        assert scheduler.file_watchdog.file_path == temp_schedule_file

        # Stop scheduler
        await scheduler.stop()
        start_task.cancel()
        try:
            await start_task
        except asyncio.CancelledError:
            pass
