"""Single task node."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any, TypeVar

from cadence.nodes.base import Node

ContextT = TypeVar("ContextT")


class SingleNode(Node[ContextT]):
    """
    Executes a single task.

    The task receives the context and can modify it.
    """

    def __init__(
        self,
        context: ContextT,
        name: str,
        task: Callable[[ContextT], Any],
        *,
        can_interrupt: bool = False,
    ) -> None:
        super().__init__(context, name)
        self._task = task
        self._can_interrupt = can_interrupt

    async def execute(self) -> bool | None:
        """Execute the task."""
        result = self._task(self._context)

        # Await if coroutine
        if inspect.iscoroutine(result):
            result = await result

        # Handle interrupt signal
        if self._can_interrupt and result is True:
            return True

        return None
