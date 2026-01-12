"""Conditional branching node."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any, TypeVar

from cadence.nodes.base import Node
from cadence.nodes.parallel import ParallelNode
from cadence.nodes.sequence import SequenceNode

ContextT = TypeVar("ContextT")


class BranchNode(Node[ContextT]):
    """
    Conditional branching based on a condition function.

    Evaluates condition and executes either if_tasks or else_tasks.
    """

    def __init__(
        self,
        context: ContextT,
        name: str,
        condition: Callable[[ContextT], Any],
        if_tasks: list[Callable[[ContextT], Any]],
        else_tasks: list[Callable[[ContextT], Any]] | None = None,
        *,
        parallel: bool = False,
    ) -> None:
        super().__init__(context, name)
        self._condition = condition
        self._if_tasks = if_tasks
        self._else_tasks = else_tasks or []
        self._parallel = parallel

    async def execute(self) -> bool | None:
        """Evaluate condition and execute appropriate branch."""
        # Evaluate condition
        result = self._condition(self._context)
        if inspect.iscoroutine(result):
            result = await result

        # Select tasks based on condition result
        tasks = self._if_tasks if result else self._else_tasks

        if not tasks:
            return None

        # Execute selected tasks
        if self._parallel:
            node = ParallelNode(self._context, f"{self._name}_branch", tasks)
        else:
            node = SequenceNode(self._context, f"{self._name}_branch", tasks)

        await node.execute()
        return None
