"""Tests for suspension detection via monotonic clock polling."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from ai_assist.suspend_detector import SuspendDetector


@pytest.mark.asyncio
async def test_no_suspension_detected():
    """Test that normal time passage doesn't trigger suspension callback."""
    detector = SuspendDetector(suspend_threshold_seconds=30, poll_interval_seconds=0.1)
    callback = AsyncMock()

    # Run for a short period
    watch_task = asyncio.create_task(detector.watch(callback))
    await asyncio.sleep(0.3)
    watch_task.cancel()

    try:
        await watch_task
    except asyncio.CancelledError:
        pass

    # Should not have triggered callback
    callback.assert_not_called()


@pytest.mark.asyncio
async def test_suspension_detected():
    """Test that clock jump > threshold triggers suspension callback."""
    detector = SuspendDetector(suspend_threshold_seconds=30, poll_interval_seconds=0.1)
    callback = AsyncMock()

    with patch("ai_assist.suspend_detector.time") as mock_time:
        # Initial state
        mock_time.monotonic.return_value = 1000.0
        mock_time.time.return_value = 2000.0

        # Start watching
        watch_task = asyncio.create_task(detector.watch(callback))
        await asyncio.sleep(0.05)  # Let it initialize

        # Simulate suspension: monotonic advances 0.1s, wall clock jumps 60s
        mock_time.monotonic.return_value = 1000.1
        mock_time.time.return_value = 2060.1

        await asyncio.sleep(0.15)  # Wait for poll
        watch_task.cancel()

        try:
            await watch_task
        except asyncio.CancelledError:
            pass

    # Should have triggered callback with wall jump
    callback.assert_called_once()
    wall_jump = callback.call_args[0][0]
    assert abs(wall_jump - 60.0) < 1.0  # ~60s jump


@pytest.mark.asyncio
async def test_backward_clock_jump_detected():
    """Test that backward clock jumps (time change) are also detected."""
    detector = SuspendDetector(suspend_threshold_seconds=30, poll_interval_seconds=0.1)
    callback = AsyncMock()

    with patch("ai_assist.suspend_detector.time") as mock_time:
        # Initial state
        mock_time.monotonic.return_value = 1000.0
        mock_time.time.return_value = 2000.0

        # Start watching
        watch_task = asyncio.create_task(detector.watch(callback))
        await asyncio.sleep(0.05)

        # Simulate backward time change: monotonic advances 0.1s, wall clock goes back 60s
        mock_time.monotonic.return_value = 1000.1
        mock_time.time.return_value = 1940.1

        await asyncio.sleep(0.15)
        watch_task.cancel()

        try:
            await watch_task
        except asyncio.CancelledError:
            pass

    # Should have triggered callback with negative wall jump
    callback.assert_called_once()
    wall_jump = callback.call_args[0][0]
    assert abs(wall_jump - (-60.0)) < 1.0  # ~-60s jump


@pytest.mark.asyncio
async def test_small_clock_drift_ignored():
    """Test that small clock drifts under threshold are ignored."""
    detector = SuspendDetector(suspend_threshold_seconds=30, poll_interval_seconds=0.1)
    callback = AsyncMock()

    with patch("ai_assist.suspend_detector.time") as mock_time:
        # Initial state
        mock_time.monotonic.return_value = 1000.0
        mock_time.time.return_value = 2000.0

        # Start watching
        watch_task = asyncio.create_task(detector.watch(callback))
        await asyncio.sleep(0.05)

        # Simulate small drift: monotonic advances 0.1s, wall clock drifts by 2s
        mock_time.monotonic.return_value = 1000.1
        mock_time.time.return_value = 2000.3  # 0.1s + 0.2s drift

        await asyncio.sleep(0.15)
        watch_task.cancel()

        try:
            await watch_task
        except asyncio.CancelledError:
            pass

    # Should not have triggered callback
    callback.assert_not_called()


@pytest.mark.asyncio
async def test_custom_threshold():
    """Test that custom suspension threshold works."""
    detector = SuspendDetector(suspend_threshold_seconds=10, poll_interval_seconds=0.1)
    callback = AsyncMock()

    with patch("ai_assist.suspend_detector.time") as mock_time:
        # Initial state
        mock_time.monotonic.return_value = 1000.0
        mock_time.time.return_value = 2000.0

        # Start watching
        watch_task = asyncio.create_task(detector.watch(callback))
        await asyncio.sleep(0.05)

        # Simulate 15s jump (over 10s threshold)
        mock_time.monotonic.return_value = 1000.1
        mock_time.time.return_value = 2015.1

        await asyncio.sleep(0.15)
        watch_task.cancel()

        try:
            await watch_task
        except asyncio.CancelledError:
            pass

    # Should have triggered callback
    callback.assert_called_once()
