"""Note decorator for marking functions as cadence notes."""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from typing import Any, Generic, ParamSpec, TypeVar, overload

from cadence.resilience.retry import retry as retry_decorator

P = ParamSpec("P")
R = TypeVar("R")
RetryConfig = int | dict[str, Any]


class Note(Generic[P, R]):
    """
    Wrapper for a note function with metadata.

    Allows attaching resilience decorators and tracking note info.
    """

    def __init__(
        self,
        fn: Callable[P, R],
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

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
        return self._fn(*args, **kwargs)

    def __repr__(self) -> str:
        return f"<Note: {self._name}>"


def _with_retry(fn: Callable[P, R], retry: RetryConfig | None) -> Callable[P, R]:
    if retry is None:
        return fn
    if isinstance(retry, int):
        return retry_decorator(max_attempts=retry)(fn)
    return retry_decorator(**retry)(fn)


@overload
def note(
    fn: Callable[P, R],
    *,
    name: str | None = None,
    description: str | None = None,
    retry: RetryConfig | None = None,
) -> Note[P, R]: ...


@overload
def note(
    fn: None = None,
    *,
    name: str | None = None,
    description: str | None = None,
    retry: RetryConfig | None = None,
) -> Callable[[Callable[P, R]], Note[P, R]]: ...


def note(
    fn: Callable[P, R] | None = None,
    *,
    name: str | None = None,
    description: str | None = None,
    retry: RetryConfig | None = None,
) -> Note[P, R] | Callable[[Callable[P, R]], Note[P, R]]:
    """
    Decorator to mark a function as a cadence note.

    Can be used with or without arguments:

        @note
        async def my_task(score): ...

        @note(name="custom_name", description="Does something")
        async def my_task(score): ...

        @note(retry=2)
        async def flaky_task(score): ...

        @note(retry={"max_attempts": 3, "backoff": "exponential"})
        async def api_task(score): ...

    Args:
        fn: The function to wrap (when used without parentheses)
        name: Optional custom name for the note
        description: Optional description for documentation
        retry: Optional retry shorthand. Pass an int for max attempts or a dict
            of arguments for cadence.retry().

    Returns:
        A Note wrapper around the function
    """

    def decorator(func: Callable[P, R]) -> Note[P, R]:
        wrapped = _with_retry(func, retry)
        return Note(wrapped, name=name, description=description)

    if fn is not None:
        # Called without parentheses: @note
        return decorator(fn)

    # Called with parentheses: @note(name="...")
    return decorator
