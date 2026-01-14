"""Tests for BranchMeasure node.

Tests cover:
- Condition evaluation (sync and async)
- True branch execution
- False branch execution
- Empty branches
- Sequential vs parallel branch execution
- Error propagation
"""

from dataclasses import dataclass

import pytest

from cadence import Score, note
from cadence.nodes.branch import BranchMeasure


# =============================================================================
# Test Fixtures
# =============================================================================


@dataclass
class BranchTestScore(Score):
    """Score for branch measure tests."""
    value: str = ""
    count: int = 0
    flag: bool = True


@pytest.fixture
def branch_score() -> BranchTestScore:
    """Provide a fresh score for each test."""
    score = BranchTestScore()
    score.__post_init__()
    return score


# =============================================================================
# Test: Condition Evaluation
# =============================================================================


class TestBranchCondition:
    """Tests for condition evaluation."""

    async def test_sync_condition_true(self, branch_score: BranchTestScore):
        """Sync condition returning True should execute if_tasks."""
        def condition(score: BranchTestScore) -> bool:
            return True

        async def set_value(score: BranchTestScore) -> None:
            score.value = "true_branch"

        measure = BranchMeasure(
            branch_score,
            "sync_true",
            condition=condition,
            if_tasks=[set_value],
            else_tasks=[],
        )
        await measure.execute()

        assert branch_score.value == "true_branch"

    async def test_sync_condition_false(self, branch_score: BranchTestScore):
        """Sync condition returning False should execute else_tasks."""
        def condition(score: BranchTestScore) -> bool:
            return False

        async def if_task(score: BranchTestScore) -> None:
            score.value = "if"

        async def else_task(score: BranchTestScore) -> None:
            score.value = "else"

        measure = BranchMeasure(
            branch_score,
            "sync_false",
            condition=condition,
            if_tasks=[if_task],
            else_tasks=[else_task],
        )
        await measure.execute()

        assert branch_score.value == "else"

    async def test_async_condition(self, branch_score: BranchTestScore):
        """Async conditions should be awaited."""
        async def async_condition(score: BranchTestScore) -> bool:
            return score.flag

        async def set_value(score: BranchTestScore) -> None:
            score.value = "async_true"

        measure = BranchMeasure(
            branch_score,
            "async_cond",
            condition=async_condition,
            if_tasks=[set_value],
        )
        await measure.execute()

        assert branch_score.value == "async_true"

    async def test_condition_based_on_score(self, branch_score: BranchTestScore):
        """Condition should have access to score state."""
        branch_score.count = 10

        def check_count(score: BranchTestScore) -> bool:
            return score.count > 5

        async def set_high(score: BranchTestScore) -> None:
            score.value = "high"

        async def set_low(score: BranchTestScore) -> None:
            score.value = "low"

        measure = BranchMeasure(
            branch_score,
            "count_check",
            condition=check_count,
            if_tasks=[set_high],
            else_tasks=[set_low],
        )
        await measure.execute()

        assert branch_score.value == "high"

    async def test_truthy_values_as_true(self, branch_score: BranchTestScore):
        """Any truthy value should be treated as True."""
        def return_string(score: BranchTestScore) -> str:
            return "truthy"

        async def set_value(score: BranchTestScore) -> None:
            score.value = "truthy_works"

        measure = BranchMeasure(
            branch_score,
            "truthy",
            condition=return_string,
            if_tasks=[set_value],
        )
        await measure.execute()

        assert branch_score.value == "truthy_works"

    async def test_falsy_values_as_false(self, branch_score: BranchTestScore):
        """Falsy values (0, "", None) should be treated as False."""
        def return_zero(score: BranchTestScore) -> int:
            return 0

        async def if_task(score: BranchTestScore) -> None:
            score.value = "if"

        async def else_task(score: BranchTestScore) -> None:
            score.value = "else"

        measure = BranchMeasure(
            branch_score,
            "falsy",
            condition=return_zero,
            if_tasks=[if_task],
            else_tasks=[else_task],
        )
        await measure.execute()

        assert branch_score.value == "else"


# =============================================================================
# Test: Branch Execution
# =============================================================================


class TestBranchExecution:
    """Tests for branch task execution."""

    async def test_multiple_if_tasks(self, branch_score: BranchTestScore):
        """Multiple if_tasks should execute in sequence."""
        def condition(score: BranchTestScore) -> bool:
            return True

        async def append_a(score: BranchTestScore) -> None:
            score.value += "A"

        async def append_b(score: BranchTestScore) -> None:
            score.value += "B"

        measure = BranchMeasure(
            branch_score,
            "multi_if",
            condition=condition,
            if_tasks=[append_a, append_b],
        )
        await measure.execute()

        assert branch_score.value == "AB"

    async def test_multiple_else_tasks(self, branch_score: BranchTestScore):
        """Multiple else_tasks should execute in sequence."""
        def condition(score: BranchTestScore) -> bool:
            return False

        async def append_x(score: BranchTestScore) -> None:
            score.value += "X"

        async def append_y(score: BranchTestScore) -> None:
            score.value += "Y"

        measure = BranchMeasure(
            branch_score,
            "multi_else",
            condition=condition,
            if_tasks=[],
            else_tasks=[append_x, append_y],
        )
        await measure.execute()

        assert branch_score.value == "XY"

    async def test_empty_if_tasks(self, branch_score: BranchTestScore):
        """Empty if_tasks should do nothing."""
        def condition(score: BranchTestScore) -> bool:
            return True

        measure = BranchMeasure(
            branch_score,
            "empty_if",
            condition=condition,
            if_tasks=[],
            else_tasks=[],
        )
        result = await measure.execute()

        assert result is None
        assert branch_score.value == ""

    async def test_none_else_tasks(self, branch_score: BranchTestScore):
        """None else_tasks should be treated as empty list."""
        def condition(score: BranchTestScore) -> bool:
            return False

        measure = BranchMeasure(
            branch_score,
            "none_else",
            condition=condition,
            if_tasks=[],
            else_tasks=None,
        )
        result = await measure.execute()

        assert result is None

    async def test_mixed_sync_async_tasks(self, branch_score: BranchTestScore):
        """Branch should handle mix of sync and async tasks."""
        def condition(score: BranchTestScore) -> bool:
            return True

        def sync_task(score: BranchTestScore) -> None:
            score.value += "S"

        async def async_task(score: BranchTestScore) -> None:
            score.value += "A"

        measure = BranchMeasure(
            branch_score,
            "mixed",
            condition=condition,
            if_tasks=[sync_task, async_task],
        )
        await measure.execute()

        assert branch_score.value == "SA"


