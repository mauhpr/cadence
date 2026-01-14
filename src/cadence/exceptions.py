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


class NoteError(CadenceError):
    """Error that occurred during note execution."""

    def __init__(
        self,
        message: str,
        *,
        note_name: str,
        original_error: Exception | None = None,
        code: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=code or "NOTE_ERROR",
            details={"note_name": note_name},
        )
        self._note_name = note_name
        self._original_error = original_error

    @property
    def note_name(self) -> str:
        return self._note_name

    @property
    def original_error(self) -> Exception | None:
        return self._original_error


class TimeoutError(CadenceError):
    """Note execution timed out."""

    def __init__(self, note_name: str, timeout_seconds: float) -> None:
        super().__init__(
            f"Note '{note_name}' timed out after {timeout_seconds}s",
            code="TIMEOUT",
            details={"note_name": note_name, "timeout": timeout_seconds},
        )


class RetryExhaustedError(CadenceError):
    """All retry attempts failed."""

    def __init__(
        self,
        note_name: str,
        attempts: int,
        last_error: Exception,
    ) -> None:
        super().__init__(
            f"Note '{note_name}' failed after {attempts} attempts: {last_error}",
            code="RETRY_EXHAUSTED",
            details={"note_name": note_name, "attempts": attempts},
        )
        self._last_error = last_error

    @property
    def last_error(self) -> Exception:
        return self._last_error
