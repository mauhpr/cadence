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
    Resilience can be configured inline via ``retry``, ``timeout``,
    and ``fallback`` parameters, or by stacking standalone decorators.
    """

    def __init__(
        self,
        fn: Callable[..., Any],
        *,
        name: str | None = None,
        description: str | None = None,
        retry: int | dict[str, Any] | None = None,
        timeout: float | dict[str, Any] | None = None,
        fallback: dict[str, Any] | None = None,
    ) -> None:
        self._name = name or fn.__name__
        self._description = description or fn.__doc__ or ""
        self._is_async = inspect.iscoroutinefunction(fn)

        # Store normalized resilience config for introspection
        self._resilience: dict[str, dict[str, Any]] = {}
        if retry is not None:
            self._resilience["retry"] = (
                {"max_attempts": retry} if isinstance(retry, int) else dict(retry)
            )
        if timeout is not None:
            self._resilience["timeout"] = (
                {"seconds": float(timeout)} if isinstance(timeout, (int, float)) else dict(timeout)
            )
        if fallback is not None:
            self._resilience["fallback"] = dict(fallback)

        # Apply resilience wrappers: timeout (innermost) → retry → fallback (outermost)
        wrapped = fn
        if timeout is not None:
            from cadence.resilience.timeout import timeout as timeout_dec

            if isinstance(timeout, (int, float)):
                wrapped = timeout_dec(float(timeout))(wrapped)
            else:
                wrapped = timeout_dec(**timeout)(wrapped)
        if retry is not None:
            from cadence.resilience.retry import retry as retry_dec

            if isinstance(retry, int):
                wrapped = retry_dec(retry)(wrapped)
            else:
                wrapped = retry_dec(**retry)(wrapped)
        if fallback is not None:
            from cadence.resilience.fallback import fallback as fallback_dec

            wrapped = fallback_dec(**fallback)(wrapped)

        self._fn = wrapped

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

    @property
    def resilience(self) -> dict[str, dict[str, Any]]:
        """Resilience configuration for this note (empty dict if none)."""
        return self._resilience

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self._fn(*args, **kwargs)

    def __repr__(self) -> str:
        if self._resilience:
            flags = ", ".join(self._resilience.keys())
            return f"<Note: {self._name} [{flags}]>"
        return f"<Note: {self._name}>"


def note(
    fn: F | None = None,
    *,
    name: str | None = None,
    description: str | None = None,
    retry: int | dict[str, Any] | None = None,
    timeout: float | dict[str, Any] | None = None,
    fallback: dict[str, Any] | None = None,
) -> Note | Callable[[F], Note]:
    """
    Decorator to mark a function as a cadence note.

    Can be used with or without arguments:

        @note
        async def my_task(score): ...

        @note(name="custom_name", description="Does something")
        async def my_task(score): ...

    Resilience can be configured inline:

        @note(retry=3, timeout=15.0)
        async def my_task(score): ...

        @note(retry={"max_attempts": 3, "backoff": "exponential"}, timeout=30.0)
        async def my_task(score): ...

        @note(fallback={"default": [], "field": "items"}, timeout=10.0)
        async def my_task(score): ...

    Args:
        fn: The function to wrap (when used without parentheses)
        name: Optional custom name for the note
        description: Optional description for documentation
        retry: Retry config — int for max_attempts, or dict for full options
        timeout: Timeout config — float for seconds, or dict for full options
        fallback: Fallback config — dict with default, field, handler, on

    Returns:
        A Note wrapper around the function
    """

    def decorator(func: F) -> Note:
        return Note(
            func,
            name=name,
            description=description,
            retry=retry,
            timeout=timeout,
            fallback=fallback,
        )

    if fn is not None:
        # Called without parentheses: @note
        return decorator(fn)

    # Called with parentheses: @note(name="...", retry=3, ...)
    return decorator
