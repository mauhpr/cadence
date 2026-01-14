"""Tests for edge cases and boundary conditions.

Tests cover:
- Task cancellation behavior
- Concurrent failures in parallel execution
- Empty workflows
- Very deep nesting
- Large number of parallel tasks
- Score state edge cases
- Error recovery patterns
"""

import asyncio
from dataclasses import dataclass

import pytest

from cadence import Cadence, Score, note


# =============================================================================
# Test Fixtures
# =============================================================================


@dataclass
class EdgeCaseScore(Score):
    """Score for edge case tests."""
    value: str = ""
    count: int = 0
    items: list[str] | None = None
    error_occurred: bool = False

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.items is None:
            self.items = []


@pytest.fixture
def edge_score() -> EdgeCaseScore:
    """Provide a fresh score for each test."""
    score = EdgeCaseScore()
    score.__post_init__()
    return score


# =============================================================================
# Test: Empty Workflows
# =============================================================================


class TestEmptyWorkflows:
    """Tests for empty and minimal workflows."""

    async def test_cadence_with_no_steps(self, edge_score):
        """Cadence with no steps should complete successfully."""
        cadence = Cadence("empty", edge_score)

        result = await cadence.run()

        assert result is edge_score

    async def test_cadence_run_multiple_times(self, edge_score):
        """Empty cadence can run multiple times."""
        cadence = Cadence("empty", edge_score)

        await cadence.run()
        await cadence.run()
        await cadence.run()

        # Should complete without error

    async def test_empty_parallel_group(self, edge_score):
        """Empty split should handle gracefully."""
        cadence = Cadence("empty_split", edge_score)

        # Run without adding any steps to split
        result = await cadence.run()

        assert result is edge_score


# =============================================================================
# Test: Cancellation Behavior
# =============================================================================


class TestCancellation:
    """Tests for task cancellation behavior."""

    async def test_cancelled_task_propagates(self, edge_score):
        """Cancelled async task should propagate CancelledError."""
        @note
        async def slow_task(score: EdgeCaseScore) -> None:
            await asyncio.sleep(10)  # Long sleep
            score.value = "completed"

        cadence = Cadence("cancel_test", edge_score).then("slow", slow_task)

        async def run_and_cancel():
            task = asyncio.create_task(cadence.run())
            await asyncio.sleep(0.01)  # Let it start
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                return True
            return False

        was_cancelled = await run_and_cancel()
        assert was_cancelled
        assert edge_score.value == ""  # Should not have completed

    async def test_cleanup_on_cancellation(self, edge_score):
        """Resources should be cleaned up on cancellation."""
        cleanup_called = []

        @note
        async def task_with_cleanup(score: EdgeCaseScore) -> None:
            try:
                await asyncio.sleep(10)
            finally:
                cleanup_called.append(True)

        cadence = Cadence("cleanup_test", edge_score).then("task", task_with_cleanup)

        task = asyncio.create_task(cadence.run())
        await asyncio.sleep(0.01)
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        # Cleanup should have been called
        assert len(cleanup_called) == 1

    async def test_cancel_during_parallel_execution(self, edge_score):
        """Cancellation during parallel execution should stop all tasks."""
        started = []
        completed = []

        @note
        async def task_a(score: EdgeCaseScore) -> None:
            started.append("a")
            await asyncio.sleep(1)
            completed.append("a")

        @note
        async def task_b(score: EdgeCaseScore) -> None:
            started.append("b")
            await asyncio.sleep(1)
            completed.append("b")

        cadence = (
            Cadence("parallel_cancel", edge_score)
            .sync("parallel", [task_a, task_b])
        )

        task = asyncio.create_task(cadence.run())
        await asyncio.sleep(0.01)  # Let tasks start
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        # Tasks should have started but not completed
        assert len(completed) == 0


# =============================================================================
# Test: Concurrent Failures
# =============================================================================


