"""Timeout decorator for note resilience."""

from __future__ import annotations

import asyncio
import functools
import inspect
import signal
from collections.abc import Callable
from typing import Any, TypeVar

from cadence.exceptions import TimeoutError as CadenceTimeoutError

F = TypeVar("F", bound=Callable[..., Any])


def timeout(
    seconds: float,
    *,
    message: str | None = None,
) -> Callable[[F], F]:
    """
    Decorator to add timeout to a note.

    Args:
        seconds: Maximum execution time in seconds
        message: Optional custom timeout message

    Example:
        @timeout(5.0)
        async def fetch_data(score):
            score.data = await slow_api.get(score.id)

        @timeout(10.0, message="Payment gateway timeout")
        async def process_payment(score):
            score.result = await payment.charge(score.amount)
    """

    def decorator(fn: F) -> F:
        note_name = getattr(fn, "__name__", "unknown")

        @functools.wraps(fn)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                result = fn(*args, **kwargs)
                if inspect.iscoroutine(result):
                    return await asyncio.wait_for(result, timeout=seconds)
                return result
            except asyncio.TimeoutError as exc:
                raise CadenceTimeoutError(note_name, seconds) from exc

        @functools.wraps(fn)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            # For sync functions, use signal-based timeout (Unix only)
            # On Windows, this won't work - sync functions can't be timed out easily
            import platform

            if platform.system() == "Windows":
                # On Windows, just run without timeout for sync functions
                # Users should use async functions for timeouts
                return fn(*args, **kwargs)

            def timeout_handler(signum: int, frame: Any) -> None:
                raise CadenceTimeoutError(note_name, seconds)

            # Set the signal handler
            old_handler = signal.signal(signal.SIGALRM, timeout_handler)
            signal.setitimer(signal.ITIMER_REAL, seconds)

            try:
                return fn(*args, **kwargs)
            finally:
                # Reset the alarm and restore handler
                signal.setitimer(signal.ITIMER_REAL, 0)
                signal.signal(signal.SIGALRM, old_handler)

        if inspect.iscoroutinefunction(fn):
            return async_wrapper  # type: ignore
        return sync_wrapper  # type: ignore

    return decorator
