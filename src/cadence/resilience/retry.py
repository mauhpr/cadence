"""Retry decorator for note resilience."""

from __future__ import annotations

import asyncio
import functools
import inspect
import random
from collections.abc import Callable
from typing import (
    Any,
    TypeVar,
)

from cadence.exceptions import RetryExhaustedError

F = TypeVar("F", bound=Callable[..., Any])


def retry(
    max_attempts: int = 3,
    *,
    delay: float = 1.0,
    backoff: str = "fixed",  # "fixed", "linear", "exponential"
    max_delay: float = 60.0,
    jitter: bool = True,
    on: tuple[type[Exception], ...] | None = None,
) -> Callable[[F], F]:
    """
    Decorator to retry a note on failure.

    Args:
        max_attempts: Maximum number of attempts (default: 3)
        delay: Initial delay between attempts in seconds (default: 1.0)
        backoff: Backoff strategy - "fixed", "linear", or "exponential"
        max_delay: Maximum delay between attempts (default: 60.0)
        jitter: Add random jitter to delays (default: True)
        on: Tuple of exception types to retry on (default: all exceptions)

    Example:
        @retry(max_attempts=3, backoff="exponential")
        async def fetch_data(score):
            score.data = await api.get(score.id)

        @retry(max_attempts=5, on=(ConnectionError, TimeoutError))
        async def call_service(score):
            score.result = await service.call()
    """

    retry_on = on or (Exception,)

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            last_error: Exception | None = None

            for attempt in range(1, max_attempts + 1):
                try:
                    result = fn(*args, **kwargs)
                    if inspect.iscoroutine(result):
                        return await result
                    return result

                except retry_on as error:
                    last_error = error

                    if attempt == max_attempts:
                        # Get note name from function or first arg
                        note_name = getattr(fn, "__name__", "unknown")
                        raise RetryExhaustedError(note_name, max_attempts, error) from error

                    # Calculate delay
                    current_delay = _calculate_delay(attempt, delay, backoff, max_delay, jitter)
                    await asyncio.sleep(current_delay)

            # Should never reach here, but just in case
            raise RetryExhaustedError(
                getattr(fn, "__name__", "unknown"),
                max_attempts,
                last_error or Exception("Unknown error"),
            )

        @functools.wraps(fn)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            import time

            last_error: Exception | None = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return fn(*args, **kwargs)

                except retry_on as error:
                    last_error = error

                    if attempt == max_attempts:
                        note_name = getattr(fn, "__name__", "unknown")
                        raise RetryExhaustedError(note_name, max_attempts, error) from error

                    current_delay = _calculate_delay(attempt, delay, backoff, max_delay, jitter)
                    time.sleep(current_delay)

            raise RetryExhaustedError(
                getattr(fn, "__name__", "unknown"),
                max_attempts,
                last_error or Exception("Unknown error"),
            )

        if inspect.iscoroutinefunction(fn):
            return async_wrapper  # type: ignore
        return sync_wrapper  # type: ignore

    return decorator


def _calculate_delay(
    attempt: int,
    base_delay: float,
    backoff: str,
    max_delay: float,
    jitter: bool,
) -> float:
    """Calculate delay for the given attempt."""
    if backoff == "fixed":
        delay = base_delay
    elif backoff == "linear":
        delay = base_delay * attempt
    elif backoff == "exponential":
        delay = base_delay * (2 ** (attempt - 1))
    else:
        delay = base_delay

    # Apply max delay cap
    delay = min(delay, max_delay)

    # Add jitter (0-25% of delay)
    if jitter:
        delay = delay * (1 + random.uniform(0, 0.25))

    return delay
