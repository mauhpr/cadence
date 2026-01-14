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

from cadence.exceptions import CadenceError, NoteError
from cadence.hooks import CadenceHooks, HooksManager
from cadence.nodes.base import Measure
from cadence.nodes.branch import BranchMeasure
from cadence.nodes.child import ChildCadenceMeasure
from cadence.nodes.parallel import ParallelMeasure
from cadence.nodes.sequence import SequenceMeasure
from cadence.nodes.single import SingleMeasure
from cadence.note import Note
from cadence.score import MergeStrategy


def _is_async_callable(obj: Any) -> bool:
    """Check if an object is an async callable (function, method, or Note)."""
    if isinstance(obj, Note):
        return obj.is_async
    if inspect.iscoroutinefunction(obj):
        return True
    if callable(obj):
        return inspect.iscoroutinefunction(obj.__call__)
    return False


ScoreT = TypeVar("ScoreT")
ChildScoreT = TypeVar("ChildScoreT")

# Type aliases for callbacks
Task = Callable[[Any], Any]
Condition = Callable[[Any], Any]
Merge = Callable[[Any, Any], Any]
TimeReporter = Callable[[str, float, Any], Any]
ErrorHandler = Callable[[Any, Exception], Any]


class Cadence(Generic[ScoreT]):
    """
    Declarative cadence builder for service logic.

    Build complex service logic with explicit control flow using a fluent API.

    Example:
        cadence = (
            Cadence("checkout", OrderScore(order_id="123"))
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
        result = cadence.get_score()
    """

    def __init__(
        self,
        name: str,
        score: ScoreT,
    ) -> None:
        """
        Create a new cadence.

        Args:
            name: Human-readable name for the cadence
            score: Initial score object
        """
        self._name = name
        self._score = score
        self._measures: list[Measure[ScoreT]] = []
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
    ) -> Cadence[ScoreT]:
        """
        Add a single task to the cadence.

        Args:
            name: Note name for logging/tracing
            task: Function that receives score
            can_interrupt: If True and task returns True, cadence stops

        Returns:
            self for chaining
        """
        wrapped_task = self._wrap_with_timing(name, task)
        measure = SingleMeasure(
            self._score,
            name,
            wrapped_task,
            can_interrupt=can_interrupt,
        )
        self._measures.append(measure)
        return self

    def sequence(
        self,
        name: str,
        tasks: list[Task],
    ) -> Cadence[ScoreT]:
        """
        Add multiple tasks to execute sequentially.

        Args:
            name: Note name for the sequence
            tasks: List of functions to execute in order

        Returns:
            self for chaining
        """
        wrapped_tasks = [
            self._wrap_with_timing(f"{name}[{i}]", task) for i, task in enumerate(tasks)
        ]
        measure = SequenceMeasure(self._score, name, wrapped_tasks)
        self._measures.append(measure)
        return self

    def sync(
        self,
        name: str,
        tasks: list[Task],
        *,
        merge_strategy: Callable[..., Any] = MergeStrategy.fail_on_conflict,
    ) -> Cadence[ScoreT]:
        """
        Add multiple tasks to execute in parallel (synchronized).

        For async tasks, uses asyncio.gather.
        For sync tasks, uses ThreadPoolExecutor.

        Args:
            name: Note name for the parallel group
            tasks: List of functions to execute concurrently
            merge_strategy: Strategy for merging parallel score changes.
                Options: MergeStrategy.fail_on_conflict (default),
                         MergeStrategy.last_write_wins,
                         MergeStrategy.smart_merge

        Returns:
            self for chaining
        """
        wrapped_tasks = [
            self._wrap_with_timing(f"{name}[{i}]", task) for i, task in enumerate(tasks)
        ]
        measure = ParallelMeasure(self._score, name, wrapped_tasks, merge_strategy)
        self._measures.append(measure)
        return self

    def split(
        self,
        name: str,
        condition: Condition,
        if_true: list[Task],
        if_false: list[Task] | None = None,
        *,
        parallel: bool = False,
    ) -> Cadence[ScoreT]:
        """
        Add conditional branching (split the cadence).

        Args:
            name: Note name for the branch
            condition: Function returning bool
            if_true: Tasks to run if condition is True
            if_false: Tasks to run if condition is False
            parallel: Execute branch tasks in parallel

        Returns:
            self for chaining
        """
        wrapped_if = [
            self._wrap_with_timing(f"{name}_if[{i}]", task) for i, task in enumerate(if_true)
        ]
        wrapped_else = [
            self._wrap_with_timing(f"{name}_else[{i}]", task)
            for i, task in enumerate(if_false or [])
        ]
        measure = BranchMeasure(
            self._score,
            name,
            condition,
            wrapped_if,
            wrapped_else,
            parallel=parallel,
        )
        self._measures.append(measure)
        return self

    def child(
        self,
        name: str,
        cadence: Cadence[ChildScoreT],
        merge: Merge,
    ) -> Cadence[ScoreT]:
        """
        Compose a child cadence.

        Args:
            name: Note name for the child cadence
            cadence: Child cadence to execute
            merge: Function to merge child score into parent

        Returns:
            self for chaining
        """
        measure = ChildCadenceMeasure(self._score, name, cadence, merge)
        self._measures.append(measure)
        return self

    def with_reporter(
        self,
        reporter: TimeReporter,
    ) -> Cadence[ScoreT]:
        """
        Add a time reporter for observability.

        The reporter is called after each note with:
        - note_name: Name of the note
        - elapsed: Time in seconds
        - score: Current score

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
    ) -> Cadence[ScoreT]:
        """
        Add an error handler.

        Args:
            handler: Function called with (score, error)
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
    ) -> Cadence[ScoreT]:
        """
        Add hooks for intercepting cadence and note execution.

        Multiple hooks can be added - they are called in order.

        Args:
            hooks: A CadenceHooks instance

        Returns:
            self for chaining

        Example:
            cadence = (
                Cadence("checkout", score)
                .with_hooks(LoggingHooks())
                .with_hooks(TimingHooks())
                .then("process", process)
            )
        """
        self._hooks_manager.add(hooks)
        return self

    async def run(self) -> ScoreT:
        """
        Execute the cadence.

        Returns:
            The final score after all notes complete

        Raises:
            CadenceError: If a note fails and no error handler is set
        """
        cadence_start = time.perf_counter()
        cadence_error: Exception | None = None

        # Call before_cadence hooks
        await self._hooks_manager.before_cadence(self._name, self._score)

        for measure in self._measures:
            note_start = time.perf_counter()

            # Call before_note hooks
            await self._hooks_manager.before_note(measure.name, self._score)

            try:
                result = await measure.execute()

                # Call after_note hooks (success)
                note_elapsed = time.perf_counter() - note_start
                await self._hooks_manager.after_note(measure.name, self._score, note_elapsed)

                # Handle interrupt signal
                if result is True:
                    break

            except CadenceError as error:
                # Call after_note hooks (with error)
                note_elapsed = time.perf_counter() - note_start
                await self._hooks_manager.after_note(measure.name, self._score, note_elapsed, error)
                await self._hooks_manager.on_error(measure.name, self._score, error)

                cadence_error = error
                if self._error_handler:
                    handler_result = self._error_handler(self._score, error)
                    if inspect.iscoroutine(handler_result):
                        await handler_result
                    if self._stop_on_error:
                        break
                else:
                    # Call after_cadence before raising
                    elapsed = time.perf_counter() - cadence_start
                    await self._hooks_manager.after_cadence(self._name, self._score, elapsed, error)
                    raise

            except Exception as error:
                # Wrap unexpected errors
                note_error = NoteError(
                    str(error),
                    note_name=measure.name,
                    original_error=error,
                )

                # Call after_note hooks (with error)
                note_elapsed = time.perf_counter() - note_start
                await self._hooks_manager.after_note(
                    measure.name, self._score, note_elapsed, note_error
                )
                await self._hooks_manager.on_error(measure.name, self._score, note_error)

                cadence_error = note_error
                if self._error_handler:
                    handler_result = self._error_handler(self._score, note_error)
                    if inspect.iscoroutine(handler_result):
                        await handler_result
                    if self._stop_on_error:
                        break
                else:
                    # Call after_cadence before raising
                    elapsed = time.perf_counter() - cadence_start
                    await self._hooks_manager.after_cadence(
                        self._name, self._score, elapsed, note_error
                    )
                    raise note_error from error

        # Report total cadence time
        elapsed = time.perf_counter() - cadence_start
        if self._time_reporter:
            reporter_result = self._time_reporter(f"{self._name}:TOTAL", elapsed, self._score)
            if inspect.iscoroutine(reporter_result):
                await reporter_result

        # Call after_cadence hooks
        await self._hooks_manager.after_cadence(self._name, self._score, elapsed, cadence_error)

        return self._score

    def run_sync(self) -> ScoreT:
        """
        Execute the cadence synchronously.

        Convenience method for non-async scores.

        Returns:
            The final score after all notes complete
        """
        return asyncio.run(self.run())

    def get_score(self) -> ScoreT:
        """Get the current score."""
        return self._score

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

            async def timed_async(score: ScoreT) -> Any:
                start = time.perf_counter()
                result = await task(score)
                elapsed = time.perf_counter() - start
                reporter_result = reporter(name, elapsed, score)
                if inspect.iscoroutine(reporter_result):
                    await reporter_result
                return result

            return timed_async
        else:

            def timed_sync(score: ScoreT) -> Any:
                start = time.perf_counter()
                result = task(score)
                elapsed = time.perf_counter() - start
                # Sync task can't await, just call reporter
                reporter(name, elapsed, score)
                return result

            return timed_sync

    def __repr__(self) -> str:
        return f"<Cadence: {self._name} ({len(self._measures)} measures)>"
