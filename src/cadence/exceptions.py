"""Custom exceptions for Cadence."""

from __future__ import annotations

from typing import Any


class CadenceError(Exception):
    """
    Base exception for cadence-related errors.

    Provides error codes and structured error information.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self._message = message
        self._code = code or "CADENCE_ERROR"
        self._details = details or {}

    @property
    def code(self) -> str:
        return self._code

    @property
    def message(self) -> str:
        return self._message

    @property
    def details(self) -> dict[str, Any]:
        return self._details

    def __str__(self) -> str:
        return f"[{self._code}] {self._message}"

    def __repr__(self) -> str:
        return f"CadenceError(code={self._code!r}, message={self._message!r})"


class BeatError(CadenceError):
    """Error that occurred during beat execution."""

    def __init__(
        self,
        message: str,
        *,
        beat_name: str,
        original_error: Exception | None = None,
        code: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=code or "BEAT_ERROR",
            details={"beat_name": beat_name},
        )
        self._beat_name = beat_name
        self._original_error = original_error

    @property
    def beat_name(self) -> str:
        return self._beat_name

    @property
    def original_error(self) -> Exception | None:
        return self._original_error


class TimeoutError(CadenceError):
    """Beat execution timed out."""

    def __init__(self, beat_name: str, timeout_seconds: float) -> None:
        super().__init__(
            f"Beat '{beat_name}' timed out after {timeout_seconds}s",
            code="TIMEOUT",
            details={"beat_name": beat_name, "timeout": timeout_seconds},
        )


class RetryExhaustedError(CadenceError):
    """All retry attempts failed."""

    def __init__(
        self,
        beat_name: str,
        attempts: int,
        last_error: Exception,
    ) -> None:
        super().__init__(
            f"Beat '{beat_name}' failed after {attempts} attempts: {last_error}",
            code="RETRY_EXHAUSTED",
            details={"beat_name": beat_name, "attempts": attempts},
        )
        self._last_error = last_error

    @property
    def last_error(self) -> Exception:
        return self._last_error
