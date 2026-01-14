"""Tests for ChildCadenceMeasure node.

Tests cover:
- Child cadence execution
- Score merging (sync and async)
- Error propagation from child
- Different score types between parent and child
"""

from dataclasses import dataclass

import pytest

from cadence import Cadence, Score, note
from cadence.nodes.child import ChildCadenceMeasure


# =============================================================================
# Test Fixtures
# =============================================================================


@dataclass
class ParentScore(Score):
    """Parent score for child measure tests."""
    total: int = 0
    results: list[str] | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.results is None:
            self.results = []


@dataclass
class ChildScore(Score):
    """Child score for child measure tests."""
    value: int = 0
    name: str = ""


@pytest.fixture
def parent_score() -> ParentScore:
    """Provide a fresh parent score for each test."""
    score = ParentScore()
    score.__post_init__()
    return score


@pytest.fixture
def child_score() -> ChildScore:
    """Provide a fresh child score for each test."""
    score = ChildScore()
    score.__post_init__()
    return score


# =============================================================================
# Test: Basic Child Execution
# =============================================================================


class TestChildMeasureBasic:
    """Tests for basic ChildCadenceMeasure execution."""

    async def test_child_cadence_executes(self, parent_score: ParentScore):
        """Child cadence should execute."""
        child_score = ChildScore()
        child_score.__post_init__()

        @note
        async def set_value(score: ChildScore) -> None:
            score.value = 42

        child = Cadence("child", child_score).then("set", set_value)

        def merge(parent: ParentScore, child: ChildScore) -> None:
            parent.total = child.value

        measure = ChildCadenceMeasure(parent_score, "child_exec", child, merge)
        await measure.execute()

        assert parent_score.total == 42

    async def test_child_with_multiple_notes(self, parent_score: ParentScore):
        """Child cadence with multiple notes should execute in sequence."""
        child_score = ChildScore()
        child_score.__post_init__()

        @note
        async def add_10(score: ChildScore) -> None:
            score.value += 10

        @note
        async def multiply_2(score: ChildScore) -> None:
            score.value *= 2

        child = (
            Cadence("multi_child", child_score)
            .then("add", add_10)
            .then("multiply", multiply_2)
        )

        def merge(parent: ParentScore, child: ChildScore) -> None:
            parent.total = child.value

        measure = ChildCadenceMeasure(parent_score, "multi", child, merge)
        await measure.execute()

        # 0 + 10 = 10, 10 * 2 = 20
        assert parent_score.total == 20

    async def test_measure_name_property(self, parent_score: ParentScore):
        """ChildCadenceMeasure should expose its name."""
        child_score = ChildScore()
        child_score.__post_init__()
        child = Cadence("child", child_score)

        def merge(parent: ParentScore, child: ChildScore) -> None:
            pass

        measure = ChildCadenceMeasure(parent_score, "test_child_name", child, merge)

        assert measure.name == "test_child_name"


# =============================================================================
# Test: Score Merging
# =============================================================================


class TestChildMeasureMerge:
    """Tests for score merging functionality."""

    async def test_sync_merge_function(self, parent_score: ParentScore):
        """Sync merge functions should work."""
        child_score = ChildScore(value=100)
        child_score.__post_init__()
        child = Cadence("child", child_score)

        def sync_merge(parent: ParentScore, child: ChildScore) -> None:
            parent.total = child.value

        measure = ChildCadenceMeasure(parent_score, "sync_merge", child, sync_merge)
        await measure.execute()

        assert parent_score.total == 100

    async def test_async_merge_function(self, parent_score: ParentScore):
        """Async merge functions should be awaited."""
        child_score = ChildScore(value=200)
        child_score.__post_init__()
        child = Cadence("child", child_score)

        async def async_merge(parent: ParentScore, child: ChildScore) -> None:
            parent.total = child.value

        measure = ChildCadenceMeasure(parent_score, "async_merge", child, async_merge)
        await measure.execute()

        assert parent_score.total == 200

    async def test_merge_multiple_fields(self, parent_score: ParentScore):
        """Merge function can copy multiple fields."""
        child_score = ChildScore(value=50, name="child_result")
        child_score.__post_init__()
        child = Cadence("child", child_score)

        def merge_all(parent: ParentScore, child: ChildScore) -> None:
            parent.total = child.value
            parent.results.append(child.name)

        measure = ChildCadenceMeasure(parent_score, "merge_all", child, merge_all)
        await measure.execute()

        assert parent_score.total == 50
        assert parent_score.results == ["child_result"]

    async def test_merge_accumulates(self, parent_score: ParentScore):
        """Merge can accumulate values."""
        parent_score.total = 100

        child_score = ChildScore(value=50)
        child_score.__post_init__()
        child = Cadence("child", child_score)

        def accumulate_merge(parent: ParentScore, child: ChildScore) -> None:
            parent.total += child.value

        measure = ChildCadenceMeasure(parent_score, "accum", child, accumulate_merge)
        await measure.execute()

        assert parent_score.total == 150


# =============================================================================
# Test: Different Score Types
# =============================================================================