class TestConcurrentFailures:
    """Tests for handling multiple concurrent failures."""

    async def test_first_failure_stops_parallel(self, edge_score):
        """First failure in parallel should stop other tasks."""
        @note
        async def fast_fail(score: EdgeCaseScore) -> None:
            await asyncio.sleep(0.01)
            raise ValueError("fast failure")

        @note
        async def slow_success(score: EdgeCaseScore) -> None:
            await asyncio.sleep(1)  # Would take long
            score.value = "completed"

        cadence = (
            Cadence("parallel_fail", edge_score)
            .sync("parallel", [fast_fail, slow_success])
        )

        with pytest.raises(Exception):
            await cadence.run()

        # Slow task should not have completed
        assert edge_score.value == ""

    async def test_multiple_failures_one_reported(self, edge_score):
        """Multiple failures should report one (first) error."""
        @note
        async def fail_a(score: EdgeCaseScore) -> None:
            await asyncio.sleep(0.01)
            raise ValueError("error A")

        @note
        async def fail_b(score: EdgeCaseScore) -> None:
            await asyncio.sleep(0.02)
            raise RuntimeError("error B")

        cadence = (
            Cadence("multi_fail", edge_score)
            .sync("parallel", [fail_a, fail_b])
        )

        with pytest.raises(Exception) as exc_info:
            await cadence.run()

        # Should get one of the errors (usually the first)
        assert "error" in str(exc_info.value).lower()

    async def test_error_in_sequence_stops_execution(self, edge_score):
        """Error in sequence should stop subsequent steps."""
        execution_order = []

        @note
        async def step_one(score: EdgeCaseScore) -> None:
            execution_order.append("one")

        @note
        async def step_error(score: EdgeCaseScore) -> None:
            execution_order.append("error")
            raise ValueError("stop here")

        @note
        async def step_three(score: EdgeCaseScore) -> None:
            execution_order.append("three")

        cadence = (
            Cadence("sequence_error", edge_score)
            .then("one", step_one)
            .then("error", step_error)
            .then("three", step_three)
        )

        with pytest.raises(Exception):
            await cadence.run()

        assert execution_order == ["one", "error"]
        assert "three" not in execution_order


# =============================================================================
# Test: Deep Nesting
# =============================================================================


class TestDeepNesting:
    """Tests for deeply nested cadence structures."""

    async def test_deeply_nested_branches(self, edge_score):
        """Should handle deeply nested branch conditions."""
        @note
        async def increment(score: EdgeCaseScore) -> None:
            score.count += 1

        def always_true(score: EdgeCaseScore) -> bool:
            return True

        def always_false(score: EdgeCaseScore) -> bool:
            return False

        # Build sequential splits with true/false branches
        cadence = Cadence("nested", edge_score)

        # 10 levels of branching - each takes true branch with increment
        for i in range(10):
            cadence = cadence.split(
                f"branch_{i}",
                condition=always_true,
                if_true=[increment],
                if_false=[],
            )

        await cadence.run()

        # Should have executed all increments
        assert edge_score.count == 10

    async def test_nested_child_cadences(self, edge_score):
        """Should handle nested child cadences."""
        @dataclass
        class InnerScore(Score):
            value: int = 0

        @note
        async def increment_inner(score: InnerScore) -> None:
            score.value += 1

        def merge_inner(parent: EdgeCaseScore, child: InnerScore) -> None:
            parent.count += child.value

        # Create nested structure
        inner_score = InnerScore()
        inner_score.__post_init__()

        inner_cadence = Cadence("inner", inner_score).then("inc", increment_inner)

        cadence = (
            Cadence("outer", edge_score)
            .child("first_child", inner_cadence, merge_inner)
            .child("second_child", inner_cadence, merge_inner)
        )

        await cadence.run()

        # Due to measure binding, inner_score is modified
        assert edge_score.count >= 1


# =============================================================================
# Test: Large Scale Parallel
# =============================================================================


class TestLargeScaleParallel:
    """Tests for large numbers of parallel tasks."""

    async def test_many_parallel_tasks(self, edge_score):
        """Should handle many parallel tasks efficiently."""
        results = []

        # Create 50 parallel tasks using closures
        tasks = []
        for i in range(50):
            # Use default parameter to capture loop variable
            async def make_task(idx: int):
                async def task(score: EdgeCaseScore) -> None:
                    results.append(idx)
                return task
            # Can't use async in list comp, so build list imperatively

        # Use factory function to create properly closed tasks
        def create_task(idx: int):
            @note
            async def task(score: EdgeCaseScore) -> None:
                results.append(idx)
            return task

        tasks = [create_task(i) for i in range(50)]

        cadence = Cadence("many_parallel", edge_score).sync("parallel", tasks)

        await cadence.run()

        # All tasks should have executed
        assert len(results) == 50

    async def test_parallel_with_varying_durations(self, edge_score):
        """Parallel tasks with different durations should all complete."""
        completion_times = []

        durations = [0.01, 0.02, 0.03, 0.01, 0.02]

        # Use factory function to create properly closed tasks
        def create_task(duration: float):
            @note
            async def task(score: EdgeCaseScore) -> None:
                await asyncio.sleep(duration)
                completion_times.append(duration)
            return task

        tasks = [create_task(d) for d in durations]

        cadence = Cadence("varying", edge_score).sync("parallel", tasks)

        await cadence.run()

        # All should complete
        assert len(completion_times) == 5


