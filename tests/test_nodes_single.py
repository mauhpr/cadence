"""Tests for SingleMeasure node.

Tests cover:
- Basic async task execution
- Sync task execution
- Interrupt signal handling
- Score modification
- Error propagation
"""

from dataclasses import dataclass

import pytest

from cadence import Score, note
from cadence.nodes.single import SingleMeasure


# =============================================================================
# Test Fixtures
# =============================================================================


@dataclass
class SingleTestScore(Score):
    """Score for single measure tests."""
    value: str = ""
    count: int = 0


@pytest.fixture
def single_score() -> SingleTestScore:
    """Provide a fresh score for each test."""
    score = SingleTestScore()
    score.__post_init__()
    return score


# =============================================================================
# Test: Basic Execution
# =============================================================================


class TestSingleMeasureBasic:
    """Tests for basic SingleMeasure execution."""

    async def test_execute_async_task(self, single_score: SingleTestScore):
        """SingleMeasure should execute async tasks."""
        async def set_value(score: SingleTestScore) -> None:
            score.value = "async"

        measure = SingleMeasure(single_score, "async_task", set_value)
        result = await measure.execute()

        assert result is None
        assert single_score.value == "async"

    async def test_execute_sync_task(self, single_score: SingleTestScore):
        """SingleMeasure should execute sync tasks."""
        def set_value(score: SingleTestScore) -> None:
            score.value = "sync"

        measure = SingleMeasure(single_score, "sync_task", set_value)
        result = await measure.execute()

        assert result is None
        assert single_score.value == "sync"

    async def test_execute_modifies_score(self, single_score: SingleTestScore):
        """SingleMeasure should allow score modification."""
        async def modify(score: SingleTestScore) -> None:
            score.value += "A"
            score.count += 1

        measure = SingleMeasure(single_score, "modify", modify)
        await measure.execute()

        assert single_score.value == "A"
        assert single_score.count == 1

    async def test_execute_multiple_times(self, single_score: SingleTestScore):
        """SingleMeasure can be executed multiple times."""
        async def increment(score: SingleTestScore) -> None:
            score.count += 1

        measure = SingleMeasure(single_score, "increment", increment)

        await measure.execute()
        await measure.execute()
        await measure.execute()

        assert single_score.count == 3

    async def test_measure_name_property(self, single_score: SingleTestScore):
        """SingleMeasure should expose its name."""
        async def noop(score: SingleTestScore) -> None:
            pass

        measure = SingleMeasure(single_score, "test_name", noop)

        assert measure.name == "test_name"


# =============================================================================
# Test: Interrupt Signal
# =============================================================================


class TestSingleMeasureInterrupt:
    """Tests for interrupt signal handling."""

    async def test_interrupt_disabled_by_default(self, single_score: SingleTestScore):
        """By default, returning True does not interrupt."""
        async def return_true(score: SingleTestScore) -> bool:
            return True

        measure = SingleMeasure(single_score, "no_interrupt", return_true)
        result = await measure.execute()

        # can_interrupt is False by default, so True return is ignored
        assert result is None

    async def test_interrupt_enabled_returns_true(self, single_score: SingleTestScore):
        """With can_interrupt=True, returning True signals interrupt."""
        async def return_true(score: SingleTestScore) -> bool:
            return True

        measure = SingleMeasure(
            single_score, "interrupt", return_true, can_interrupt=True
        )
        result = await measure.execute()

        assert result is True

    async def test_interrupt_enabled_returns_false(self, single_score: SingleTestScore):
        """With can_interrupt=True, returning False does not interrupt."""
        async def return_false(score: SingleTestScore) -> bool:
            return False

        measure = SingleMeasure(
            single_score, "no_interrupt", return_false, can_interrupt=True
        )
        result = await measure.execute()

        # False is not truthy, so no interrupt
        assert result is None

    async def test_interrupt_enabled_returns_none(self, single_score: SingleTestScore):
        """With can_interrupt=True, returning None does not interrupt."""
        async def return_none(score: SingleTestScore) -> None:
            return None

        measure = SingleMeasure(
            single_score, "no_interrupt", return_none, can_interrupt=True
        )
        result = await measure.execute()

        assert result is None

    async def test_sync_task_can_interrupt(self, single_score: SingleTestScore):
        """Sync tasks can also signal interrupt."""
        def return_true(score: SingleTestScore) -> bool:
            return True

        measure = SingleMeasure(
            single_score, "sync_interrupt", return_true, can_interrupt=True
        )
        result = await measure.execute()

        assert result is True


# =============================================================================
# Test: Error Handling
# =============================================================================


class TestSingleMeasureErrors:
    """Tests for error handling in SingleMeasure."""

    async def test_async_exception_propagates(self, single_score: SingleTestScore):
        """Exceptions from async tasks should propagate."""
        async def raise_error(score: SingleTestScore) -> None:
            raise ValueError("async error")

        measure = SingleMeasure(single_score, "error", raise_error)

        with pytest.raises(ValueError, match="async error"):
            await measure.execute()

    async def test_sync_exception_propagates(self, single_score: SingleTestScore):
        """Exceptions from sync tasks should propagate."""
        def raise_error(score: SingleTestScore) -> None:
            raise RuntimeError("sync error")

        measure = SingleMeasure(single_score, "error", raise_error)

        with pytest.raises(RuntimeError, match="sync error"):
            await measure.execute()

    async def test_exception_after_score_modification(self, single_score: SingleTestScore):
        """Score modifications before exception should persist."""
        async def modify_then_fail(score: SingleTestScore) -> None:
            score.value = "modified"
            raise ValueError("after modification")

        measure = SingleMeasure(single_score, "modify_fail", modify_then_fail)

        with pytest.raises(ValueError):
            await measure.execute()

        # Modification happened before error
        assert single_score.value == "modified"


# =============================================================================
# Test: With @note Decorator
# =============================================================================


class TestSingleMeasureWithNote:
    """Tests for SingleMeasure with @note decorated functions."""

    async def test_with_note_decorator(self, single_score: SingleTestScore):
        """SingleMeasure should work with @note decorated functions."""
        @note
        async def decorated_task(score: SingleTestScore) -> None:
            score.value = "decorated"

        measure = SingleMeasure(single_score, "decorated", decorated_task)
        await measure.execute()

        assert single_score.value == "decorated"

    async def test_with_sync_note_decorator(self, single_score: SingleTestScore):
        """SingleMeasure should work with sync @note decorated functions."""
        @note
        def sync_decorated(score: SingleTestScore) -> None:
            score.value = "sync_decorated"

        measure = SingleMeasure(single_score, "sync_decorated", sync_decorated)
        await measure.execute()

        assert single_score.value == "sync_decorated"
