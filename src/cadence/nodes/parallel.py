"""Parallel execution measure with copy-on-write score isolation."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypeVar, cast

from cadence.exceptions import ParallelNoteError
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
        task_names: list[str] | None = None,
    ) -> None:
        super().__init__(score, name)
        self._tasks = tasks
        self._merge_strategy = merge_strategy
        self._task_names = task_names or [
            self._resolve_task_name(i, t) for i, t in enumerate(tasks)
        ]

    @staticmethod
    def _resolve_task_name(index: int, task: Any) -> str:
        """Extract a human-readable name from a task callable."""
        if isinstance(task, Note):
            return task.name
        name: str | None = getattr(task, "__name__", None)
        if name and name not in ("<lambda>", "timed_async", "timed_sync"):
            return name
        return f"task[{index}]"

    async def _wrap_task_error(
        self,
        index: int,
        task_name: str,
        coro: Any,
    ) -> Any:
        """Wrap a coroutine to re-raise exceptions as ParallelNoteError."""
        try:
            return await coro
        except ParallelNoteError:
            raise
        except Exception as e:
            raise ParallelNoteError(
                f"Task '{task_name}' in group '{self._name}' failed: {e}",
                group_name=self._name,
                task_index=index,
                task_name=task_name,
                original_error=e,
            ) from e

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

        # Separate async and sync tasks with their snapshots and indices
        async_items: list[tuple[int, str, Callable[..., Any], Any]] = []
        sync_items: list[tuple[int, str, Callable[..., Any], Any]] = []

        for i, (task, snapshot) in enumerate(zip(self._tasks, snapshots, strict=True)):
            name = self._task_names[i]
            if _is_async_callable(task):
                async_items.append((i, name, task, snapshot))
            else:
                sync_items.append((i, name, task, snapshot))

        # Create wrapped coroutines for async tasks
        async_coros = [
            self._wrap_task_error(idx, name, task(snapshot))
            for idx, name, task, snapshot in async_items
        ]

        # Run sync tasks in thread pool, wrapped for error context
        if sync_items:
            loop = asyncio.get_running_loop()
            with ThreadPoolExecutor(max_workers=len(sync_items)) as executor:
                sync_futures = [
                    self._wrap_task_error(
                        idx,
                        name,
                        loop.run_in_executor(executor, task, snapshot),
                    )
                    for idx, name, task, snapshot in sync_items
                ]
                await asyncio.gather(*async_coros, *sync_futures)
        elif async_coros:
            await asyncio.gather(*async_coros)

        # Merge all snapshots back into original score
        async_snapshots = [s for _, _, _, s in async_items]
        sync_snapshots = [s for _, _, _, s in sync_items]
        all_snapshots = async_snapshots + sync_snapshots
        merge_snapshots(score_as_score, all_snapshots, self._merge_strategy)

        return None

    async def _execute_direct(self) -> bool | None:
        """Execute without copy-on-write (legacy behavior for non-Score types)."""
        async_items: list[tuple[int, str, Callable[..., Any]]] = []
        sync_items: list[tuple[int, str, Callable[..., Any]]] = []

        for i, task in enumerate(self._tasks):
            name = self._task_names[i]
            if _is_async_callable(task):
                async_items.append((i, name, task))
            else:
                sync_items.append((i, name, task))

        async_coros = [
            self._wrap_task_error(idx, name, task(self._score)) for idx, name, task in async_items
        ]

        if sync_items:
            loop = asyncio.get_running_loop()
            with ThreadPoolExecutor(max_workers=len(sync_items)) as executor:
                sync_futures = [
                    self._wrap_task_error(
                        idx,
                        name,
                        loop.run_in_executor(executor, task, self._score),
                    )
                    for idx, name, task in sync_items
                ]
                await asyncio.gather(*async_coros, *sync_futures)
        elif async_coros:
            await asyncio.gather(*async_coros)

        return None
