"""Tests for hot reload functionality"""

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from ai_assist.monitors import MonitoringScheduler
from ai_assist.state import StateManager


@pytest.fixture
def temp_schedules_file():
    """Create temporary schedules file"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "schedules.json"


@pytest.fixture
def mock_agent():
    """Create mock agent"""
    agent = MagicMock()
    agent.query = AsyncMock(return_value="Test result")
    return agent


@pytest.fixture
def state_manager(tmp_path):
    """Create state manager"""
    return StateManager(state_dir=tmp_path / "state")


class TestHotReload:
    """Tests for hot reload functionality"""

    @pytest.mark.asyncio
    async def test_task_cancellation_handled_gracefully(self, mock_agent, state_manager, temp_schedules_file):
        """Test that task cancellation during reload doesn't crash"""
        # Create initial schedule
        temp_schedules_file.write_text(
            json.dumps(
                {
                    "version": "1.0",
                    "monitors": [],
                    "tasks": [{"name": "Test Task", "prompt": "Test prompt", "interval": "1h", "enabled": True}],
                }
            )
        )

        config = MagicMock()
        scheduler = MonitoringScheduler(mock_agent, config, state_manager, None, schedule_file=temp_schedules_file)

        # Start a task
        task = asyncio.create_task(scheduler._schedule_task("Test", mock_agent.query, 3600))

        # Let it start
        await asyncio.sleep(0.1)

        # Cancel the task (simulates what reload does)
        task.cancel()

        # Should not raise CancelledError
        try:
            await task
        except asyncio.CancelledError:
            pytest.fail("CancelledError not caught - task should handle gracefully")

        # If we get here, cancellation was handled properly
        assert True

    @pytest.mark.asyncio
    async def test_time_based_task_cancellation(self, mock_agent, state_manager, temp_schedules_file):
        """Test that time-based task cancellation is handled"""
        from ai_assist.tasks import TaskDefinition

        temp_schedules_file.write_text(
            json.dumps(
                {
                    "version": "1.0",
                    "monitors": [],
                    "tasks": [
                        {"name": "Morning Task", "prompt": "Test", "interval": "morning on weekdays", "enabled": True}
                    ],
                }
            )
        )

        config = MagicMock()
        scheduler = MonitoringScheduler(mock_agent, config, state_manager, None, schedule_file=temp_schedules_file)

        # Create a time-based task definition
        task_def = TaskDefinition(name="Morning Task", prompt="Test", interval="morning on weekdays")

        # Start the task
        task = asyncio.create_task(scheduler._schedule_task("Morning Task", mock_agent.query, 0, task_def=task_def))

        # Let it start
        await asyncio.sleep(0.1)

        # Cancel during the sleep
        task.cancel()

        # Should not raise CancelledError
        try:
            await task
        except asyncio.CancelledError:
            pytest.fail("CancelledError not caught in time-based task")

        assert True

    @pytest.mark.asyncio
    async def test_reload_schedules_cancels_tasks(self, mock_agent, state_manager, temp_schedules_file):
        """Test that reload properly cancels and restarts tasks"""
        # Create initial schedule
        temp_schedules_file.write_text(
            json.dumps(
                {
                    "version": "1.0",
                    "monitors": [],
                    "tasks": [{"name": "Task 1", "prompt": "Test 1", "interval": "1h", "enabled": True}],
                }
            )
        )

        config = MagicMock()
        scheduler = MonitoringScheduler(mock_agent, config, state_manager, None, schedule_file=temp_schedules_file)

        # Verify initial task loaded (+ built-in nightly-synthesis)
        task_names = {t.task_def.name for t in scheduler.user_tasks}
        assert "Task 1" in task_names
        assert "nightly-synthesis" in task_names

        # Simulate reload with new schedule
        temp_schedules_file.write_text(
            json.dumps(
                {
                    "version": "1.0",
                    "monitors": [],
                    "tasks": [{"name": "Task 2", "prompt": "Test 2", "interval": "2h", "enabled": True}],
                }
            )
        )

        # Reload should not crash
        await scheduler.reload_schedules()

        # Verify new task loaded (+ built-in nightly-synthesis)
        task_names = {t.task_def.name for t in scheduler.user_tasks}
        assert "Task 2" in task_names
        assert "Task 1" not in task_names
        assert "nightly-synthesis" in task_names
