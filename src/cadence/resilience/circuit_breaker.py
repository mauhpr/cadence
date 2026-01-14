"""Circuit breaker pattern for protecting against cascading failures."""

from __future__ import annotations

import functools
import inspect
import time
from collections.abc import Callable
from enum import Enum
from threading import Lock
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation, requests flow through
    OPEN = "open"  # Failing, requests are blocked
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitOpenError(Exception):
    """Raised when circuit is open and request is blocked."""

    def __init__(self, name: str, retry_after: float) -> None:
        self.name = name
        self.retry_after = retry_after
        super().__init__(f"Circuit '{name}' is open. Retry after {retry_after:.1f}s")


class CircuitBreaker:
    """
    Circuit breaker implementation with thread-safe state management.

    States:
    - CLOSED: Normal operation, all requests pass through
    - OPEN: Too many failures, all requests are rejected immediately
    - HALF_OPEN: Testing recovery, limited requests allowed

    Transitions:
    - CLOSED → OPEN: When failure_threshold is exceeded
    - OPEN → HALF_OPEN: After recovery_timeout expires
    - HALF_OPEN → CLOSED: On successful request
    - HALF_OPEN → OPEN: On failed request
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 1,
        excluded_exceptions: tuple[type[Exception], ...] | None = None,
    ) -> None:
        """
        Initialize circuit breaker.

        Args:
            name: Identifier for this circuit
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Seconds to wait before trying half-open
            half_open_max_calls: Max concurrent calls in half-open state
            excluded_exceptions: Exceptions that don't count as failures
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self.excluded_exceptions = excluded_exceptions or ()

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float | None = None
        self._half_open_calls = 0
        self._lock = Lock()

    @property
    def state(self) -> CircuitState:
        """Get current state, checking for automatic transitions."""
        with self._lock:
            if self._state == CircuitState.OPEN and self._last_failure_time is not None:
                # Check if recovery timeout has passed
                elapsed = time.monotonic() - self._last_failure_time
                if elapsed >= self.recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_calls = 0
            return self._state

    def _record_success(self) -> None:
        """Record a successful call."""
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                self._half_open_calls = 0
            elif self._state == CircuitState.CLOSED:
                # Optionally decay failure count on success
                self._failure_count = max(0, self._failure_count - 1)

    def _record_failure(self) -> None:
        """Record a failed call."""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()

            if self._state == CircuitState.HALF_OPEN:
                # Any failure in half-open reopens the circuit
                self._state = CircuitState.OPEN
                self._half_open_calls = 0
            elif self._state == CircuitState.CLOSED:
                if self._failure_count >= self.failure_threshold:
                    self._state = CircuitState.OPEN

    def _can_execute(self) -> bool:
        """Check if a request can proceed."""
        state = self.state  # This may trigger OPEN → HALF_OPEN transition

        if state == CircuitState.CLOSED:
            return True

        if state == CircuitState.OPEN:
            return False

        if state == CircuitState.HALF_OPEN:
            with self._lock:
                if self._half_open_calls < self.half_open_max_calls:
                    self._half_open_calls += 1
                    return True
                return False

        return False

    def _get_retry_after(self) -> float:
        """Get seconds until circuit might close."""
        with self._lock:
            if self._last_failure_time is None:
                return 0.0
            elapsed = time.monotonic() - self._last_failure_time
            return max(0.0, self.recovery_timeout - elapsed)

    def reset(self) -> None:
        """Manually reset the circuit to closed state."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._last_failure_time = None
            self._half_open_calls = 0


# Global registry of circuit breakers for sharing across decorators
_circuit_registry: dict[str, CircuitBreaker] = {}
_registry_lock = Lock()


def get_circuit(
    name: str,
    failure_threshold: int = 5,
    recovery_timeout: float = 30.0,
    half_open_max_calls: int = 1,
    excluded_exceptions: tuple[type[Exception], ...] | None = None,
) -> CircuitBreaker:
    """Get or create a circuit breaker by name."""
    with _registry_lock:
        if name not in _circuit_registry:
            _circuit_registry[name] = CircuitBreaker(
                name=name,
                failure_threshold=failure_threshold,
                recovery_timeout=recovery_timeout,
                half_open_max_calls=half_open_max_calls,
                excluded_exceptions=excluded_exceptions,
            )
        return _circuit_registry[name]


def circuit_breaker(
    failure_threshold: int = 5,
    recovery_timeout: float = 30.0,
    half_open_max_calls: int = 1,
    name: str | None = None,
    excluded_exceptions: tuple[type[Exception], ...] | None = None,
) -> Callable[[F], F]:
    """
    Circuit breaker decorator for protecting against cascading failures.

    When a function fails repeatedly (exceeds failure_threshold), the circuit
    "opens" and immediately rejects all calls for recovery_timeout seconds.
    After that, it enters "half-open" state where limited calls are allowed
    to test if the service has recovered.

    Args:
        failure_threshold: Number of failures before opening circuit
        recovery_timeout: Seconds to wait before allowing test calls
        half_open_max_calls: Max concurrent calls in half-open state
        name: Circuit name (defaults to function name). Same name = shared circuit.
        excluded_exceptions: Exceptions that don't count as failures

    Example:
        @note
        @circuit_breaker(failure_threshold=5, recovery_timeout=30)
        async def call_external_service(score):
            return await external_api.call()

        # Multiple functions can share a circuit:
        @circuit_breaker(name="payment-api", failure_threshold=3)
        async def charge_card(score): ...

        @circuit_breaker(name="payment-api", failure_threshold=3)
        async def refund_card(score): ...
    """

    def decorator(func: F) -> F:
        circuit_name = name or func.__name__
        circuit = get_circuit(
            name=circuit_name,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
            half_open_max_calls=half_open_max_calls,
            excluded_exceptions=excluded_exceptions,
        )

        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                if not circuit._can_execute():
                    raise CircuitOpenError(circuit_name, circuit._get_retry_after())

                try:
                    result = await func(*args, **kwargs)
                    circuit._record_success()
                    return result
                except Exception as e:
                    if circuit.excluded_exceptions and isinstance(e, circuit.excluded_exceptions):
                        circuit._record_success()
                        raise
                    circuit._record_failure()
                    raise

            return async_wrapper  # type: ignore
        else:

            @functools.wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                if not circuit._can_execute():
                    raise CircuitOpenError(circuit_name, circuit._get_retry_after())

                try:
                    result = func(*args, **kwargs)
                    circuit._record_success()
                    return result
                except Exception as e:
                    if circuit.excluded_exceptions and isinstance(e, circuit.excluded_exceptions):
                        circuit._record_success()
                        raise
                    circuit._record_failure()
                    raise

            return sync_wrapper  # type: ignore

    return decorator
