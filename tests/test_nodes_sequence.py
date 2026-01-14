"""Tests for SequenceMeasure node.

Tests cover:
- Sequential execution order
- Mix of sync and async tasks
- Error propagation
- Empty task lists
- Score accumulation
"""

from dataclasses import dataclass

import pytest

from cadence import Score, note
from cadence.nodes.sequence import SequenceMeasure


# =============================================================================
# Test Fixtures
# =============================================================================


@dataclass
class SequenceTestScore(Score):
    """Score for sequence measure tests."""
    value: str = ""
    count: int = 0
    order: list[str] | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.order is None:
            self.order = []


@pytest.fixture
def sequence_score() -> SequenceTestScore:
    """Provide a fresh score for each test."""
    score = SequenceTestScore()
    score.__post_init__()
    return score


# =============================================================================
# Test: Basic Sequential Execution
# =============================================================================


class TestSequenceMeasureBasic:
    """Tests for basic SequenceMeasure execution."""

    async def test_execute_single_task(self, sequence_score: SequenceTestScore):
        """SequenceMeasure should execute a single task."""
        async def set_value(score: SequenceTestScore) -> None:
            score.value = "single"

        measure = SequenceMeasure(sequence_score, "single", [set_value])
        result = await measure.execute()

        assert result is None
        assert sequence_score.value == "single"

    async def test_execute_multiple_tasks(self, sequence_score: SequenceTestScore):
        """SequenceMeasure should execute multiple tasks."""
        async def append_a(score: SequenceTestScore) -> None:
            score.value += "A"

        async def append_b(score: SequenceTestScore) -> None:
            score.value += "B"

        async def append_c(score: SequenceTestScore) -> None:
            score.value += "C"

        measure = SequenceMeasure(
            sequence_score, "multi", [append_a, append_b, append_c]
        )
        await measure.execute()

        assert sequence_score.value == "ABC"

    async def test_execute_empty_list(self, sequence_score: SequenceTestScore):
        """SequenceMeasure should handle empty task list."""
        measure = SequenceMeasure(sequence_score, "empty", [])
        result = await measure.execute()

        assert result is None
        assert sequence_score.value == ""

    async def test_measure_name_property(self, sequence_score: SequenceTestScore):
        """SequenceMeasure should expose its name."""
        async def noop(score: SequenceTestScore) -> None:
            pass

        measure = SequenceMeasure(sequence_score, "test_name", [noop])

        assert measure.name == "test_name"


# =============================================================================
# Test: Execution Order
# =============================================================================


class TestSequenceMeasureOrder:
    """Tests for sequential execution order."""

    async def test_tasks_execute_in_order(self, sequence_score: SequenceTestScore):
        """Tasks should execute in the order provided."""
        async def track_1(score: SequenceTestScore) -> None:
            score.order.append("1")

        async def track_2(score: SequenceTestScore) -> None:
            score.order.append("2")

        async def track_3(score: SequenceTestScore) -> None:
            score.order.append("3")

        measure = SequenceMeasure(
            sequence_score, "ordered", [track_1, track_2, track_3]
        )
        await measure.execute()

        assert sequence_score.order == ["1", "2", "3"]

    async def test_later_tasks_see_earlier_modifications(
        self, sequence_score: SequenceTestScore
    ):
        """Later tasks should see modifications from earlier tasks."""
        async def set_value(score: SequenceTestScore) -> None:
            score.value = "initial"

        async def append_suffix(score: SequenceTestScore) -> None:
            score.value += "_modified"

        measure = SequenceMeasure(
            sequence_score, "chain", [set_value, append_suffix]
        )
        await measure.execute()

        assert sequence_score.value == "initial_modified"


# =============================================================================
# Test: Mixed Sync and Async
# =============================================================================


class TestSequenceMeasureMixed:
    """Tests for mixed sync/async task execution."""

    async def test_sync_tasks(self, sequence_score: SequenceTestScore):
        """SequenceMeasure should execute sync tasks."""
        def sync_append_a(score: SequenceTestScore) -> None:
            score.value += "A"

        def sync_append_b(score: SequenceTestScore) -> None:
            score.value += "B"

        measure = SequenceMeasure(
            sequence_score, "sync", [sync_append_a, sync_append_b]
        )
        await measure.execute()

        assert sequence_score.value == "AB"

    async def test_mixed_sync_async_tasks(self, sequence_score: SequenceTestScore):
        """SequenceMeasure should handle mix of sync and async tasks."""
        def sync_append_a(score: SequenceTestScore) -> None:
            score.value += "A"

        async def async_append_b(score: SequenceTestScore) -> None:
            score.value += "B"

        def sync_append_c(score: SequenceTestScore) -> None:
            score.value += "C"

        async def async_append_d(score: SequenceTestScore) -> None:
            score.value += "D"

        measure = SequenceMeasure(
            sequence_score,
            "mixed",
            [sync_append_a, async_append_b, sync_append_c, async_append_d],
        )
        await measure.execute()

        assert sequence_score.value == "ABCD"