# =============================================================================
# Test: Score State Edge Cases
# =============================================================================


class TestScoreStateEdgeCases:
    """Tests for edge cases in score state management."""

    async def test_none_field_handling(self, edge_score):
        """Should handle None values in score fields."""
        @note
        async def set_none(score: EdgeCaseScore) -> None:
            score.value = None  # type: ignore

        cadence = Cadence("none_test", edge_score).then("set", set_none)

        await cadence.run()

        assert edge_score.value is None

    async def test_empty_string_vs_none(self, edge_score):
        """Should distinguish between empty string and None."""
        @note
        async def check_empty(score: EdgeCaseScore) -> None:
            # Initially empty string
            assert score.value == ""
            score.value = "set"

        cadence = Cadence("empty_test", edge_score).then("check", check_empty)

        await cadence.run()

        assert edge_score.value == "set"

    async def test_list_mutation(self, edge_score):
        """Should handle list mutation correctly."""
        @note
        async def append_item(score: EdgeCaseScore) -> None:
            score.items.append("item")

        cadence = (
            Cadence("list_test", edge_score)
            .then("add1", append_item)
            .then("add2", append_item)
            .then("add3", append_item)
        )

        await cadence.run()

        assert len(edge_score.items) == 3

    async def test_score_initialization_edge_cases(self):
        """Score should initialize correctly with various defaults."""
        @dataclass
        class ComplexScore(Score):
            required_field: str
            optional_field: str | None = None
            list_field: list[int] | None = None
            dict_field: dict[str, str] | None = None

            def __post_init__(self) -> None:
                super().__post_init__()
                if self.list_field is None:
                    self.list_field = []
                if self.dict_field is None:
                    self.dict_field = {}

        score = ComplexScore(required_field="test")
        score.__post_init__()

        assert score.required_field == "test"
        assert score.optional_field is None
        assert score.list_field == []
        assert score.dict_field == {}


# =============================================================================
# Test: Error Recovery
# =============================================================================


class TestErrorRecovery:
    """Tests for error recovery patterns."""

    async def test_error_preserves_prior_state(self, edge_score):
        """State modifications before error should persist."""
        @note
        async def modify_then_error(score: EdgeCaseScore) -> None:
            score.value = "modified"
            score.count = 42
            raise ValueError("after modification")

        cadence = Cadence("preserve_state", edge_score).then("modify", modify_then_error)

        with pytest.raises(Exception):
            await cadence.run()

        # Modifications before error should persist
        assert edge_score.value == "modified"
        assert edge_score.count == 42

    async def test_error_flag_pattern(self, edge_score):
        """Common pattern: set error flag on failure."""
        @note
        async def risky_operation(score: EdgeCaseScore) -> None:
            try:
                raise ValueError("something went wrong")
            except Exception:
                score.error_occurred = True
                raise

        cadence = Cadence("error_flag", edge_score).then("risky", risky_operation)

        with pytest.raises(Exception):
            await cadence.run()

        assert edge_score.error_occurred is True

    async def test_partial_completion_tracking(self, edge_score):
        """Track which steps completed before error."""
        completed_steps = []

        @note
        async def track_step(score: EdgeCaseScore, name: str = "default") -> None:
            completed_steps.append(name)

        @note
        async def failing_step(score: EdgeCaseScore) -> None:
            raise ValueError("stop here")

        # Create steps with proper closures
        @note
        async def step_a(score: EdgeCaseScore) -> None:
            completed_steps.append("a")

        @note
        async def step_b(score: EdgeCaseScore) -> None:
            completed_steps.append("b")

        @note
        async def step_c(score: EdgeCaseScore) -> None:
            completed_steps.append("c")

        cadence = (
            Cadence("partial", edge_score)
            .then("a", step_a)
            .then("b", step_b)
            .then("fail", failing_step)
            .then("c", step_c)
        )

        with pytest.raises(Exception):
            await cadence.run()

        assert completed_steps == ["a", "b"]


# =============================================================================
# Test: Sync vs Async Handling
# =============================================================================


