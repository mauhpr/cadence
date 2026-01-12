"""Core Cadence class - the main API for the Cadence framework."""

from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Callable
from typing import (
    Any,
    Generic,
    TypeVar,
)

from cadence.exceptions import CadenceError, BeatError
from cadence.hooks import CadenceHooks, HooksManager
from cadence.nodes.base import Node
from cadence.nodes.branch import BranchNode
from cadence.nodes.child import ChildCadenceNode
from cadence.nodes.parallel import ParallelNode
from cadence.nodes.sequence import SequenceNode
from cadence.nodes.single import SingleNode
from cadence.state import MergeStrategy
from cadence.step import Beat


def _is_async_callable(obj: Any) -> bool:
    """Check if an object is an async callable (function, method, or Beat)."""
    if isinstance(obj, Beat):
        return obj.is_async
    if inspect.iscoroutinefunction(obj):
        return True
    if hasattr(obj, "__call__"):
        return inspect.iscoroutinefunction(obj.__call__)
    return False

ContextT = TypeVar("ContextT")
ChildContextT = TypeVar("ChildContextT")

# Type aliases for callbacks
Task = Callable[[ContextT], Any]
Condition = Callable[[ContextT], Any]
Merge = Callable[[ContextT, Any], Any]
TimeReporter = Callable[[str, float, ContextT], Any]
ErrorHandler = Callable[[ContextT, Exception], Any]


