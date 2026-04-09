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
    agent.config = MagicMock()
    agent.config.mcp_servers = {}
    agent.sessions = {}
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
        monitor.run = AsyncMock(return_value=MagicMock(success=True, output="ok"))
        # Mock user tasks too (kg-synthesis is auto-injected)
        for task in scheduler.user_tasks:
            task.run = AsyncMock(return_value=MagicMock(success=True, output="ok"))
        scheduler._wait_for_network = AsyncMock(return_value=True)

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
        scheduler._wait_for_network = AsyncMock(return_value=True)

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


@pytest.fixture
def schedule_file_with_daily_task():
    """Schedule file with a daily 8:00 task on all days."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        schedule = {
            "monitors": [],
            "tasks": [
                {
                    "name": "morning_briefing",
                    "prompt": "Morning briefing",
                    "interval": "8:00 on monday,tuesday,wednesday,thursday,friday,saturday,sunday",
                    "enabled": True,
                }
            ],
        }
        json.dump(schedule, f)
        f.flush()
        yield Path(f.name)

    Path(f.name).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_startup_catchup_runs_missed_task(mock_agent, schedule_file_with_daily_task):
    """Test that startup catchup runs a task missed since last 24h (reboot scenario)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_manager = StateManager(Path(tmpdir))
        config = MagicMock()

        scheduler = MonitoringScheduler(
            agent=mock_agent, config=config, state_manager=state_manager, schedule_file=schedule_file_with_daily_task
        )
        scheduler._wait_for_network = AsyncMock(return_value=True)

        task_runner = scheduler.user_tasks[0]
        task_runner.run = AsyncMock(return_value=MagicMock(success=True, output="ok"))

        # Simulate: it's 09:00, task scheduled at 08:00 hasn't run today
        now = datetime(2026, 3, 30, 9, 0, 0)  # Monday 09:00, task due at 08:00
        await scheduler._run_missed_tasks_at_startup(now=now)

        task_runner.run.assert_called_once()


@pytest.mark.asyncio
async def test_startup_catchup_skips_successfully_run_task(mock_agent, schedule_file_with_daily_task):
    """Test that startup catchup skips tasks that already succeeded since their scheduled time."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_manager = StateManager(Path(tmpdir))
        config = MagicMock()

        scheduler = MonitoringScheduler(
            agent=mock_agent, config=config, state_manager=state_manager, schedule_file=schedule_file_with_daily_task
        )
        scheduler._wait_for_network = AsyncMock(return_value=True)

        task_runner = scheduler.user_tasks[0]
        task_runner.run = AsyncMock(return_value=MagicMock(success=True, output="ok"))

        # Simulate: task ran successfully at 08:05 today, service restarts at 09:00
        now = datetime(2026, 3, 30, 9, 0, 0)
        state = state_manager.get_monitor_state(task_runner.state_key)
        state.last_check = datetime(2026, 3, 30, 8, 5, 0)
        state.last_results = {"task_name": "morning_briefing", "last_success": True}

        await scheduler._run_missed_tasks_at_startup(now=now)

        task_runner.run.assert_not_called()


@pytest.mark.asyncio
async def test_startup_catchup_retries_failed_run(mock_agent, schedule_file_with_daily_task):
    """Test that startup catchup retries tasks that failed (e.g. no network after suspend)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_manager = StateManager(Path(tmpdir))
        config = MagicMock()

        scheduler = MonitoringScheduler(
            agent=mock_agent, config=config, state_manager=state_manager, schedule_file=schedule_file_with_daily_task
        )
        scheduler._wait_for_network = AsyncMock(return_value=True)

        task_runner = scheduler.user_tasks[0]
        task_runner.run = AsyncMock(return_value=MagicMock(success=True, output="ok"))

        # Simulate: suspend recovery ran the task at 08:45 but it failed (no network)
        now = datetime(2026, 3, 30, 9, 0, 0)
        state = state_manager.get_monitor_state(task_runner.state_key)
        state.last_check = datetime(2026, 3, 30, 8, 45, 0)
        state.last_results = {"task_name": "morning_briefing", "last_success": False, "last_error": "DNS failure"}

        await scheduler._run_missed_tasks_at_startup(now=now)

        task_runner.run.assert_called_once()


