"""Tests for scheduled action executor (non-polling, event-driven)"""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from ai_assist.scheduled_actions import ScheduledAction, ScheduledActionManager


@pytest.mark.asyncio
async def test_calculate_next_execution_time(tmp_path):
    """Test calculating when to wake up next"""
    action_file = tmp_path / "scheduled-actions.json"
    mock_agent = MagicMock()

    manager = ScheduledActionManager(action_file, mock_agent)

    # No pending actions
    next_time = manager._calculate_next_execution_time()
    assert next_time is None

    # One action in 2 hours
    action1 = ScheduledAction(
        id="test-1",
        prompt="Action 1",
        scheduled_at=datetime.now() + timedelta(hours=2),
        created_at=datetime.now(),
        created_by="user",
        notification_channels=["console"],
        status="pending",
    )
    manager.actions = [action1]

    next_time = manager._calculate_next_execution_time()
    assert next_time is not None
    assert (next_time - datetime.now()).total_seconds() > 7100  # ~2 hours

    # Add earlier action
    action2 = ScheduledAction(
        id="test-2",
        prompt="Action 2",
        scheduled_at=datetime.now() + timedelta(minutes=30),
        created_at=datetime.now(),
        created_by="user",
        notification_channels=["console"],
        status="pending",
    )
    manager.actions.append(action2)

    next_time = manager._calculate_next_execution_time()
    assert next_time is not None
    assert (next_time - datetime.now()).total_seconds() < 1900  # ~30 minutes


@pytest.mark.asyncio
async def test_execute_only_due_actions(tmp_path):
    """Test that only due actions execute, not future ones"""
    action_file = tmp_path / "scheduled-actions.json"
    mock_agent = MagicMock()
    mock_agent.query = AsyncMock(return_value="Done")

    manager = ScheduledActionManager(action_file, mock_agent)

    # Past action (should execute)
    past_action = ScheduledAction(
        id="past",
        prompt="Past action",
        scheduled_at=datetime.now() - timedelta(seconds=10),
        created_at=datetime.now(),
        created_by="user",
        notification_channels=["console"],
        status="pending",
        execute_query=True,  # Execute via agent
        notify=False,
    )

    # Future action (should not execute)
    future_action = ScheduledAction(
        id="future",
        prompt="Future action",
        scheduled_at=datetime.now() + timedelta(hours=1),
        created_at=datetime.now(),
        created_by="user",
        notification_channels=["console"],
        status="pending",
        execute_query=True,  # Execute via agent when due
        notify=False,
    )

    manager.actions = [past_action, future_action]
    await manager.execute_due_actions()

    # Past action should be executed
    assert manager.actions[0].status == "completed"

    # Future action should remain pending
    assert manager.actions[1].status == "pending"

    # Agent called only once (for past action)
    mock_agent.query.assert_called_once_with("Past action")


@pytest.mark.asyncio
async def test_sleep_until_next_action(tmp_path):
    """Test sleeping until next scheduled action"""
    action_file = tmp_path / "scheduled-actions.json"
    mock_agent = MagicMock()
    mock_agent.query = AsyncMock(return_value="Done")

    manager = ScheduledActionManager(action_file, mock_agent)

    # Action in 0.5 seconds
    soon_action = ScheduledAction(
        id="soon",
        prompt="Soon action",
        scheduled_at=datetime.now() + timedelta(seconds=0.5),
        created_at=datetime.now(),
        created_by="user",
        notification_channels=["console"],
        status="pending",
        notify=False,
    )

    manager.actions = [soon_action]

    start = datetime.now()

    # Sleep until next action
    next_time = manager._calculate_next_execution_time()
    if next_time:
        sleep_seconds = (next_time - datetime.now()).total_seconds()
        if sleep_seconds > 0:
            await asyncio.sleep(sleep_seconds)

    elapsed = (datetime.now() - start).total_seconds()

    # Should have slept approximately 0.5 seconds
    assert 0.4 < elapsed < 0.7

    # Now execute
    await manager.execute_due_actions()
    assert manager.actions[0].status == "completed"


@pytest.mark.asyncio
async def test_reload_on_file_change(tmp_path):
    """Test that actions reload when file changes (simulating FileWatchdog)"""
    action_file = tmp_path / "scheduled-actions.json"
    mock_agent = MagicMock()

    manager = ScheduledActionManager(action_file, mock_agent)

    # Initial state - no actions
    assert len(manager.actions) == 0

    # Simulate file change - new action added
    action = ScheduledAction(
        id="new-1",
        prompt="New action",
        scheduled_at=datetime.now() + timedelta(hours=1),
        created_at=datetime.now(),
        created_by="user",
        notification_channels=["console"],
        status="pending",
    )

    # Manually add to list and persist
    manager.actions = [action]
    await manager._persist()

    # Reload (simulating FileWatchdog callback)
    await manager.load_actions()

    # Should have loaded the new action
    assert len(manager.actions) == 1
    assert manager.actions[0].id == "new-1"
