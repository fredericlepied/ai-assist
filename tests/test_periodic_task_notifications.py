"""Tests for periodic task and monitor notifications"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_assist.monitor_runner import MonitorRunner
from ai_assist.task_runner import TaskRunner
from ai_assist.tasks import MonitorDefinition, TaskDefinition


@pytest.mark.asyncio
async def test_task_with_notify_sends_notification(tmp_path):
    """Test that task with notify=True sends notification on completion"""
    # Create task with notify enabled
    task_def = TaskDefinition(
        name="test-task",
        prompt="Check system status",
        interval="1h",
        enabled=True,
        notify=True,
        notification_channels=["console", "file"],
    )

    mock_agent = MagicMock()
    mock_agent.query = AsyncMock(return_value="System is healthy")

    mock_state = MagicMock()

    # Patch NotificationDispatcher to verify it's called
    with patch("ai_assist.notification_dispatcher.NotificationDispatcher") as mock_dispatcher_class:
        mock_dispatcher = MagicMock()
        mock_dispatcher.dispatch = AsyncMock(return_value={"console": True, "file": True})
        mock_dispatcher_class.return_value = mock_dispatcher

        runner = TaskRunner(task_def, mock_agent, mock_state)
        result = await runner.run()

        # Verify task executed
        assert result.success is True
        assert "System is healthy" in result.output

        # Verify notification was dispatched
        mock_dispatcher_class.assert_called_once()
        mock_dispatcher.dispatch.assert_called_once()

        # Verify notification details
        notification = mock_dispatcher.dispatch.call_args[0][0]
        assert notification.title == "Task: test-task"
        assert notification.level == "success"
        assert notification.channels == ["console", "file"]


@pytest.mark.asyncio
async def test_task_without_notify_no_notification(tmp_path):
    """Test that task with notify=False does not send notification"""
    task_def = TaskDefinition(
        name="silent-task",
        prompt="Check logs",
        interval="5m",
        enabled=True,
        notify=False,  # No notifications
    )

    mock_agent = MagicMock()
    mock_agent.query = AsyncMock(return_value="Logs are clean")

    mock_state = MagicMock()

    with patch("ai_assist.notification_dispatcher.NotificationDispatcher") as mock_dispatcher_class:
        runner = TaskRunner(task_def, mock_agent, mock_state)
        result = await runner.run()

        # Task should execute
        assert result.success is True

        # No notification dispatcher should be created
        mock_dispatcher_class.assert_not_called()


@pytest.mark.asyncio
async def test_task_failure_sends_error_notification(tmp_path):
    """Test that failed task sends error-level notification"""
    task_def = TaskDefinition(
        name="failing-task",
        prompt="This will fail",
        interval="1h",
        enabled=True,
        notify=True,
        notification_channels=["console"],
    )

    mock_agent = MagicMock()
    mock_agent.query = AsyncMock(side_effect=Exception("Task failed"))

    mock_state = MagicMock()

    with patch("ai_assist.notification_dispatcher.NotificationDispatcher") as mock_dispatcher_class:
        mock_dispatcher = MagicMock()
        mock_dispatcher.dispatch = AsyncMock(return_value={"console": True})
        mock_dispatcher_class.return_value = mock_dispatcher

        runner = TaskRunner(task_def, mock_agent, mock_state)
        result = await runner.run()

        # Task should be marked as failed
        assert result.success is False
        assert "Task failed" in result.output

        # Verify error notification was sent
        mock_dispatcher.dispatch.assert_called_once()
        notification = mock_dispatcher.dispatch.call_args[0][0]
        assert notification.level == "error"
        assert notification.title == "Task: failing-task"


@pytest.mark.asyncio
async def test_monitor_with_notify_sends_notification(tmp_path):
    """Test that monitor with notify=True sends notification"""
    monitor_def = MonitorDefinition(
        name="test-monitor",
        prompt="Check for failures",
        interval="30m",
        enabled=True,
        notify=True,
        notification_channels=["desktop", "file"],
    )

    mock_agent = MagicMock()
    mock_agent.query = AsyncMock(return_value="No failures found")

    # Mock state manager to not return cached results
    mock_state = MagicMock()
    mock_state.get_cached_query = MagicMock(return_value=None)  # No cache

    with patch("ai_assist.notification_dispatcher.NotificationDispatcher") as mock_dispatcher_class:
        mock_dispatcher = MagicMock()
        mock_dispatcher.dispatch = AsyncMock(return_value={"desktop": True, "file": True})
        mock_dispatcher_class.return_value = mock_dispatcher

        runner = MonitorRunner(monitor_def, mock_agent, mock_state, None)
        await runner.run()

        # Verify notification was sent
        mock_dispatcher_class.assert_called_once()
        mock_dispatcher.dispatch.assert_called_once()

        notification = mock_dispatcher.dispatch.call_args[0][0]
        assert notification.title == "Monitor: test-monitor"
        assert notification.channels == ["desktop", "file"]


@pytest.mark.asyncio
async def test_notification_truncates_long_output(tmp_path):
    """Test that notification message is truncated if output is too long"""
    task_def = TaskDefinition(
        name="verbose-task",
        prompt="Generate long output",
        interval="1h",
        enabled=True,
        notify=True,
        notification_channels=["console"],
    )

    # Create very long output (300 chars)
    long_output = "A" * 300

    mock_agent = MagicMock()
    mock_agent.query = AsyncMock(return_value=long_output)

    mock_state = MagicMock()

    with patch("ai_assist.notification_dispatcher.NotificationDispatcher") as mock_dispatcher_class:
        mock_dispatcher = MagicMock()
        mock_dispatcher.dispatch = AsyncMock(return_value={"console": True})
        mock_dispatcher_class.return_value = mock_dispatcher

        runner = TaskRunner(task_def, mock_agent, mock_state)
        await runner.run()

        # Verify notification message is truncated
        notification = mock_dispatcher.dispatch.call_args[0][0]
        assert len(notification.message) <= 200


@pytest.mark.asyncio
async def test_default_notification_channels(tmp_path):
    """Test that default notification channels are used if not specified"""
    task_def = TaskDefinition(
        name="default-channels-task",
        prompt="Check status",
        interval="1h",
        enabled=True,
        notify=True,
        # No notification_channels specified
    )

    mock_agent = MagicMock()
    mock_agent.query = AsyncMock(return_value="OK")

    mock_state = MagicMock()

    with patch("ai_assist.notification_dispatcher.NotificationDispatcher") as mock_dispatcher_class:
        mock_dispatcher = MagicMock()
        mock_dispatcher.dispatch = AsyncMock(return_value={"console": True})
        mock_dispatcher_class.return_value = mock_dispatcher

        runner = TaskRunner(task_def, mock_agent, mock_state)
        await runner.run()

        # Should use default channels (console only for tasks)
        notification = mock_dispatcher.dispatch.call_args[0][0]
        assert "console" in notification.channels