@pytest.mark.asyncio
async def test_startup_catchup_skips_task_that_ran_yesterday(mock_agent, schedule_file_with_daily_task):
    """Test that startup catchup skips today's task if it ran at yesterday's scheduled time."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_manager = StateManager(Path(tmpdir))
        config = MagicMock()

        scheduler = MonitoringScheduler(
            agent=mock_agent, config=config, state_manager=state_manager, schedule_file=schedule_file_with_daily_task
        )
        scheduler._wait_for_network = AsyncMock(return_value=True)

        task_runner = scheduler.user_tasks[0]
        task_runner.run = AsyncMock(return_value=MagicMock(success=True, output="ok"))

        # Simulate: it's 07:00 today, task ran yesterday at 08:05 (so no missed run)
        now = datetime(2026, 3, 30, 7, 0, 0)
        state = state_manager.get_monitor_state(task_runner.state_key)
        state.last_check = datetime(2026, 3, 29, 8, 5, 0)  # ran yesterday at 08:05

        await scheduler._run_missed_tasks_at_startup(now=now)

        task_runner.run.assert_not_called()


@pytest.mark.asyncio
async def test_startup_catchup_skips_when_network_unavailable(mock_agent, schedule_file_with_daily_task):
    """Test that startup catchup is skipped when network is not available."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_manager = StateManager(Path(tmpdir))
        config = MagicMock()

        scheduler = MonitoringScheduler(
            agent=mock_agent, config=config, state_manager=state_manager, schedule_file=schedule_file_with_daily_task
        )
        scheduler._wait_for_network = AsyncMock(return_value=False)

        task_runner = scheduler.user_tasks[0]
        task_runner.run = AsyncMock(return_value=MagicMock(success=True, output="ok"))

        now = datetime(2026, 3, 30, 9, 0, 0)
        await scheduler._run_missed_tasks_at_startup(now=now)

        task_runner.run.assert_not_called()


@pytest.mark.asyncio
async def test_suspend_recovery_waits_for_network(mock_agent, temp_schedule_file):
    """Test that suspend recovery waits for network before running missed tasks."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_manager = StateManager(Path(tmpdir))
        config = MagicMock()

        scheduler = MonitoringScheduler(
            agent=mock_agent, config=config, state_manager=state_manager, schedule_file=temp_schedule_file
        )
        scheduler._wait_for_network = AsyncMock(return_value=True)

        monitor = scheduler.monitors[0]
        monitor.run = AsyncMock(return_value=MagicMock(success=True, output="ok"))
        for task in scheduler.user_tasks:
            task.run = AsyncMock(return_value=MagicMock(success=True, output="ok"))

        now = datetime(2026, 2, 6, 10, 0, 0)
        await scheduler._handle_wake_event(2 * 3600, now=now)

        scheduler._wait_for_network.assert_called_once()
        monitor.run.assert_called_once()


@pytest.mark.asyncio
async def test_suspend_recovery_skips_tasks_when_network_unavailable(mock_agent, temp_schedule_file):
    """Test that suspend recovery skips missed tasks when network never comes up."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_manager = StateManager(Path(tmpdir))
        config = MagicMock()

        scheduler = MonitoringScheduler(
            agent=mock_agent, config=config, state_manager=state_manager, schedule_file=temp_schedule_file
        )
        scheduler._wait_for_network = AsyncMock(return_value=False)

        monitor = scheduler.monitors[0]
        monitor.run = AsyncMock()
        for task in scheduler.user_tasks:
            task.run = AsyncMock()

        now = datetime(2026, 2, 6, 10, 0, 0)
        await scheduler._handle_wake_event(2 * 3600, now=now)

        monitor.run.assert_not_called()


@pytest.mark.asyncio
async def test_suspend_recovery_continues_after_task_exception(mock_agent, temp_schedule_file):
    """Test that suspend recovery runs all tasks even if one raises an exception."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_manager = StateManager(Path(tmpdir))
        config = MagicMock()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            schedule = {
                "monitors": [
                    {"name": "task_a", "enabled": True, "prompt": "A", "interval": "9:00 on weekdays"},
                    {"name": "task_b", "enabled": True, "prompt": "B", "interval": "9:00 on weekdays"},
                ],
                "tasks": [],
            }
            json.dump(schedule, f)
            f.flush()
            schedule_file = Path(f.name)

        try:
            scheduler = MonitoringScheduler(
                agent=mock_agent, config=config, state_manager=state_manager, schedule_file=schedule_file
            )

            assert len(scheduler.monitors) == 2
            scheduler.monitors[0].run = AsyncMock(side_effect=RuntimeError("task_a failed"))
            scheduler.monitors[1].run = AsyncMock(return_value=MagicMock(success=True, output="ok"))
            for task in scheduler.user_tasks:
                task.run = AsyncMock(return_value=MagicMock(success=True, output="ok"))
            scheduler._wait_for_network = AsyncMock(return_value=True)

            # Friday 10:00, suspended for 2h — both tasks missed at 09:00
            now = datetime(2026, 2, 6, 10, 0, 0)
            await scheduler._handle_wake_event(2 * 3600, now=now)

            # task_b should still have run despite task_a failing
            scheduler.monitors[1].run.assert_called_once()
        finally:
            schedule_file.unlink(missing_ok=True)
