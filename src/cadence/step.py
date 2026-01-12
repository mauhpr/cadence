"""Beat decorator for marking functions as cadence beats."""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


class Beat:
    """
    Wrapper for a beat function with metadata.

    Allows attaching resilience decorators and tracking beat info.
    """

    def __init__(
        self,
        fn: Callable,
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
        return f"<Beat: {self._name}>"


def beat(
    fn: F | None = None,
    *,
    name: str | None = None,
    description: str | None = None,
) -> Beat | Callable[[F], Beat]:
    """
    Decorator to mark a function as a cadence beat.

    Can be used with or without arguments:

        @beat
        async def my_task(ctx): ...

        @beat(name="custom_name", description="Does something")
        async def my_task(ctx): ...

    Args:
        fn: The function to wrap (when used without parentheses)
        name: Optional custom name for the beat
        description: Optional description for documentation

    Returns:
        A Beat wrapper around the function
    """

    def decorator(func: F) -> Beat:
        return Beat(func, name=name, description=description)

    if fn is not None:
        # Called without parentheses: @beat
        return decorator(fn)

    # Called with parentheses: @beat(name="...")
    return decorator
