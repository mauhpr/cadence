"""Child cadence composition measure."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypeVar

from cadence.nodes.base import Measure

if TYPE_CHECKING:
    from cadence.cadence import Cadence

ScoreT = TypeVar("ScoreT")
ChildScoreT = TypeVar("ChildScoreT")


class ChildCadenceMeasure(Measure[ScoreT]):
    """
    Composes a child cadence into the parent cadence.

    Runs the child cadence and merges its score back to parent.
    """

    def __init__(
        self,
        score: ScoreT,
        name: str,
        child_cadence: Cadence[ChildScoreT],
        merge: Callable[[ScoreT, ChildScoreT], Any],
    ) -> None:
        super().__init__(score, name)
        self._child_cadence = child_cadence
        self._merge = merge

    async def execute(self) -> bool | None:
        """Run child cadence and merge results."""
        # Execute child cadence
        await self._child_cadence.run()

        # Get child score
        child_score = self._child_cadence.get_score()

        # Merge child score into parent
        result = self._merge(self._score, child_score)
        if inspect.iscoroutine(result):
            await result

        return None
