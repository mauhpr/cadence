"""Sequential execution measure."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any, TypeVar

from cadence.nodes.base import Measure

ScoreT = TypeVar("ScoreT")


class SequenceMeasure(Measure[ScoreT]):
    """
    Executes multiple tasks sequentially.

    Tasks run one after another in order.
    """

    def __init__(
        self,
        score: ScoreT,
        name: str,
        tasks: list[Callable[[ScoreT], Any]],
    ) -> None:
        super().__init__(score, name)
        self._tasks = tasks

    async def execute(self) -> bool | None:
        """Execute all tasks in sequence."""
        for task in self._tasks:
            result = task(self._score)

            # Await if coroutine
            if inspect.iscoroutine(result):
                await result

        return None
