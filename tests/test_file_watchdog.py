"""Tests for OS-level file watching with watchdog library."""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from ai_assist.file_watchdog import FileWatchdog, _shared_observers


@pytest.fixture(autouse=True)
def _clean_shared_observers():
    """Ensure shared observer state is clean between tests."""
    _shared_observers.clear()
    yield
    _shared_observers.clear()


@pytest.mark.asyncio
async def test_detects_file_modification():
    """Test that file modifications trigger callback."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test.json"
        test_file.write_text('{"test": 1}')

        callback = AsyncMock()
        watchdog = FileWatchdog(test_file, callback, debounce_seconds=0.1)

        await watchdog.start()
        await asyncio.sleep(0.2)  # Let watchdog initialize

        # Modify file
        test_file.write_text('{"test": 2}')

        # Wait for debounce + processing
        await asyncio.sleep(0.3)

        await watchdog.stop()

        # Should have triggered callback once
        assert callback.call_count >= 1


@pytest.mark.asyncio
async def test_debouncing_multiple_changes():
    """Test that multiple rapid changes are debounced into single callback."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test.json"
        test_file.write_text('{"test": 1}')

        callback = AsyncMock()
        watchdog = FileWatchdog(test_file, callback, debounce_seconds=0.2)

        await watchdog.start()
        await asyncio.sleep(0.2)

        # Make multiple rapid changes
        for i in range(5):
            test_file.write_text(f'{{"test": {i}}}')
            await asyncio.sleep(0.05)  # 50ms between changes

        # Wait for debounce + processing
        await asyncio.sleep(0.4)

        await watchdog.stop()

        # Should have triggered callback only once or twice due to debouncing
        # (Some OS might batch differently, so allow some flexibility)
        assert callback.call_count <= 3


@pytest.mark.asyncio
async def test_ignores_other_files():
    """Test that changes to other files in same directory are ignored."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test.json"
        other_file = Path(tmpdir) / "other.json"
        test_file.write_text('{"test": 1}')
        other_file.write_text('{"other": 1}')

        callback = AsyncMock()
        watchdog = FileWatchdog(test_file, callback, debounce_seconds=0.1)

        await watchdog.start()
        await asyncio.sleep(0.2)

        # Modify other file
        other_file.write_text('{"other": 2}')

        await asyncio.sleep(0.3)
        await watchdog.stop()

        # Should not have triggered callback
        callback.assert_not_called()


@pytest.mark.asyncio
async def test_file_created_after_start():
    """Test that watchdog works when file is created after start."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test.json"

        callback = AsyncMock()
        watchdog = FileWatchdog(test_file, callback, debounce_seconds=0.1)

        await watchdog.start()
        await asyncio.sleep(0.2)

        # Create file
        test_file.write_text('{"test": 1}')

        await asyncio.sleep(0.3)

        # Modify file
        test_file.write_text('{"test": 2}')

        await asyncio.sleep(0.3)
        await watchdog.stop()

        # Should have triggered callback for modification
        assert callback.call_count >= 1


@pytest.mark.asyncio
async def test_stop_prevents_further_callbacks():
    """Test that stopping watchdog prevents further callbacks."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test.json"
        test_file.write_text('{"test": 1}')

        callback = AsyncMock()
        watchdog = FileWatchdog(test_file, callback, debounce_seconds=0.1)

        await watchdog.start()
        await asyncio.sleep(0.2)

        # Modify file
        test_file.write_text('{"test": 2}')
        await asyncio.sleep(0.3)

        # Stop watchdog
        await watchdog.stop()
        await asyncio.sleep(0.1)

        # Reset count after stop so we only measure post-stop calls
        callback.reset_mock()

        # Modify file again
        test_file.write_text('{"test": 3}')
        await asyncio.sleep(0.3)

        # Should not have triggered additional callbacks
        assert callback.call_count == 0


@pytest.mark.asyncio
async def test_custom_debounce_time():
    """Test that custom debounce time works."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test.json"
        test_file.write_text('{"test": 1}')

        callback = AsyncMock()
        # Very short debounce
        watchdog = FileWatchdog(test_file, callback, debounce_seconds=0.05)

        await watchdog.start()
        await asyncio.sleep(0.1)

        test_file.write_text('{"test": 2}')

        # Should trigger quickly with short debounce
        await asyncio.sleep(0.15)

        await watchdog.stop()

        assert callback.call_count >= 1


@pytest.mark.asyncio
async def test_multiple_watchers_same_directory():
    """Test that multiple watchers on the same directory share one Observer."""
    with tempfile.TemporaryDirectory() as tmpdir:
        file_a = Path(tmpdir) / "a.json"
        file_b = Path(tmpdir) / "b.json"
        file_a.write_text("a1")
        file_b.write_text("b1")

        callback_a = AsyncMock()
        callback_b = AsyncMock()
        watcher_a = FileWatchdog(file_a, callback_a, debounce_seconds=0.1)
        watcher_b = FileWatchdog(file_b, callback_b, debounce_seconds=0.1)

        # Starting both must not raise (macOS FSEvents would error without sharing)
        await watcher_a.start()
        await watcher_b.start()
        await asyncio.sleep(0.2)

        # Shared observer: one entry for this directory
        assert len(_shared_observers) == 1

        # Modify only file_a
        file_a.write_text("a2")
        await asyncio.sleep(0.3)

        assert callback_a.call_count >= 1
        assert callback_b.call_count == 0

        # Modify only file_b
        file_b.write_text("b2")
        await asyncio.sleep(0.3)

        assert callback_b.call_count >= 1

        await watcher_a.stop()
        # Observer still alive for watcher_b
        assert tmpdir in str(list(_shared_observers.keys()))

        await watcher_b.stop()
        # Observer released
        assert len(_shared_observers) == 0
