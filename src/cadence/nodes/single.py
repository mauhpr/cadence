"""Single task measure."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any, TypeVar

from cadence.nodes.base import Measure

ScoreT = TypeVar("ScoreT")


class SingleMeasure(Measure[ScoreT]):
    """
    Executes a single task.

    The task receives the score and can modify it.
    """

    def __init__(
        self,
        score: ScoreT,
        name: str,
        task: Callable[[ScoreT], Any],
        *,
        can_interrupt: bool = False,
    ) -> None:
        super().__init__(score, name)
        self._task = task
        self._can_interrupt = can_interrupt

    async def execute(self) -> bool | None:
        """Execute the task."""
        result = self._task(self._score)

        # Await if coroutine
        if inspect.iscoroutine(result):
            result = await result

        # Handle interrupt signal
        if self._can_interrupt and result is True:
            return True

        return None
