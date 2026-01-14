"""Parallel execution measure with copy-on-write score isolation."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypeVar, cast

from cadence.nodes.base import Measure
from cadence.note import Note
from cadence.score import MergeStrategy, Score, merge_snapshots

ScoreT = TypeVar("ScoreT")


def _is_async_callable(obj: Any) -> bool:
    """Check if an object is an async callable (function, method, or Note)."""
    if isinstance(obj, Note):
        return obj.is_async
    if inspect.iscoroutinefunction(obj):
        return True
    if callable(obj):
        return inspect.iscoroutinefunction(obj.__call__)
    return False


class ParallelMeasure(Measure[ScoreT]):
    """
    Executes multiple tasks in parallel with copy-on-write score isolation.

    Each task receives an isolated snapshot of the score to prevent race
    conditions. After all tasks complete, changes are merged back using
    a configurable merge strategy.

    For async tasks: uses asyncio.gather
    For sync tasks: uses ThreadPoolExecutor

    Merge strategies:
    - fail_on_conflict (default): Raises error if same field modified differently
    - last_write_wins: Last task's value wins for each field
    - smart_merge: Merges lists, sets, dicts intelligently
    """

    def __init__(
        self,
        score: ScoreT,
        name: str,
        tasks: list[Callable[[ScoreT], Any]],
        merge_strategy: Callable[..., Any] = MergeStrategy.fail_on_conflict,
    ) -> None:
        super().__init__(score, name)
        self._tasks = tasks
        self._merge_strategy = merge_strategy

    async def execute(self) -> bool | None:
        """Execute all tasks in parallel with isolated score snapshots."""
        if not self._tasks:
            return None

        # Check if score supports copy-on-write
        use_cow = isinstance(self._score, Score) and hasattr(self._score, "_snapshot")

        if use_cow:
            return await self._execute_with_cow()
        else:
            return await self._execute_direct()

    async def _execute_with_cow(self) -> bool | None:
        """Execute with copy-on-write score isolation."""
        # Create isolated snapshots for each task
        score_as_score = cast(Score, self._score)
        snapshots: list[Any] = [score_as_score._snapshot() for _ in self._tasks]

        # Separate async and sync tasks with their snapshots
        async_tasks: list[Callable[..., Any]] = []
        async_snapshots: list[Any] = []
        sync_tasks: list[Callable[..., Any]] = []
        sync_snapshots: list[Any] = []

        for task, snapshot in zip(self._tasks, snapshots, strict=True):
            if _is_async_callable(task):
                async_tasks.append(task)
                async_snapshots.append(snapshot)
            else:
                sync_tasks.append(task)
                sync_snapshots.append(snapshot)

        # Create coroutines for async tasks
        async_coros = [
            task(snapshot) for task, snapshot in zip(async_tasks, async_snapshots, strict=True)
        ]

        # Run sync tasks in thread pool
        if sync_tasks:
            loop = asyncio.get_running_loop()
            with ThreadPoolExecutor(max_workers=len(sync_tasks)) as executor:
                sync_futures = [
                    loop.run_in_executor(executor, task, snapshot)
                    for task, snapshot in zip(sync_tasks, sync_snapshots, strict=True)
                ]
                # Wait for all tasks concurrently
                await asyncio.gather(*async_coros, *sync_futures)
        elif async_coros:
            await asyncio.gather(*async_coros)

        # Merge all snapshots back into original score
        all_snapshots = async_snapshots + sync_snapshots
        merge_snapshots(score_as_score, all_snapshots, self._merge_strategy)

        return None

    async def _execute_direct(self) -> bool | None:
        """Execute without copy-on-write (legacy behavior for non-Score types)."""
        async_tasks = []
        sync_tasks = []

        for task in self._tasks:
            if _is_async_callable(task):
                async_tasks.append(task)
            else:
                sync_tasks.append(task)

        async_coros = [task(self._score) for task in async_tasks]

        if sync_tasks:
            loop = asyncio.get_running_loop()
            with ThreadPoolExecutor(max_workers=len(sync_tasks)) as executor:
                sync_futures = [
                    loop.run_in_executor(executor, task, self._score) for task in sync_tasks
                ]
                await asyncio.gather(*async_coros, *sync_futures)
        elif async_coros:
            await asyncio.gather(*async_coros)

        return None