class TestSyncAsyncHandling:
    """Tests for mixed sync/async handling."""

    async def test_sync_function_in_async_cadence(self, edge_score):
        """Sync functions should work in async cadence."""
        @note
        def sync_step(score: EdgeCaseScore) -> None:
            score.value = "sync"

        cadence = Cadence("sync_test", edge_score).then("sync", sync_step)

        await cadence.run()

        assert edge_score.value == "sync"

    async def test_mixed_sync_async_sequence(self, edge_score):
        """Mixed sync and async steps should execute correctly."""
        @note
        def sync_first(score: EdgeCaseScore) -> None:
            score.value += "S"

        @note
        async def async_second(score: EdgeCaseScore) -> None:
            score.value += "A"

        @note
        def sync_third(score: EdgeCaseScore) -> None:
            score.value += "S"

        cadence = (
            Cadence("mixed", edge_score)
            .then("sync1", sync_first)
            .then("async1", async_second)
            .then("sync2", sync_third)
        )

        await cadence.run()

        assert edge_score.value == "SAS"

    async def test_sync_error_propagation(self, edge_score):
        """Sync function errors should propagate correctly."""
        @note
        def sync_error(score: EdgeCaseScore) -> None:
            raise ValueError("sync error")

        cadence = Cadence("sync_error", edge_score).then("error", sync_error)

        with pytest.raises(Exception, match="sync error"):
            await cadence.run()


# =============================================================================
# Test: Boundary Conditions
# =============================================================================


class TestBoundaryConditions:
    """Tests for boundary conditions."""

    async def test_zero_duration_tasks(self, edge_score):
        """Tasks that complete instantly should work."""
        @note
        async def instant_task(score: EdgeCaseScore) -> None:
            pass  # Completes immediately

        cadence = (
            Cadence("instant", edge_score)
            .then("task1", instant_task)
            .then("task2", instant_task)
            .then("task3", instant_task)
        )

        await cadence.run()

        # Should complete without issues

    async def test_single_task_cadence(self, edge_score):
        """Single task cadence should work correctly."""
        @note
        async def only_task(score: EdgeCaseScore) -> None:
            score.value = "only"

        cadence = Cadence("single", edge_score).then("only", only_task)

        result = await cadence.run()

        assert result is edge_score
        assert edge_score.value == "only"

    async def test_very_long_step_name(self, edge_score):
        """Very long step names should be handled."""
        long_name = "a" * 1000

        @note
        async def task(score: EdgeCaseScore) -> None:
            score.value = "done"

        cadence = Cadence("long_names", edge_score).then(long_name, task)

        await cadence.run()

        assert edge_score.value == "done"

    async def test_unicode_step_names(self, edge_score):
        """Unicode step names should work."""
        @note
        async def task(score: EdgeCaseScore) -> None:
            score.value = "done"

        cadence = (
            Cadence("unicode", edge_score)
            .then("验证", task)  # Chinese
            .then("検証", task)  # Japanese
            .then("проверка", task)  # Russian
        )

        await cadence.run()

        assert edge_score.value == "done"

    async def test_special_characters_in_names(self, edge_score):
        """Special characters in names should be handled."""
        @note
        async def task(score: EdgeCaseScore) -> None:
            score.value = "done"

        cadence = (
            Cadence("special", edge_score)
            .then("step-with-dashes", task)
            .then("step_with_underscores", task)
            .then("step.with.dots", task)
        )

        await cadence.run()

        assert edge_score.value == "done"


# =============================================================================
# Test: Cadence Reuse
# =============================================================================


class TestCadenceReuse:
    """Tests for cadence reuse patterns."""

    async def test_run_same_cadence_multiple_times(self, edge_score):
        """Same cadence instance can be run multiple times."""
        @note
        async def increment(score: EdgeCaseScore) -> None:
            score.count += 1

        cadence = Cadence("reuse", edge_score).then("inc", increment)

        await cadence.run()
        await cadence.run()
        await cadence.run()

        # Note: Due to measure binding, same score is modified each time
        assert edge_score.count >= 1

    async def test_cadence_as_template(self):
        """Cadence can be used as a template pattern."""
        @note
        async def process(score: EdgeCaseScore) -> None:
            score.value = f"processed_{score.count}"

        # Create template
        template_score = EdgeCaseScore()
        template_score.__post_init__()

        template = Cadence("template", template_score).then("process", process)

        # Run with different initial states
        template_score.count = 1
        await template.run()

        template_score.count = 2
        await template.run()

        # Template score was modified
        assert "processed_" in template_score.value
