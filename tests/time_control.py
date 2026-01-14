"""
Time Control utilities for testing Cadence timeouts and delays.

Inspired by Temporal's WorkflowEnvironment.start_time_skipping() pattern,
this module provides a TimeController that enables testing timeout behavior
without waiting for real delays.

Example:
    async def test_timeout():
        controller = TimeController()
        async with controller.time_skipping():
            # This test completes instantly even with a 30s timeout
            result = await cadence_with_30s_timeout.run()
            assert controller.elapsed >= 30.0
"""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from unittest.mock import patch


class TimeController:
    """
    Control time in tests without real delays.

    The TimeController patches asyncio.sleep() to advance virtual time
    instantly while yielding control to the event loop. This allows
    testing timeout behavior, retry delays, and rate limiting without
    waiting for actual time to pass.

    Features:
    - Track total elapsed virtual time
    - Test timeout scenarios in milliseconds
    - Verify delay patterns (e.g., exponential backoff)
    - Reset time between tests

    Example:
        >>> controller = TimeController()
        >>> async with controller.time_skipping():
        ...     await some_function_with_delays()
        ...     print(f"Virtual time elapsed: {controller.elapsed}s")
    """

    def __init__(self):
        """Initialize the time controller with zero elapsed time."""
        self._current_time: float = 0.0
        self._original_sleep = asyncio.sleep
        self._sleep_calls: list[float] = []

    async def _mock_sleep(self, delay: float) -> None:
        """
        Instant sleep that advances virtual time.

        Args:
            delay: The requested sleep duration in seconds

        Instead of actually sleeping, this:
        1. Records the delay for verification
        2. Advances the virtual clock
        3. Yields control with sleep(0) so other coroutines can run
        """
        self._sleep_calls.append(delay)
        self._current_time += delay
        # Yield control without actual delay - use original sleep to avoid recursion
        await self._original_sleep(0)

    @asynccontextmanager
    async def time_skipping(self) -> AsyncGenerator["TimeController", None]:
        """
        Context manager for instant time advancement.

        All asyncio.sleep() calls within this context will be intercepted
        and advanced instantly. The virtual time and sleep calls are tracked
        for assertions.

        Example:
            >>> async with controller.time_skipping():
            ...     await asyncio.sleep(10)  # Returns instantly
            ...     assert controller.elapsed == 10.0
        """
        with patch.object(asyncio, "sleep", self._mock_sleep):
            yield self

    @property
    def elapsed(self) -> float:
        """
        Total virtual time elapsed.

        Returns:
            The sum of all sleep durations since last reset.
        """
        return self._current_time

    @property
    def sleep_calls(self) -> list[float]:
        """
        List of all sleep durations requested.

        Useful for verifying retry backoff patterns or rate limiting.

        Returns:
            List of sleep durations in order of occurrence.

        Example:
            >>> # Verify exponential backoff pattern
            >>> assert controller.sleep_calls == [1.0, 2.0, 4.0, 8.0]
        """
        return self._sleep_calls.copy()

    @property
    def sleep_count(self) -> int:
        """
        Number of sleep calls made.

        Returns:
            Count of times asyncio.sleep() was called.
        """
        return len(self._sleep_calls)

    def reset(self) -> None:
        """
        Reset the time controller for a new test.

        Clears:
        - Elapsed virtual time
        - Sleep call history
        """
        self._current_time = 0.0
        self._sleep_calls.clear()

    def assert_slept_for(self, expected: float, tolerance: float = 0.001) -> None:
        """
        Assert that the total sleep time matches expected.

        Args:
            expected: Expected total sleep duration
            tolerance: Acceptable difference (default 0.001s)

        Raises:
            AssertionError: If actual differs from expected beyond tolerance
        """
        actual = self.elapsed
        if abs(actual - expected) > tolerance:
            raise AssertionError(
                f"Expected total sleep of {expected}s, but got {actual}s "
                f"(difference: {abs(actual - expected)}s)"
            )

    def assert_sleep_pattern(
        self, expected_pattern: list[float], tolerance: float = 0.001
    ) -> None:
        """
        Assert that sleep calls match an expected pattern.

        Useful for verifying exponential backoff or fixed delays.

        Args:
            expected_pattern: List of expected sleep durations in order
            tolerance: Acceptable difference per call (default 0.001s)

        Raises:
            AssertionError: If actual pattern differs from expected

        Example:
            >>> # Verify exponential backoff: 1s, 2s, 4s
            >>> controller.assert_sleep_pattern([1.0, 2.0, 4.0])
        """
        actual = self.sleep_calls

        if len(actual) != len(expected_pattern):
            raise AssertionError(
                f"Expected {len(expected_pattern)} sleep calls, got {len(actual)}.\n"
                f"Expected: {expected_pattern}\n"
                f"Actual: {actual}"
            )

        for i, (expected_delay, actual_delay) in enumerate(
            zip(expected_pattern, actual, strict=True)
        ):
            if abs(expected_delay - actual_delay) > tolerance:
                raise AssertionError(
                    f"Sleep call {i}: expected {expected_delay}s, got {actual_delay}s.\n"
                    f"Full expected: {expected_pattern}\n"
                    f"Full actual: {actual}"
                )


# =============================================================================
# Pytest Fixture (also available in conftest.py)
# =============================================================================


def time_controller() -> TimeController:
    """
    Create a fresh TimeController.

    For pytest fixtures, this function can be used directly:

        @pytest.fixture
        def time_controller():
            return TimeController()

    Or imported from this module:

        from tests.time_control import time_controller as tc_fixture
    """
    return TimeController()
