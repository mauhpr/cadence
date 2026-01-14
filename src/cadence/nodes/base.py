"""Base measure interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

ScoreT = TypeVar("ScoreT")


class Measure(ABC, Generic[ScoreT]):
    """
    Abstract base class for all cadence measures.

    Each measure represents an execution unit in the cadence.
    """

    def __init__(self, score: ScoreT, name: str) -> None:
        self._score = score
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    @property
    def score(self) -> ScoreT:
        return self._score

    @abstractmethod
    async def execute(self) -> bool | None:
        """
        Execute this measure.

        Returns:
            None for normal completion
            True to interrupt the cadence
            False for explicit continue
        """
        ...

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}: {self._name}>"
