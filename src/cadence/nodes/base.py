"""Base node interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

ContextT = TypeVar("ContextT")


class Node(ABC, Generic[ContextT]):
    """
    Abstract base class for all cadence nodes.

    Each node represents an execution unit in the cadence.
    """

    def __init__(self, context: ContextT, name: str) -> None:
        self._context = context
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    @property
    def context(self) -> ContextT:
        return self._context

    @abstractmethod
    async def execute(self) -> bool | None:
        """
        Execute this node.

        Returns:
            None for normal completion
            True to interrupt the cadence
            False for explicit continue
        """
        ...

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}: {self._name}>"
