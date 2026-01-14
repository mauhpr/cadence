"""Note decorator for marking functions as cadence notes."""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


class Note:
    """
    Wrapper for a note function with metadata.

    Allows attaching resilience decorators and tracking note info.
    """

    def __init__(
        self,
        fn: Callable[..., Any],
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> None:
        self._fn = fn
        self._name = name or fn.__name__
        self._description = description or fn.__doc__ or ""
        self._is_async = inspect.iscoroutinefunction(fn)

        # Preserve function metadata
        functools.update_wrapper(self, fn)

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def is_async(self) -> bool:
        return self._is_async

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self._fn(*args, **kwargs)

    def __repr__(self) -> str:
        return f"<Note: {self._name}>"


def note(
    fn: F | None = None,
    *,
    name: str | None = None,
    description: str | None = None,
) -> Note | Callable[[F], Note]:
    """
    Decorator to mark a function as a cadence note.

    Can be used with or without arguments:

        @note
        async def my_task(score): ...

        @note(name="custom_name", description="Does something")
        async def my_task(score): ...

    Args:
        fn: The function to wrap (when used without parentheses)
        name: Optional custom name for the note
        description: Optional description for documentation

    Returns:
        A Note wrapper around the function
    """

    def decorator(func: F) -> Note:
        return Note(func, name=name, description=description)

    if fn is not None:
        # Called without parentheses: @note
        return decorator(fn)

    # Called with parentheses: @note(name="...")
    return decorator