# =============================================================================
# Test: Parallel Branch Execution
# =============================================================================


class TestBranchParallel:
    """Tests for parallel branch execution."""

    async def test_parallel_if_tasks(self, branch_score: BranchTestScore):
        """Parallel mode should run if_tasks in parallel."""
        def condition(score: BranchTestScore) -> bool:
            return True

        # Use non-conflicting modifications
        async def increment_count(score: BranchTestScore) -> None:
            pass  # No modification to avoid conflict

        async def noop(score: BranchTestScore) -> None:
            pass

        measure = BranchMeasure(
            branch_score,
            "parallel",
            condition=condition,
            if_tasks=[increment_count, noop],
            parallel=True,
        )
        result = await measure.execute()

        # Should complete without error
        assert result is None

    async def test_sequential_is_default(self, branch_score: BranchTestScore):
        """Sequential execution should be the default."""
        def condition(score: BranchTestScore) -> bool:
            return True

        async def set_a(score: BranchTestScore) -> None:
            score.value = "A"

        async def append_b(score: BranchTestScore) -> None:
            score.value += "B"

        measure = BranchMeasure(
            branch_score,
            "sequential_default",
            condition=condition,
            if_tasks=[set_a, append_b],
            # parallel not specified, defaults to False
        )
        await measure.execute()

        # Sequential order preserved
        assert branch_score.value == "AB"


# =============================================================================
# Test: Error Handling
# =============================================================================


class TestBranchErrors:
    """Tests for error handling in BranchMeasure."""

    async def test_condition_error_propagates(self, branch_score: BranchTestScore):
        """Error in condition should propagate."""
        def failing_condition(score: BranchTestScore) -> bool:
            raise ValueError("condition error")

        async def noop(score: BranchTestScore) -> None:
            pass

        measure = BranchMeasure(
            branch_score,
            "cond_error",
            condition=failing_condition,
            if_tasks=[noop],
        )

        with pytest.raises(ValueError, match="condition error"):
            await measure.execute()

    async def test_if_task_error_propagates(self, branch_score: BranchTestScore):
        """Error in if_task should propagate."""
        def condition(score: BranchTestScore) -> bool:
            return True

        async def failing_task(score: BranchTestScore) -> None:
            raise RuntimeError("task error")

        measure = BranchMeasure(
            branch_score,
            "if_error",
            condition=condition,
            if_tasks=[failing_task],
        )

        with pytest.raises(RuntimeError, match="task error"):
            await measure.execute()

    async def test_else_task_error_propagates(self, branch_score: BranchTestScore):
        """Error in else_task should propagate."""
        def condition(score: BranchTestScore) -> bool:
            return False

        async def failing_task(score: BranchTestScore) -> None:
            raise RuntimeError("else error")

        measure = BranchMeasure(
            branch_score,
            "else_error",
            condition=condition,
            if_tasks=[],
            else_tasks=[failing_task],
        )

        with pytest.raises(RuntimeError, match="else error"):
            await measure.execute()

    async def test_partial_execution_on_error(self, branch_score: BranchTestScore):
        """Tasks before error should have run."""
        def condition(score: BranchTestScore) -> bool:
            return True

        async def set_value(score: BranchTestScore) -> None:
            score.value = "set"

        async def raise_error(score: BranchTestScore) -> None:
            raise ValueError("after set")

        measure = BranchMeasure(
            branch_score,
            "partial",
            condition=condition,
            if_tasks=[set_value, raise_error],
        )

        with pytest.raises(ValueError):
            await measure.execute()

        # First task ran
        assert branch_score.value == "set"


# =============================================================================
# Test: With @note Decorator
# =============================================================================


class TestBranchWithNote:
    """Tests for BranchMeasure with @note decorated functions."""

    async def test_with_note_decorators(self, branch_score: BranchTestScore):
        """BranchMeasure should work with @note decorated functions."""
        def condition(score: BranchTestScore) -> bool:
            return True

        @note
        async def note_task(score: BranchTestScore) -> None:
            score.value = "noted"

        measure = BranchMeasure(
            branch_score,
            "noted",
            condition=condition,
            if_tasks=[note_task],
        )
        await measure.execute()

        assert branch_score.value == "noted"


# =============================================================================
# Test: Measure Properties
# =============================================================================


class TestBranchProperties:
    """Tests for BranchMeasure properties."""

    async def test_measure_name_property(self, branch_score: BranchTestScore):
        """BranchMeasure should expose its name."""
        def condition(score: BranchTestScore) -> bool:
            return True

        measure = BranchMeasure(
            branch_score,
            "test_branch_name",
            condition=condition,
            if_tasks=[],
        )

        assert measure.name == "test_branch_name"
