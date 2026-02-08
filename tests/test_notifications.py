"""Tests for notification system"""

import json
from datetime import datetime

import pytest

from ai_assist.notification_channels import (
    ConsoleNotificationChannel,
    DesktopNotificationChannel,
    FileNotificationChannel,
)
from ai_assist.notification_dispatcher import Notification, NotificationDispatcher


@pytest.mark.asyncio
async def test_console_notification(capsys):
    """Test console notification delivery"""
    notification = Notification(
        id="notif-1",
        action_id="action-1",
        title="Action Completed",
        message="DCI job check found 5 failures",
        level="warning",
        timestamp=datetime.now(),
        channels=["console"],
        delivered={},
    )

    channel = ConsoleNotificationChannel()
    result = await channel.send(notification)

    assert result is True


@pytest.mark.asyncio
async def test_file_notification(tmp_path):
    """Test file log notification delivery"""
    log_file = tmp_path / "notifications.log"

    notification = Notification(
        id="notif-2",
        action_id="action-2",
        title="Reminder",
        message="Check on deployment status",
        level="info",
        timestamp=datetime.now(),
        channels=["file"],
        delivered={},
    )

    channel = FileNotificationChannel(log_file)
    result = await channel.send(notification)

    assert result is True

    # Verify appended to log
    assert log_file.exists()
    content = log_file.read_text()
    assert "Check on deployment status" in content
    assert "action-2" in content


@pytest.mark.asyncio
async def test_notification_dispatcher(tmp_path):
    """Test notification dispatcher with multiple channels"""
    log_file = tmp_path / "notifications.log"

    notification = Notification(
        id="notif-3",
        action_id="action-3",
        title="Test Notification",
        message="This is a test message",
        level="success",
        timestamp=datetime.now(),
        channels=["console", "file"],
        delivered={},
    )

    dispatcher = NotificationDispatcher(notification_log=log_file)
    results = await dispatcher.dispatch(notification)

    # Both channels should succeed
    assert results["console"] is True
    assert results["file"] is True

    # Verify notification marked as delivered
    assert notification.delivered["console"] is True
    assert notification.delivered["file"] is True

    # Verify file log
    assert log_file.exists()
    content = log_file.read_text()
    assert "This is a test message" in content


@pytest.mark.asyncio
async def test_notification_with_unknown_channel(tmp_path):
    """Test notification dispatcher handles unknown channels gracefully"""
    log_file = tmp_path / "notifications.log"

    notification = Notification(
        id="notif-4",
        action_id="action-4",
        title="Test",
        message="Test message",
        level="info",
        timestamp=datetime.now(),
        channels=["console", "unknown_channel", "file"],
        delivered={},
    )

    dispatcher = NotificationDispatcher(notification_log=log_file)
    results = await dispatcher.dispatch(notification)

    # Known channels succeed
    assert results["console"] is True
    assert results["file"] is True

    # Unknown channel fails
    assert results["unknown_channel"] is False


@pytest.mark.asyncio
async def test_multiple_notifications_append(tmp_path):
    """Test that multiple notifications append to log file"""
    log_file = tmp_path / "notifications.log"
    channel = FileNotificationChannel(log_file)

    # Send first notification
    notif1 = Notification(
        id="notif-1",
        action_id="action-1",
        title="First",
        message="First message",
        level="info",
        timestamp=datetime.now(),
        channels=["file"],
        delivered={},
    )
    await channel.send(notif1)

    # Send second notification
    notif2 = Notification(
        id="notif-2",
        action_id="action-2",
        title="Second",
        message="Second message",
        level="warning",
        timestamp=datetime.now(),
        channels=["file"],
        delivered={},
    )
    await channel.send(notif2)

    # Verify both are in log
    content = log_file.read_text()
    assert "First message" in content
    assert "Second message" in content

    # Verify JSONL format (2 lines)
    lines = content.strip().split("\n")
    assert len(lines) == 2
    json.loads(lines[0])  # Should parse as JSON
    json.loads(lines[1])  # Should parse as JSON


@pytest.mark.asyncio
async def test_desktop_notification():
    """Test desktop notification via libnotify/D-Bus"""

    notification = Notification(
        id="notif-desktop",
        action_id="action-desktop",
        title="Test Desktop Notification",
        message="This is a test",
        level="info",
        timestamp=datetime.now(),
        channels=["desktop"],
        delivered={},
    )

    channel = DesktopNotificationChannel()
    result = await channel.send(notification)

    # Should return bool (success depends on platform and notify-send availability)
    assert isinstance(result, bool)

    # On Linux with notify-send, should succeed
    # On other platforms or without notify-send, may fail gracefully
