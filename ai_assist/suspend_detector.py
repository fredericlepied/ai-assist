"""Suspension detection via monotonic clock polling.

This module detects laptop suspension by comparing monotonic clock
(which pauses during suspension) with wall-clock time (which continues).
"""

import asyncio
import time
from collections.abc import Awaitable, Callable


class SuspendDetector:
    """Detects system suspension by monitoring clock discontinuities.

    Uses monotonic clock vs wall-clock comparison to detect when the
    system has been suspended. Triggers a callback when a discontinuity
    larger than the threshold is detected.

    Attributes:
        suspend_threshold_seconds: Minimum clock jump to trigger suspension detection
        poll_interval_seconds: How often to check for clock discontinuities
    """

    def __init__(
        self,
        suspend_threshold_seconds: float = 30.0,
        poll_interval_seconds: float = 5.0,
    ):
        """Initialize suspension detector.

        Args:
            suspend_threshold_seconds: Minimum clock jump (in seconds) to
                consider as suspension. Default 30s.
            poll_interval_seconds: How often to poll for clock jumps.
                Default 5s.
        """
        self.suspend_threshold_seconds = suspend_threshold_seconds
        self.poll_interval_seconds = poll_interval_seconds
        self.last_monotonic: float | None = None
        self.last_wall_clock: float | None = None

    async def watch(self, callback: Callable[..., Awaitable[None]]) -> None:
        """Watch for suspension events and trigger callback.

        Args:
            callback: Async function called with wall_jump_seconds when
                suspension is detected. Positive values indicate forward
                jump (suspension), negative values indicate backward clock
                adjustment.

        This method runs indefinitely until cancelled.
        """
        # Initialize on first run
        self.last_monotonic = time.monotonic()
        self.last_wall_clock = time.time()

        while True:
            await asyncio.sleep(self.poll_interval_seconds)

            current_mono = time.monotonic()
            current_wall = time.time()

            # Calculate elapsed time according to each clock
            mono_elapsed = current_mono - self.last_monotonic
            expected_wall = self.last_wall_clock + mono_elapsed

            # Detect discontinuity
            wall_jump = current_wall - expected_wall

            if abs(wall_jump) > self.suspend_threshold_seconds:
                # System suspended or clock changed
                await callback(wall_jump)

            # Update for next iteration
            self.last_monotonic = current_mono
            self.last_wall_clock = current_wall
