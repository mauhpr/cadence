"""
Shared test fixtures for Cadence test suite.

Provides minimal, reusable fixtures following the "simple factories over complex harness" pattern.
Inspired by Temporal's WorkflowEnvironment and Prefect's test_harness context manager.
"""

import asyncio
from dataclasses import dataclass
from typing import Any

import pytest

from cadence import Score, note


# =============================================================================
# Session-Scoped Event Loop
# =============================================================================


@pytest.fixture(scope="session")
def event_loop():
    """
    Single event loop for all tests (3-4x faster than function-scoped).

    This is the recommended pattern from pytest-asyncio for performance.
    All async tests share this loop, reducing setup/teardown overhead.
    """
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# =============================================================================
# Test Scores
# =============================================================================


@dataclass
class SampleScore(Score):
    """
    Minimal score for unit tests.

    Includes common fields used across test scenarios:
    - value: string accumulator for tracking note execution order
    - count: integer counter for tracking execution count
    - completed: flag for tracking completion state
    """
    value: str = ""
    count: int = 0
    completed: bool = False


@pytest.fixture
def test_score() -> SampleScore:
    """Provide a fresh SampleScore instance for each test."""
    score = SampleScore()
    score.__post_init__()  # Initialize locks
    return score


# =============================================================================
# Note Factories
# =============================================================================


def make_note(
    name: str = "test_note",
    side_effect: Exception | None = None,
    return_value: Any = None,
    delay: float = 0,
    append_to_value: str | None = None,
    increment_count: bool = False,
):
    """
    Create a mock note for testing. Covers 95% of testing needs.

    Args:
        name: Name for the note function (appears in traces/logs)
        side_effect: Exception to raise when note executes
        return_value: Value to return (notes typically return None)
        delay: Artificial delay in seconds (use TimeController for testing)
        append_to_value: String to append to score.value (if score has it)
        increment_count: Whether to increment score.count (if score has it)

    Returns:
        A decorated note function ready for use in cadences

    Example:
        >>> success_note = make_note("validate", append_to_value="V")
        >>> failing_note = make_note("payment", side_effect=ConnectionError())
    """
    async def _note(score: Score) -> Any:
        if delay > 0:
            await asyncio.sleep(delay)

        # Track execution in score if fields exist
        if append_to_value is not None and hasattr(score, "value"):
            score.value += append_to_value
        if increment_count and hasattr(score, "count"):
            score.count += 1

        if side_effect:
            raise side_effect

        return return_value

    _note.__name__ = name
    return note(_note)


def make_flaky_note(
    name: str = "flaky_note",
    failures: int = 2,
    error: Exception | None = None,
    append_on_success: str | None = None,
):
    """
    Create a note that fails N times then succeeds.

    Useful for testing retry logic without relying on randomness.
    Uses closure to track call count across invocations.

    Args:
        name: Name for the note function
        failures: Number of times to fail before succeeding
        error: Exception to raise on failure (defaults to ConnectionError)
        append_on_success: String to append to score.value on success

    Returns:
        A decorated note function that fails predictably

    Example:
        >>> flaky = make_flaky_note("api_call", failures=3)
        >>> # First 3 calls raise ConnectionError, 4th succeeds
    """
    if error is None:
        error = ConnectionError("transient failure")

    call_count = 0

    async def _note(score: Score) -> None:
        nonlocal call_count
        call_count += 1

        if call_count <= failures:
            raise error

        # Success path
        if append_on_success is not None and hasattr(score, "value"):
            score.value += append_on_success

    _note.__name__ = name
    return note(_note)


def make_sync_note(
    name: str = "sync_note",
    side_effect: Exception | None = None,
    append_to_value: str | None = None,
):
    """
    Create a synchronous note for testing sync/async interop.

    Cadence supports both sync and async notes. This factory creates
    synchronous notes for testing that capability.

    Args:
        name: Name for the note function
        side_effect: Exception to raise when note executes
        append_to_value: String to append to score.value

    Returns:
        A decorated synchronous note function
    """
    def _note(score: Score) -> None:
        if append_to_value is not None and hasattr(score, "value"):
            score.value += append_to_value

        if side_effect:
            raise side_effect

    _note.__name__ = name
    return note(_note)


# =============================================================================
# Hook Testing Utilities
# =============================================================================


class MockHooksCollector:
    """
    Collect hook invocations for testing.

    Records all hook method calls with their arguments for assertions.
    Useful for testing custom hook implementations.

    Example:
        >>> collector = MockHooksCollector()
        >>> cadence.with_hooks(collector).run()
        >>> assert ("before_note", "validate") in collector.calls
    """

    def __init__(self):
        self.calls: list[tuple[str, ...]] = []

    async def before_cadence(self, cadence_name: str, score: Score) -> None:
        self.calls.append(("before_cadence", cadence_name))

    async def after_cadence(
        self,
        cadence_name: str,
        score: Score,
        duration: float,
        error: Exception | None = None,
    ) -> None:
        self.calls.append(("after_cadence", cadence_name, error is not None))

    async def before_note(self, note_name: str, score: Score) -> None:
        self.calls.append(("before_note", note_name))

    async def after_note(
        self,
        note_name: str,
        score: Score,
        duration: float,
        error: Exception | None = None,
    ) -> None:
        self.calls.append(("after_note", note_name, error is not None))

    async def on_error(
        self,
        note_name: str,
        score: Score,
        error: Exception,
    ) -> bool | None:
        self.calls.append(("on_error", note_name, str(error)))
        return None  # Don't suppress errors

    async def on_retry(
        self,
        note_name: str,
        score: Score,
        attempt: int,
        max_attempts: int,
        error: Exception,
    ) -> None:
        self.calls.append(("on_retry", note_name, attempt, max_attempts))


@pytest.fixture
def mock_hooks() -> MockHooksCollector:
    """Provide a fresh MockHooksCollector for each test."""
    return MockHooksCollector()


# =============================================================================
# Time Control
# =============================================================================


from tests.time_control import TimeController


@pytest.fixture
def time_controller() -> TimeController:
    """Provide a fresh TimeController for testing timeouts without real delays."""
    return TimeController()


# =============================================================================
# Async Utilities
# =============================================================================


@pytest.fixture
def fast_timeout() -> float:
    """Short timeout for tests that need quick failure detection."""
    return 0.1


@pytest.fixture
def slow_timeout() -> float:
    """Longer timeout for tests with intentional delays."""
    return 2.0
