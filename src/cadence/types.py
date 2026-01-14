"""Type definitions for Cadence."""

from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

# Score type variable - bound to any class
ScoreT = TypeVar("ScoreT")
ChildScoreT = TypeVar("ChildScoreT")

# Task signatures
SyncTask = Callable[[ScoreT], None]
AsyncTask = Callable[[ScoreT], Coroutine[Any, Any, None]]
Task = SyncTask[ScoreT] | AsyncTask[ScoreT]

# Condition signatures (for branching)
SyncCondition = Callable[[ScoreT], bool]
AsyncCondition = Callable[[ScoreT], Coroutine[Any, Any, bool]]
Condition = SyncCondition[ScoreT] | AsyncCondition[ScoreT]

# Interruptible task (can stop cadence)
SyncInterruptible = Callable[[ScoreT], bool | None]
AsyncInterruptible = Callable[[ScoreT], Coroutine[Any, Any, bool | None]]
Interruptible = SyncInterruptible[ScoreT] | AsyncInterruptible[ScoreT]

# Merge task for child cadences
SyncMerge = Callable[[ScoreT, ChildScoreT], None]
AsyncMerge = Callable[[ScoreT, ChildScoreT], Coroutine[Any, Any, None]]
Merge = SyncMerge[ScoreT, ChildScoreT] | AsyncMerge[ScoreT, ChildScoreT]

# Reporter callbacks
TimeReporter = Callable[[str, float, ScoreT], Any]
ErrorHandler = Callable[[ScoreT, Exception], Any]
