"""Sequential execution node."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any, TypeVar

from cadence.nodes.base import Node

ContextT = TypeVar("ContextT")


class SequenceNode(Node[ContextT]):
    """
    Executes multiple tasks sequentially.

    Tasks run one after another in order.
    """

    def __init__(
        self,
        context: ContextT,
        name: str,
        tasks: list[Callable[[ContextT], Any]],
    ) -> None:
        super().__init__(context, name)
        self._tasks = tasks

    async def execute(self) -> bool | None:
        """Execute all tasks in sequence."""
        for task in self._tasks:
            result = task(self._context)

            # Await if coroutine
            if inspect.iscoroutine(result):
                await result

        return None
