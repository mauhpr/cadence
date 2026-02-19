"""Fallback decorator for note resilience."""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from typing import (
    Any,
    TypeVar,
)

F = TypeVar("F", bound=Callable[..., Any])
T = TypeVar("T")


def fallback(
    default: T | None = None,
    *,
    field: str | None = None,
    handler: Callable[[Exception], T] | None = None,
    on: tuple[type[Exception], ...] | None = None,
) -> Callable[[F], F]:
    """
    Decorator to provide fallback behavior on failure.

    Either provide a default value or a handler function.

    Args:
        default: Default value to return on failure
        field: Score attribute to set on failure (for notes that mutate score).
               When provided, sets ``setattr(score, field, value)`` on the first
               positional argument and returns ``None``.
        handler: Function that receives the exception and returns a fallback value
        on: Tuple of exception types to catch (default: all exceptions)

    Example:
        @fallback(default=[], field="web_results")
        async def fetch_optional_data(score):
            score.web_results = await api.get_extras(score.id)

        @fallback(handler=lambda e: {"error": str(e), "cached": True})
        async def fetch_with_fallback(score):
            score.data = await volatile_api.get(score.id)
    """

    catch_on = on or (Exception,)

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                result = fn(*args, **kwargs)
                if inspect.iscoroutine(result):
                    return await result
                return result
            except catch_on as error:
                value = handler(error) if handler is not None else default
                if field is not None and args:
                    setattr(args[0], field, value)
                    return None
                return value

        @functools.wraps(fn)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return fn(*args, **kwargs)
            except catch_on as error:
                value = handler(error) if handler is not None else default
                if field is not None and args:
                    setattr(args[0], field, value)
                    return None
                return value

        if inspect.iscoroutinefunction(fn):
            return async_wrapper  # type: ignore
        return sync_wrapper  # type: ignore

    return decorator
