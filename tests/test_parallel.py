"""Tests for parallel execution with copy-on-write context."""

import pytest
import asyncio
from dataclasses import dataclass, field
from typing import List, Optional

from cadence import Cadence, Context, beat, MergeConflict, MergeStrategy, BeatError


@dataclass
class ParallelTestContext(Context):
    """Context for parallel execution tests."""
    task_a_result: Optional[str] = None
    task_b_result: Optional[str] = None
    task_c_result: Optional[str] = None
    shared_list: Optional[List[str]] = None
    shared_value: Optional[str] = None


@beat
async def task_a(ctx: ParallelTestContext) -> None:
    """Task that sets task_a_result."""
    await asyncio.sleep(0.01)
    ctx.task_a_result = "A"


@beat
async def task_b(ctx: ParallelTestContext) -> None:
    """Task that sets task_b_result."""
    await asyncio.sleep(0.01)
    ctx.task_b_result = "B"


@beat
async def task_c(ctx: ParallelTestContext) -> None:
    """Task that sets task_c_result."""
    await asyncio.sleep(0.01)
    ctx.task_c_result = "C"


@beat
async def append_a(ctx: ParallelTestContext) -> None:
    """Task that appends to shared list."""
    if ctx.shared_list is None:
        ctx.shared_list = []
    ctx.shared_list.append("A")


@beat
async def append_b(ctx: ParallelTestContext) -> None:
    """Task that appends to shared list."""
    if ctx.shared_list is None:
        ctx.shared_list = []
    ctx.shared_list.append("B")


@beat
async def set_shared_1(ctx: ParallelTestContext) -> None:
    """Task that sets shared value to 1."""
    ctx.shared_value = "value1"


@beat
async def set_shared_2(ctx: ParallelTestContext) -> None:
    """Task that sets shared value to 2."""
    ctx.shared_value = "value2"


class TestParallelExecution:
    """Test parallel node execution with context isolation."""

    @pytest.mark.asyncio
    async def test_sync_different_fields(self):
        """Test parallel tasks writing to different fields."""
        ctx = ParallelTestContext()
        ctx.__post_init__()

        cadence = (
            Cadence("test", ctx)
            .sync("tasks", [task_a, task_b, task_c])
        )

        result = await cadence.run()

        assert result.task_a_result == "A"
        assert result.task_b_result == "B"
        assert result.task_c_result == "C"

    @pytest.mark.asyncio
    async def test_sync_conflict_detection(self):
        """Test that conflicting writes are detected."""
        ctx = ParallelTestContext()
        ctx.__post_init__()

        cadence = (
            Cadence("test", ctx)
            .sync("tasks", [set_shared_1, set_shared_2])
        )

        # MergeConflict is wrapped in BeatError by Cadence.run()
        with pytest.raises(BeatError) as exc_info:
            await cadence.run()

        # The original MergeConflict should be the cause
        assert isinstance(exc_info.value.original_error, MergeConflict)
        assert exc_info.value.original_error.field == "shared_value"

    @pytest.mark.asyncio
    async def test_sync_isolation(self):
        """Test that parallel tasks don't see each other's changes."""
        changes_seen = []

        @beat
        async def check_isolation(ctx: ParallelTestContext) -> None:
            # Record what we see at start
            changes_seen.append({
                "a": ctx.task_a_result,
                "b": ctx.task_b_result,
            })
            await asyncio.sleep(0.02)
            # Set our value
            ctx.task_a_result = "from_check"

        ctx = ParallelTestContext()
        ctx.__post_init__()

        cadence = (
            Cadence("test", ctx)
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
        ctx = ParallelTestContext()
        ctx.__post_init__()

        # Custom parallel node would be needed for custom strategy
        # For now, test the merge strategy directly
        from cadence.state import merge_snapshots

        snap1 = ctx._snapshot()
        snap1.shared_list = ["A"]

        snap2 = ctx._snapshot()
        snap2.shared_list = ["B"]

        merge_snapshots(ctx, [snap1, snap2], MergeStrategy.smart_merge)

        assert ctx.shared_list == ["A", "B"]

    @pytest.mark.asyncio
    async def test_last_write_wins(self):
        """Test last_write_wins ignores conflicts."""
        ctx = ParallelTestContext()
        ctx.__post_init__()

        from cadence.state import merge_snapshots

        snap1 = ctx._snapshot()
        snap1.shared_value = "first"

        snap2 = ctx._snapshot()
        snap2.shared_value = "second"

        merge_snapshots(ctx, [snap1, snap2], MergeStrategy.last_write_wins)

        assert ctx.shared_value == "second"


class TestMixedSyncAsync:
    """Test parallel execution with mixed sync and async tasks."""

    @pytest.mark.asyncio
    async def test_sync_and_async_parallel(self):
        """Test parallel execution of mixed sync/async tasks."""
        @beat
        def sync_task(ctx: ParallelTestContext) -> None:
            ctx.task_a_result = "sync"

        @beat
        async def async_task(ctx: ParallelTestContext) -> None:
            await asyncio.sleep(0.01)
            ctx.task_b_result = "async"

        ctx = ParallelTestContext()
        ctx.__post_init__()

        cadence = (
            Cadence("test", ctx)
            .sync("mixed", [sync_task, async_task])
        )

        result = await cadence.run()

        assert result.task_a_result == "sync"
        assert result.task_b_result == "async"
