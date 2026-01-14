"""Tests for parallel execution with copy-on-write score."""

import pytest
import asyncio
from dataclasses import dataclass, field
from typing import List, Optional

from cadence import Cadence, Score, note, MergeConflict, MergeStrategy, NoteError


@dataclass
class ParallelTestScore(Score):
    """Score for parallel execution tests."""
    task_a_result: Optional[str] = None
    task_b_result: Optional[str] = None
    task_c_result: Optional[str] = None
    shared_list: Optional[List[str]] = None
    shared_value: Optional[str] = None


@note
async def task_a(score: ParallelTestScore) -> None:
    """Task that sets task_a_result."""
    await asyncio.sleep(0.01)
    score.task_a_result = "A"


@note
async def task_b(score: ParallelTestScore) -> None:
    """Task that sets task_b_result."""
    await asyncio.sleep(0.01)
    score.task_b_result = "B"


@note
async def task_c(score: ParallelTestScore) -> None:
    """Task that sets task_c_result."""
    await asyncio.sleep(0.01)
    score.task_c_result = "C"


@note
async def append_a(score: ParallelTestScore) -> None:
    """Task that appends to shared list."""
    if score.shared_list is None:
        score.shared_list = []
    score.shared_list.append("A")


@note
async def append_b(score: ParallelTestScore) -> None:
    """Task that appends to shared list."""
    if score.shared_list is None:
        score.shared_list = []
    score.shared_list.append("B")


@note
async def set_shared_1(score: ParallelTestScore) -> None:
    """Task that sets shared value to 1."""
    score.shared_value = "value1"


@note
async def set_shared_2(score: ParallelTestScore) -> None:
    """Task that sets shared value to 2."""
    score.shared_value = "value2"


class TestParallelExecution:
    """Test parallel measure execution with score isolation."""

    @pytest.mark.asyncio
    async def test_sync_different_fields(self):
        """Test parallel tasks writing to different fields."""
        score = ParallelTestScore()
        score.__post_init__()

        cadence = (
            Cadence("test", score)
            .sync("tasks", [task_a, task_b, task_c])
        )

        result = await cadence.run()

        assert result.task_a_result == "A"
        assert result.task_b_result == "B"
        assert result.task_c_result == "C"

    @pytest.mark.asyncio
    async def test_sync_conflict_detection(self):
        """Test that conflicting writes are detected."""
        score = ParallelTestScore()
        score.__post_init__()

        cadence = (
            Cadence("test", score)
            .sync("tasks", [set_shared_1, set_shared_2])
        )

        # MergeConflict is wrapped in NoteError by Cadence.run()
        with pytest.raises(NoteError) as exc_info:
            await cadence.run()

        # The original MergeConflict should be the cause
        assert isinstance(exc_info.value.original_error, MergeConflict)
        assert exc_info.value.original_error.field == "shared_value"

    @pytest.mark.asyncio
    async def test_sync_isolation(self):
        """Test that parallel tasks don't see each other's changes."""
        changes_seen = []

        @note
        async def check_isolation(score: ParallelTestScore) -> None:
            # Record what we see at start
            changes_seen.append({
                "a": score.task_a_result,
                "b": score.task_b_result,
            })
            await asyncio.sleep(0.02)
            # Set our value
            score.task_a_result = "from_check"

        score = ParallelTestScore()
        score.__post_init__()

        cadence = (
            Cadence("test", score)
            .sync("tasks", [check_isolation, task_b])
        )

        # This should work - different fields
        await cadence.run()

        # Each task should have seen None for the other's field
        assert all(c["a"] is None for c in changes_seen)
        assert all(c["b"] is None for c in changes_seen)


class TestMergeStrategies:
    """Test different merge strategies in parallel execution."""

    @pytest.mark.asyncio
    async def test_smart_merge_lists(self):
        """Test smart merge combines lists from parallel tasks."""
        score = ParallelTestScore()
        score.__post_init__()

        # Custom parallel node would be needed for custom strategy
        # For now, test the merge strategy directly
        from cadence.score import merge_snapshots

        snap1 = score._snapshot()
        snap1.shared_list = ["A"]

        snap2 = score._snapshot()
        snap2.shared_list = ["B"]

        merge_snapshots(score, [snap1, snap2], MergeStrategy.smart_merge)

        assert score.shared_list == ["A", "B"]

    @pytest.mark.asyncio
    async def test_last_write_wins(self):
        """Test last_write_wins ignores conflicts."""
        score = ParallelTestScore()
        score.__post_init__()

        from cadence.score import merge_snapshots

        snap1 = score._snapshot()
        snap1.shared_value = "first"

        snap2 = score._snapshot()
        snap2.shared_value = "second"

        merge_snapshots(score, [snap1, snap2], MergeStrategy.last_write_wins)

        assert score.shared_value == "second"


class TestMixedSyncAsync:
    """Test parallel execution with mixed sync and async tasks."""

    @pytest.mark.asyncio
    async def test_sync_and_async_parallel(self):
        """Test parallel execution of mixed sync/async tasks."""
        @note
        def sync_task(score: ParallelTestScore) -> None:
            score.task_a_result = "sync"

        @note
        async def async_task(score: ParallelTestScore) -> None:
            await asyncio.sleep(0.01)
            score.task_b_result = "async"

        score = ParallelTestScore()
        score.__post_init__()

        cadence = (
            Cadence("test", score)
            .sync("mixed", [sync_task, async_task])
        )

        result = await cadence.run()

        assert result.task_a_result == "sync"
        assert result.task_b_result == "async"