class Cadence(Generic[ContextT]):
    """
    Declarative cadence builder for service logic.

    Build complex service logic with explicit control flow using a fluent API.

    Example:
        cadence = (
            Cadence("checkout", OrderContext(order_id="123"))
            .then("fetch_order", fetch_order)
            .sync("enrich", [fetch_user, fetch_inventory])
            .split("route",
                condition=is_premium,
                if_true=[priority_process],
                if_false=[standard_process]
            )
            .then("finalize", finalize_order)
        )

        await cadence.run()
        result = cadence.get_context()
    """

    def __init__(
        self,
        name: str,
        context: ContextT,
    ) -> None:
        """
        Create a new cadence.

        Args:
            name: Human-readable name for the cadence
            context: Initial context object
        """
        self._name = name
        self._context = context
        self._nodes: list[Node[ContextT]] = []
        self._time_reporter: TimeReporter | None = None
        self._error_handler: ErrorHandler | None = None
        self._stop_on_error: bool = True
        self._hooks_manager: HooksManager = HooksManager()

    @property
    def name(self) -> str:
        return self._name

    def then(
        self,
        name: str,
        task: Task,
        *,
        can_interrupt: bool = False,
    ) -> Cadence[ContextT]:
        """
        Add a single task to the cadence.

        Args:
            name: Beat name for logging/tracing
            task: Function that receives context
            can_interrupt: If True and task returns True, cadence stops

        Returns:
            self for chaining
        """
        wrapped_task = self._wrap_with_timing(name, task)
        node = SingleNode(
            self._context,
            name,
            wrapped_task,
            can_interrupt=can_interrupt,
        )
        self._nodes.append(node)
        return self


    def sequence(
        self,
        name: str,
        tasks: list[Task],
    ) -> Cadence[ContextT]:
        """
        Add multiple tasks to execute sequentially.

        Args:
            name: Beat name for the sequence
            tasks: List of functions to execute in order

        Returns:
            self for chaining
        """
        wrapped_tasks = [
            self._wrap_with_timing(f"{name}[{i}]", task)
            for i, task in enumerate(tasks)
        ]
        node = SequenceNode(self._context, name, wrapped_tasks)
        self._nodes.append(node)
        return self

    def sync(
        self,
        name: str,
        tasks: list[Task],
        *,
        merge_strategy: Callable = MergeStrategy.fail_on_conflict,
    ) -> Cadence[ContextT]:
        """
        Add multiple tasks to execute in parallel (synchronized).

        For async tasks, uses asyncio.gather.
        For sync tasks, uses ThreadPoolExecutor.

        Args:
            name: Beat name for the parallel group
            tasks: List of functions to execute concurrently
            merge_strategy: Strategy for merging parallel context changes.
                Options: MergeStrategy.fail_on_conflict (default),
                         MergeStrategy.last_write_wins,
                         MergeStrategy.smart_merge

        Returns:
            self for chaining
        """
        wrapped_tasks = [
            self._wrap_with_timing(f"{name}[{i}]", task)
            for i, task in enumerate(tasks)
        ]
        node = ParallelNode(self._context, name, wrapped_tasks, merge_strategy)
        self._nodes.append(node)
        return self


    def split(
        self,
        name: str,
        condition: Condition,
        if_true: list[Task],
        if_false: list[Task] | None = None,
        *,
        parallel: bool = False,
    ) -> Cadence[ContextT]:
        """
        Add conditional branching (split the cadence).

        Args:
            name: Beat name for the branch
            condition: Function returning bool
            if_true: Tasks to run if condition is True
            if_false: Tasks to run if condition is False
            parallel: Execute branch tasks in parallel

        Returns:
            self for chaining
        """
        wrapped_if = [
            self._wrap_with_timing(f"{name}_if[{i}]", task)
            for i, task in enumerate(if_true)
        ]
        wrapped_else = [
            self._wrap_with_timing(f"{name}_else[{i}]", task)
            for i, task in enumerate(if_false or [])
        ]
        node = BranchNode(
            self._context,
            name,
            condition,
            wrapped_if,
            wrapped_else,
            parallel=parallel,
        )
        self._nodes.append(node)
        return self


    def child(
        self,
        name: str,
        cadence: Cadence[ChildContextT],
        merge: Merge,
    ) -> Cadence[ContextT]:
        """
        Compose a child cadence.

        Args:
            name: Beat name for the child cadence
            cadence: Child cadence to execute
            merge: Function to merge child context into parent

        Returns:
            self for chaining
        """
        node = ChildCadenceNode(self._context, name, cadence, merge)
        self._nodes.append(node)
        return self

    def with_reporter(
        self,
        reporter: TimeReporter,
    ) -> Cadence[ContextT]:
        """
        Add a time reporter for observability.

        The reporter is called after each beat with:
        - beat_name: Name of the beat
        - elapsed: Time in seconds
        - context: Current context

        Args:
            reporter: Callback function

        Returns:
            self for chaining
        """
        self._time_reporter = reporter
        return self

    def on_error(
        self,
        handler: ErrorHandler,
        *,
        stop: bool = True,
    ) -> Cadence[ContextT]:
        """
        Add an error handler.

        Args:
            handler: Function called with (context, error)
            stop: If True, stop cadence on error. If False, continue.

        Returns:
            self for chaining
        """
        self._error_handler = handler
        self._stop_on_error = stop
        return self

    def with_hooks(
        self,
        hooks: CadenceHooks,
    ) -> Cadence[ContextT]:
        """
        Add hooks for intercepting cadence and beat execution.

        Multiple hooks can be added - they are called in order.

        Args:
            hooks: A CadenceHooks instance

        Returns:
            self for chaining

        Example:
            cadence = (
                Cadence("checkout", ctx)
                .with_hooks(LoggingHooks())
                .with_hooks(TimingHooks())
                .then("process", process)
            )
        """
        self._hooks_manager.add(hooks)
        return self

    async def run(self) -> ContextT:
        """
        Execute the cadence.

        Returns:
            The final context after all beats complete

        Raises:
            CadenceError: If a beat fails and no error handler is set
        """
        cadence_start = time.perf_counter()
        cadence_error: Exception | None = None

        # Call before_cadence hooks
        await self._hooks_manager.before_cadence(self._name, self._context)

        for node in self._nodes:
            beat_start = time.perf_counter()

            # Call before_beat hooks
            await self._hooks_manager.before_beat(node.name, self._context)

            try:
                result = await node.execute()

                # Call after_beat hooks (success)
                beat_elapsed = time.perf_counter() - beat_start
                await self._hooks_manager.after_beat(
                    node.name, self._context, beat_elapsed
                )

                # Handle interrupt signal
                if result is True:
                    break

            except CadenceError as error:
                # Call after_beat hooks (with error)
                beat_elapsed = time.perf_counter() - beat_start
                await self._hooks_manager.after_beat(
                    node.name, self._context, beat_elapsed, error
                )
                await self._hooks_manager.on_error(node.name, self._context, error)

                cadence_error = error
                if self._error_handler:
                    handler_result = self._error_handler(self._context, error)
                    if inspect.iscoroutine(handler_result):
                        await handler_result
                    if self._stop_on_error:
                        break
                else:
                    # Call after_cadence before raising
                    elapsed = time.perf_counter() - cadence_start
                    await self._hooks_manager.after_cadence(
                        self._name, self._context, elapsed, error
                    )
                    raise

            except Exception as error:
                # Wrap unexpected errors
                beat_error = BeatError(
                    str(error),
                    beat_name=node.name,
                    original_error=error,
                )

                # Call after_beat hooks (with error)
                beat_elapsed = time.perf_counter() - beat_start
                await self._hooks_manager.after_beat(
                    node.name, self._context, beat_elapsed, beat_error
                )
                await self._hooks_manager.on_error(node.name, self._context, beat_error)

                cadence_error = beat_error
                if self._error_handler:
                    handler_result = self._error_handler(self._context, beat_error)
                    if inspect.iscoroutine(handler_result):
                        await handler_result
                    if self._stop_on_error:
                        break
                else:
                    # Call after_cadence before raising
                    elapsed = time.perf_counter() - cadence_start
                    await self._hooks_manager.after_cadence(
                        self._name, self._context, elapsed, beat_error
                    )
                    raise beat_error from error

        # Report total cadence time
        elapsed = time.perf_counter() - cadence_start
        if self._time_reporter:
            reporter_result = self._time_reporter(
                f"{self._name}:TOTAL", elapsed, self._context
            )
            if inspect.iscoroutine(reporter_result):
                await reporter_result

        # Call after_cadence hooks
        await self._hooks_manager.after_cadence(
            self._name, self._context, elapsed, cadence_error
        )

        return self._context

    def run_sync(self) -> ContextT:
        """
        Execute the cadence synchronously.

        Convenience method for non-async contexts.

        Returns:
            The final context after all beats complete
        """
        return asyncio.run(self.run())

    def get_context(self) -> ContextT:
        """Get the current context."""
        return self._context


    def _wrap_with_timing(
        self,
        name: str,
        task: Task,
    ) -> Task:
        """Wrap a task with timing reporting."""
        if not self._time_reporter:
            return task

        reporter = self._time_reporter

        if _is_async_callable(task):
            async def timed_async(context: ContextT) -> Any:
                start = time.perf_counter()
                result = await task(context)
                elapsed = time.perf_counter() - start
                reporter_result = reporter(name, elapsed, context)
                if inspect.iscoroutine(reporter_result):
                    await reporter_result
                return result
            return timed_async
        else:
            def timed_sync(context: ContextT) -> Any:
                start = time.perf_counter()
                result = task(context)
                elapsed = time.perf_counter() - start
                # Sync task can't await, just call reporter
                reporter(name, elapsed, context)
                return result
            return timed_sync

    def __repr__(self) -> str:
        return f"<Cadence: {self._name} ({len(self._nodes)} nodes)>"
