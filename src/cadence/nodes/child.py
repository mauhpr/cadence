"""Child cadence composition node."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypeVar

from cadence.nodes.base import Node

if TYPE_CHECKING:
    from cadence.flow import Cadence

ContextT = TypeVar("ContextT")
ChildContextT = TypeVar("ChildContextT")


class ChildCadenceNode(Node[ContextT]):
    """
    Composes a child cadence into the parent cadence.

    Runs the child cadence and merges its context back to parent.
    """

    def __init__(
        self,
        context: ContextT,
        name: str,
        child_cadence: Cadence[ChildContextT],
        merge: Callable[[ContextT, ChildContextT], Any],
    ) -> None:
        super().__init__(context, name)
        self._child_cadence = child_cadence
        self._merge = merge

    async def execute(self) -> bool | None:
        """Run child cadence and merge results."""
        # Execute child cadence
        await self._child_cadence.run()

        # Get child context
        child_context = self._child_cadence.get_context()

        # Merge child context into parent
        result = self._merge(self._context, child_context)
        if inspect.iscoroutine(result):
            await result

        return None
