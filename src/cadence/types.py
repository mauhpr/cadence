"""Type definitions for Cadence."""

from collections.abc import Callable, Coroutine
from typing import Any, TypeVar, Union

# Context type variable - bound to any class
ContextT = TypeVar("ContextT")
ChildContextT = TypeVar("ChildContextT")

# Task signatures
SyncTask = Callable[[ContextT], None]
AsyncTask = Callable[[ContextT], Coroutine[Any, Any, None]]
Task = Union[SyncTask[ContextT], AsyncTask[ContextT]]

# Condition signatures (for branching)
SyncCondition = Callable[[ContextT], bool]
AsyncCondition = Callable[[ContextT], Coroutine[Any, Any, bool]]
Condition = Union[SyncCondition[ContextT], AsyncCondition[ContextT]]

# Interruptible task (can stop cadence)
SyncInterruptible = Callable[[ContextT], bool | None]
AsyncInterruptible = Callable[[ContextT], Coroutine[Any, Any, bool | None]]
Interruptible = Union[SyncInterruptible[ContextT], AsyncInterruptible[ContextT]]

# Merge task for child cadences
SyncMerge = Callable[[ContextT, ChildContextT], None]
AsyncMerge = Callable[[ContextT, ChildContextT], Coroutine[Any, Any, None]]
Merge = Union[SyncMerge[ContextT, ChildContextT], AsyncMerge[ContextT, ChildContextT]]

# Reporter callbacks
TimeReporter = Callable[[str, float, ContextT], Any]
ErrorHandler = Callable[[ContextT, Exception], Any]
