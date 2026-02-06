"""Tests for task file watcher"""

import asyncio
from pathlib import Path

import pytest

from ai_assist.task_watcher import TaskFileWatcher


@pytest.fixture
def temp_task_file(tmp_path):
    """Create temporary task file"""
    task_file = tmp_path / "tasks.yaml"
    task_file.write_text("tasks: []")
    return task_file


@pytest.mark.asyncio
async def test_file_watcher_detects_change(temp_task_file):
    """Test that file watcher detects file changes"""
    callback_called = False

    async def callback():
        nonlocal callback_called
        callback_called = True

    watcher = TaskFileWatcher(temp_task_file, callback)

    # Start watcher in background
    watch_task = asyncio.create_task(watcher.watch(check_interval=0.1))

    # Give it time to initialize
    await asyncio.sleep(0.2)

    # Modify the file
    temp_task_file.write_text("tasks:\n  - name: test\n")

    # Give watcher time to detect change
    await asyncio.sleep(0.3)

    # Stop watcher
    watcher.stop()
    watch_task.cancel()
    try:
        await watch_task
    except asyncio.CancelledError:
        pass

    assert callback_called is True


@pytest.mark.asyncio
async def test_file_watcher_no_change(temp_task_file):
    """Test that callback is not called when file doesn't change"""
    callback_count = 0

    async def callback():
        nonlocal callback_count
        callback_count += 1

    watcher = TaskFileWatcher(temp_task_file, callback)

    # Start watcher
    watch_task = asyncio.create_task(watcher.watch(check_interval=0.1))

    # Wait but don't modify file
    await asyncio.sleep(0.3)

    # Stop watcher
    watcher.stop()
    watch_task.cancel()
    try:
        await watch_task
    except asyncio.CancelledError:
        pass

    # Callback should not be called (file hasn't changed)
    assert callback_count == 0


@pytest.mark.asyncio
async def test_file_watcher_handles_callback_error(temp_task_file):
    """Test that file watcher continues running even if callback fails"""
    callback_count = 0

    async def failing_callback():
        nonlocal callback_count
        callback_count += 1
        raise Exception("Callback error")

    watcher = TaskFileWatcher(temp_task_file, failing_callback)

    # Start watcher
    watch_task = asyncio.create_task(watcher.watch(check_interval=0.1))

    # Give it time to initialize
    await asyncio.sleep(0.2)

    # Modify file
    temp_task_file.write_text("tasks:\n  - name: test1\n")

    # Wait for detection
    await asyncio.sleep(0.3)

    # Modify again
    temp_task_file.write_text("tasks:\n  - name: test2\n")

    # Wait for second detection
    await asyncio.sleep(0.3)

    # Stop watcher
    watcher.stop()
    watch_task.cancel()
    try:
        await watch_task
    except asyncio.CancelledError:
        pass

    # Both callbacks should have been attempted despite errors
    assert callback_count >= 1


@pytest.mark.asyncio
async def test_file_watcher_nonexistent_file(tmp_path):
    """Test file watcher with non-existent file"""
    nonexistent = tmp_path / "nonexistent.yaml"

    callback_called = False

    async def callback():
        nonlocal callback_called
        callback_called = True

    watcher = TaskFileWatcher(nonexistent, callback)

    # Start watcher
    watch_task = asyncio.create_task(watcher.watch(check_interval=0.1))

    # Wait a bit
    await asyncio.sleep(0.2)

    # Create the file
    nonexistent.write_text("tasks: []")

    # Wait for detection
    await asyncio.sleep(0.3)

    # Stop watcher
    watcher.stop()
    watch_task.cancel()
    try:
        await watch_task
    except asyncio.CancelledError:
        pass

    # Callback should be called when file appears
    assert callback_called is True


def test_file_watcher_stop():
    """Test stopping file watcher"""
    watcher = TaskFileWatcher(Path("/tmp/test.yaml"), lambda: None)
    assert watcher.running is False

    watcher.running = True
    watcher.stop()
    assert watcher.running is False