# =============================================================================
# Test: Error Handling
# =============================================================================


class TestSequenceMeasureErrors:
    """Tests for error handling in SequenceMeasure."""

    async def test_error_stops_execution(self, sequence_score: SequenceTestScore):
        """Error in a task should stop execution of remaining tasks."""
        async def append_a(score: SequenceTestScore) -> None:
            score.value += "A"

        async def raise_error(score: SequenceTestScore) -> None:
            raise ValueError("error in middle")

        async def append_b(score: SequenceTestScore) -> None:
            score.value += "B"

        measure = SequenceMeasure(
            sequence_score, "error", [append_a, raise_error, append_b]
        )

        with pytest.raises(ValueError, match="error in middle"):
            await measure.execute()

        # Only first task ran
        assert sequence_score.value == "A"

    async def test_sync_error_propagates(self, sequence_score: SequenceTestScore):
        """Sync task errors should propagate."""
        def raise_error(score: SequenceTestScore) -> None:
            raise RuntimeError("sync error")

        measure = SequenceMeasure(sequence_score, "sync_error", [raise_error])

        with pytest.raises(RuntimeError, match="sync error"):
            await measure.execute()

    async def test_error_in_first_task(self, sequence_score: SequenceTestScore):
        """Error in first task should propagate immediately."""
        async def raise_error(score: SequenceTestScore) -> None:
            raise ValueError("first task error")

        async def append_a(score: SequenceTestScore) -> None:
            score.value += "A"

        measure = SequenceMeasure(
            sequence_score, "first_error", [raise_error, append_a]
        )

        with pytest.raises(ValueError, match="first task error"):
            await measure.execute()

        # No tasks ran after error
        assert sequence_score.value == ""

    async def test_error_preserves_prior_modifications(
        self, sequence_score: SequenceTestScore
    ):
        """Modifications before error should persist."""
        async def modify_count(score: SequenceTestScore) -> None:
            score.count = 42

        async def raise_error(score: SequenceTestScore) -> None:
            raise ValueError("after modification")

        measure = SequenceMeasure(
            sequence_score, "preserve", [modify_count, raise_error]
        )

        with pytest.raises(ValueError):
            await measure.execute()

        # Prior modification persists
        assert sequence_score.count == 42


# =============================================================================
# Test: With @note Decorator
# =============================================================================


class TestSequenceMeasureWithNote:
    """Tests for SequenceMeasure with @note decorated functions."""

    async def test_with_note_decorators(self, sequence_score: SequenceTestScore):
        """SequenceMeasure should work with @note decorated functions."""
        @note
        async def note_append_a(score: SequenceTestScore) -> None:
            score.value += "A"

        @note
        async def note_append_b(score: SequenceTestScore) -> None:
            score.value += "B"

        measure = SequenceMeasure(
            sequence_score, "notes", [note_append_a, note_append_b]
        )
        await measure.execute()

        assert sequence_score.value == "AB"

    async def test_with_mixed_note_and_plain(self, sequence_score: SequenceTestScore):
        """SequenceMeasure should work with mix of @note and plain functions."""
        @note
        async def note_task(score: SequenceTestScore) -> None:
            score.value += "N"

        async def plain_task(score: SequenceTestScore) -> None:
            score.value += "P"

        measure = SequenceMeasure(
            sequence_score, "mixed_notes", [note_task, plain_task, note_task]
        )
        await measure.execute()

        assert sequence_score.value == "NPN"


# =============================================================================
# Test: Accumulation Patterns
# =============================================================================


class TestSequenceMeasureAccumulation:
    """Tests for common score accumulation patterns."""

    async def test_counter_accumulation(self, sequence_score: SequenceTestScore):
        """Tasks can accumulate values in counters."""
        async def increment(score: SequenceTestScore) -> None:
            score.count += 1

        # Create 5 increment tasks
        tasks = [increment for _ in range(5)]

        measure = SequenceMeasure(sequence_score, "counter", tasks)
        await measure.execute()

        assert sequence_score.count == 5

    async def test_string_accumulation(self, sequence_score: SequenceTestScore):
        """Tasks can accumulate strings."""
        letters = ["H", "E", "L", "L", "O"]
        tasks = []

        for letter in letters:
            # Create closure correctly
            async def append_letter(score: SequenceTestScore, l: str = letter) -> None:
                score.value += l
            tasks.append(append_letter)

        measure = SequenceMeasure(sequence_score, "string", tasks)
        await measure.execute()

        assert sequence_score.value == "HELLO"
