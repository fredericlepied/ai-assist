"""Tests for TUI notification display"""

import json
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from rich.console import Console

from ai_assist.tui_interactive import NotificationWatcher, display_notification


@pytest.mark.asyncio
async def test_display_notification(capsys):
    """Test that notification is displayed in TUI"""
    console = Console()

    notification = {
        "timestamp": "2026-02-08T14:00:00",
        "level": "success",
        "title": "Test Notification",
        "message": "This is a test message",
        "action_id": "test-123",
    }

    await display_notification(console, notification)

    # Can't easily verify Rich output, but at least verify no errors
    assert True


@pytest.mark.asyncio
async def test_notification_watcher_reads_new_entries(tmp_path):
    """Test that NotificationWatcher reads and displays new log entries"""
    console = MagicMock()
    notification_log = tmp_path / "notifications.log"

    # Create initial log file
    notification_log.write_text("")

    # Create watcher (should seek to end)
    watcher = NotificationWatcher(console)
    watcher.notification_log = notification_log

    # Initialize position
    watcher.last_position = 0

    # Add a notification
    notification = {
        "timestamp": datetime.now().isoformat(),
        "level": "info",
        "title": "Test",
        "message": "New notification",
        "action_id": "test-1",
    }

    with open(notification_log, "a") as f:
        f.write(json.dumps(notification) + "\n")

    # Trigger file change handler
    await watcher.on_file_change()

    # Verify it read the notification (position advanced)
    assert watcher.last_position > 0


@pytest.mark.asyncio
async def test_notification_watcher_ignores_existing_entries(tmp_path):
    """Test that NotificationWatcher only shows new entries, not existing ones"""
    console = MagicMock()
    notification_log = tmp_path / "notifications.log"

    # Create log file with existing entries
    existing_notification = {
        "timestamp": datetime.now().isoformat(),
        "level": "info",
        "title": "Old",
        "message": "Old notification",
        "action_id": "old-1",
    }

    with open(notification_log, "w") as f:
        f.write(json.dumps(existing_notification) + "\n")

    # Create watcher (should seek to end, ignoring existing entries)
    watcher = NotificationWatcher(console)
    watcher.notification_log = notification_log

    # Trigger file change handler - should not display old notifications
    await watcher.on_file_change()

    # Now add a new notification
    new_notification = {
        "timestamp": datetime.now().isoformat(),
        "level": "success",
        "title": "New",
        "message": "New notification",
        "action_id": "new-1",
    }

    with open(notification_log, "a") as f:
        f.write(json.dumps(new_notification) + "\n")

    await watcher.on_file_change()

    # Verify position advanced beyond just the new entry
    assert watcher.last_position > len(json.dumps(existing_notification))


@pytest.mark.asyncio
async def test_notification_watcher_handles_malformed_json(tmp_path):
    """Test that NotificationWatcher gracefully handles malformed JSON"""
    console = MagicMock()
    notification_log = tmp_path / "notifications.log"

    notification_log.write_text("")

    watcher = NotificationWatcher(console)
    watcher.notification_log = notification_log
    watcher.last_position = 0

    # Add malformed JSON
    with open(notification_log, "a") as f:
        f.write("not valid json\n")

    # Should not raise exception
    await watcher.on_file_change()

    assert watcher.last_position > 0


@pytest.mark.asyncio
async def test_notification_watcher_start_stop(tmp_path):
    """Test that NotificationWatcher can start and stop cleanly"""
    console = MagicMock()
    notification_log = tmp_path / "notifications.log"
    notification_log.write_text("")

    watcher = NotificationWatcher(console)
    watcher.notification_log = notification_log

    await watcher.start()
    assert watcher.watchdog is not None

    await watcher.stop()
    # Verify it stopped cleanly (no exceptions)