class TestChildMeasureDifferentScores:
    """Tests for different parent and child score types."""

    async def test_different_score_types(self, parent_score: ParentScore):
        """Child can have different score type than parent."""
        @dataclass
        class CustomChildScore(Score):
            items: list[int] | None = None

            def __post_init__(self) -> None:
                super().__post_init__()
                if self.items is None:
                    self.items = []

        child_score = CustomChildScore()
        child_score.__post_init__()

        @note
        async def add_items(score: CustomChildScore) -> None:
            score.items.extend([1, 2, 3])

        child = Cadence("custom_child", child_score).then("add", add_items)

        def merge(parent: ParentScore, child: CustomChildScore) -> None:
            parent.total = sum(child.items)

        measure = ChildCadenceMeasure(parent_score, "custom", child, merge)
        await measure.execute()

        assert parent_score.total == 6

    async def test_same_score_type(self, parent_score: ParentScore):
        """Child can have same score type as parent."""
        child_score = ParentScore(total=77)
        child_score.__post_init__()
        child = Cadence("same_type", child_score)

        def merge(parent: ParentScore, child: ParentScore) -> None:
            parent.total = child.total
            parent.results = child.results.copy()

        measure = ChildCadenceMeasure(parent_score, "same", child, merge)
        await measure.execute()

        assert parent_score.total == 77


# =============================================================================
# Test: Error Handling
# =============================================================================


class TestChildMeasureErrors:
    """Tests for error handling in ChildCadenceMeasure."""

    async def test_child_error_propagates(self, parent_score: ParentScore):
        """Errors in child cadence should propagate."""
        child_score = ChildScore()
        child_score.__post_init__()

        @note
        async def raise_error(score: ChildScore) -> None:
            raise ValueError("child error")

        child = Cadence("failing_child", child_score).then("fail", raise_error)

        def merge(parent: ParentScore, child: ChildScore) -> None:
            parent.total = child.value

        measure = ChildCadenceMeasure(parent_score, "child_fail", child, merge)

        with pytest.raises(Exception):  # Wrapped in NoteError
            await measure.execute()

    async def test_merge_error_propagates(self, parent_score: ParentScore):
        """Errors in merge function should propagate."""
        child_score = ChildScore(value=42)
        child_score.__post_init__()
        child = Cadence("child", child_score)

        def failing_merge(parent: ParentScore, child: ChildScore) -> None:
            raise RuntimeError("merge error")

        measure = ChildCadenceMeasure(parent_score, "merge_fail", child, failing_merge)

        with pytest.raises(RuntimeError, match="merge error"):
            await measure.execute()

    async def test_async_merge_error_propagates(self, parent_score: ParentScore):
        """Errors in async merge function should propagate."""
        child_score = ChildScore(value=42)
        child_score.__post_init__()
        child = Cadence("child", child_score)

        async def async_failing_merge(parent: ParentScore, child: ChildScore) -> None:
            raise ValueError("async merge error")

        measure = ChildCadenceMeasure(
            parent_score, "async_fail", child, async_failing_merge
        )

        with pytest.raises(ValueError, match="async merge error"):
            await measure.execute()

    async def test_child_executes_before_merge(self, parent_score: ParentScore):
        """Child should fully execute before merge is called."""
        child_score = ChildScore()
        child_score.__post_init__()
        execution_order: list[str] = []

        @note
        async def track_child(score: ChildScore) -> None:
            execution_order.append("child")
            score.value = 99

        child = Cadence("tracked", child_score).then("track", track_child)

        def tracking_merge(parent: ParentScore, child: ChildScore) -> None:
            execution_order.append("merge")
            parent.total = child.value

        measure = ChildCadenceMeasure(parent_score, "ordered", child, tracking_merge)
        await measure.execute()

        assert execution_order == ["child", "merge"]
        assert parent_score.total == 99


# =============================================================================
# Test: Child Cadence with Hooks
# =============================================================================


class TestChildMeasureWithHooks:
    """Tests for ChildCadenceMeasure with hooks."""

    async def test_child_hooks_execute(self, parent_score: ParentScore):
        """Child cadence hooks should still execute."""
        from cadence.hooks import CadenceHooks

        hook_calls: list[str] = []

        class TrackingHooks(CadenceHooks):
            async def before_cadence(self, cadence_name: str, score: Score) -> None:
                hook_calls.append(f"before:{cadence_name}")

            async def after_cadence(
                self,
                cadence_name: str,
                score: Score,
                duration: float,
                error: Exception | None = None,
            ) -> None:
                hook_calls.append(f"after:{cadence_name}")

        child_score = ChildScore()
        child_score.__post_init__()

        @note
        async def noop(score: ChildScore) -> None:
            pass

        child = (
            Cadence("hooked_child", child_score)
            .with_hooks(TrackingHooks())
            .then("noop", noop)
        )

        def merge(parent: ParentScore, child: ChildScore) -> None:
            pass

        measure = ChildCadenceMeasure(parent_score, "with_hooks", child, merge)
        await measure.execute()

        assert "before:hooked_child" in hook_calls
        assert "after:hooked_child" in hook_calls


# =============================================================================
# Test: Nested Child Cadences
# =============================================================================


class TestChildMeasureNested:
    """Tests for nested child cadences."""

    async def test_nested_child_cadences(self, parent_score: ParentScore):
        """Child cadences can contain their own child cadences."""
        # Innermost child
        inner_score = ChildScore(value=10)
        inner_score.__post_init__()
        inner_child = Cadence("inner", inner_score)

        # Middle child with nested child
        middle_score = ChildScore()
        middle_score.__post_init__()

        def inner_merge(middle: ChildScore, inner: ChildScore) -> None:
            middle.value = inner.value * 2

        middle_child = (
            Cadence("middle", middle_score)
            .child("inner_step", inner_child, inner_merge)
        )

        # Outer merge
        def outer_merge(parent: ParentScore, middle: ChildScore) -> None:
            parent.total = middle.value

        measure = ChildCadenceMeasure(parent_score, "nested", middle_child, outer_merge)
        await measure.execute()

        # 10 * 2 = 20
        assert parent_score.total == 20
