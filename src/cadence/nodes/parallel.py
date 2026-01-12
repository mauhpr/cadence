"""Parallel execution node with copy-on-write context isolation."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypeVar

from cadence.nodes.base import Node
from cadence.state import Context, MergeStrategy, merge_snapshots
from cadence.step import Beat

ContextT = TypeVar("ContextT")


def _is_async_callable(obj: Any) -> bool:
    """Check if an object is an async callable (function, method, or Beat)."""
    if isinstance(obj, Beat):
        return obj.is_async
    if inspect.iscoroutinefunction(obj):
        return True
    if hasattr(obj, "__call__"):
        return inspect.iscoroutinefunction(obj.__call__)
    return False


class ParallelNode(Node[ContextT]):
    """
    Executes multiple tasks in parallel with copy-on-write context isolation.

    Each task receives an isolated snapshot of the context to prevent race
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
        context: ContextT,
        name: str,
        tasks: list[Callable[[ContextT], Any]],
        merge_strategy: Callable = MergeStrategy.fail_on_conflict,
    ) -> None:
        super().__init__(context, name)
        self._tasks = tasks
        self._merge_strategy = merge_strategy

    async def execute(self) -> bool | None:
        """Execute all tasks in parallel with isolated context snapshots."""
        if not self._tasks:
            return None

        # Check if context supports copy-on-write
        use_cow = isinstance(self._context, Context) and hasattr(self._context, "_snapshot")

        if use_cow:
            return await self._execute_with_cow()
        else:
            return await self._execute_direct()

    async def _execute_with_cow(self) -> bool | None:
        """Execute with copy-on-write context isolation."""
        # Create isolated snapshots for each task
        snapshots = [self._context._snapshot() for _ in self._tasks]

        # Separate async and sync tasks with their snapshots
        async_tasks = []
        async_snapshots = []
        sync_tasks = []
        sync_snapshots = []

        for task, snapshot in zip(self._tasks, snapshots):
            if _is_async_callable(task):
                async_tasks.append(task)
                async_snapshots.append(snapshot)
            else:
                sync_tasks.append(task)
                sync_snapshots.append(snapshot)

        # Create coroutines for async tasks
        async_coros = [task(snapshot) for task, snapshot in zip(async_tasks, async_snapshots)]

        # Run sync tasks in thread pool
        if sync_tasks:
            loop = asyncio.get_running_loop()
            with ThreadPoolExecutor(max_workers=len(sync_tasks)) as executor:
                sync_futures = [
                    loop.run_in_executor(executor, task, snapshot)
                    for task, snapshot in zip(sync_tasks, sync_snapshots)
                ]
                # Wait for all tasks concurrently
                await asyncio.gather(*async_coros, *sync_futures)
        elif async_coros:
            await asyncio.gather(*async_coros)

        # Merge all snapshots back into original context
        all_snapshots = async_snapshots + sync_snapshots
        merge_snapshots(self._context, all_snapshots, self._merge_strategy)

        return None

    async def _execute_direct(self) -> bool | None:
        """Execute without copy-on-write (legacy behavior for non-Context types)."""
        async_tasks = []
        sync_tasks = []

        for task in self._tasks:
            if _is_async_callable(task):
                async_tasks.append(task)
            else:
                sync_tasks.append(task)

        async_coros = [task(self._context) for task in async_tasks]

        if sync_tasks:
            loop = asyncio.get_running_loop()
            with ThreadPoolExecutor(max_workers=len(sync_tasks)) as executor:
                sync_futures = [
                    loop.run_in_executor(executor, task, self._context)
                    for task in sync_tasks
                ]
                await asyncio.gather(*async_coros, *sync_futures)
        elif async_coros:
            await asyncio.gather(*async_coros)

        return None
