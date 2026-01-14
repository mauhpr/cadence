"""Conditional branching measure."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any, TypeVar

from cadence.nodes.base import Measure
from cadence.nodes.parallel import ParallelMeasure
from cadence.nodes.sequence import SequenceMeasure

ScoreT = TypeVar("ScoreT")


class BranchMeasure(Measure[ScoreT]):
    """
    Conditional branching based on a condition function.

    Evaluates condition and executes either if_tasks or else_tasks.
    """

    def __init__(
        self,
        score: ScoreT,
        name: str,
        condition: Callable[[ScoreT], Any],
        if_tasks: list[Callable[[ScoreT], Any]],
        else_tasks: list[Callable[[ScoreT], Any]] | None = None,
        *,
        parallel: bool = False,
    ) -> None:
        super().__init__(score, name)
        self._condition = condition
        self._if_tasks = if_tasks
        self._else_tasks = else_tasks or []
        self._parallel = parallel

    async def execute(self) -> bool | None:
        """Evaluate condition and execute appropriate branch."""
        # Evaluate condition
        result = self._condition(self._score)
        if inspect.iscoroutine(result):
            result = await result

        # Select tasks based on condition result
        tasks = self._if_tasks if result else self._else_tasks

        if not tasks:
            return None

        # Execute selected tasks
        branch_measure: Measure[ScoreT]
        if self._parallel:
            branch_measure = ParallelMeasure(self._score, f"{self._name}_branch", tasks)
        else:
            branch_measure = SequenceMeasure(self._score, f"{self._name}_branch", tasks)

        await branch_measure.execute()
        return None
