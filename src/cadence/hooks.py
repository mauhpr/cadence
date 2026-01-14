"""Middleware and hooks system for Cadence.

Provides hooks for intercepting cadence and note execution:
- before_cadence / after_cadence: Called at cadence start/end
- before_note / after_note: Called before/after each note
- on_error: Called when a note or cadence fails
- on_retry: Called before each retry attempt

Example:
    from cadence import Cadence
    from cadence.hooks import CadenceHooks, LoggingHooks, TimingHooks

    # Using built-in hooks
    cadence = (
        Cadence("checkout", OrderScore())
        .with_hooks(LoggingHooks())
        .with_hooks(TimingHooks())
        .then("process", process)
    )

    # Custom hooks
    class MyHooks(CadenceHooks):
        async def before_note(self, note_name, score):
            print(f"Starting: {note_name}")

        async def after_note(self, note_name, score, duration, error=None):
            print(f"Completed: {note_name} in {duration:.3f}s")

    cadence = cadence.with_hooks(MyHooks())
"""

from __future__ import annotations

import inspect
import logging
import time
from collections.abc import Callable
from typing import (
    Any,
    TypeVar,
)

ScoreT = TypeVar("ScoreT")

logger = logging.getLogger("cadence")


class CadenceHooks:
    """
    Base class for cadence hooks.

    Override methods to intercept cadence and note execution.
    All methods are optional - override only what you need.
    """

    async def before_cadence(
        self,
        cadence_name: str,
        score: ScoreT,
    ) -> None:
        """Called before cadence execution starts."""
        pass

    async def after_cadence(
        self,
        cadence_name: str,
        score: ScoreT,
        duration: float,
        error: Exception | None = None,
    ) -> None:
        """Called after cadence execution completes (success or failure)."""
        pass

    async def before_note(
        self,
        note_name: str,
        score: ScoreT,
    ) -> None:
        """Called before each note executes."""
        pass

    async def after_note(
        self,
        note_name: str,
        score: ScoreT,
        duration: float,
        error: Exception | None = None,
    ) -> None:
        """Called after each note completes (success or failure)."""
        pass

    async def on_error(
        self,
        note_name: str,
        score: ScoreT,
        error: Exception,
    ) -> bool | None:
        """
        Called when a note fails.

        Return True to suppress the error and continue.
        Return False or None to propagate the error.
        """
        return None

    async def on_retry(
        self,
        note_name: str,
        score: ScoreT,
        attempt: int,
        max_attempts: int,
        error: Exception,
    ) -> None:
        """Called before each retry attempt."""
        pass


class HooksManager:
    """
    Manages multiple hooks for a cadence.

    Hooks are called in order of registration.
    """

    def __init__(self) -> None:
        self._hooks: list[CadenceHooks] = []

    def add(self, hooks: CadenceHooks) -> HooksManager:
        """Add a hooks instance."""
        self._hooks.append(hooks)
        return self

    def remove(self, hooks: CadenceHooks) -> HooksManager:
        """Remove a hooks instance."""
        if hooks in self._hooks:
            self._hooks.remove(hooks)
        return self

    def clear(self) -> None:
        """Remove all hooks."""
        self._hooks.clear()

    async def _call_hook(
        self,
        method_name: str,
        *args: Any,
        **kwargs: Any,
    ) -> Any | None:
        """Call a hook method on all registered hooks."""
        results = []
        for hooks in self._hooks:
            method = getattr(hooks, method_name, None)
            if method is not None:
                result = method(*args, **kwargs)
                if inspect.iscoroutine(result):
                    result = await result
                results.append(result)
        return results

    async def before_cadence(self, cadence_name: str, score: ScoreT) -> None:
        await self._call_hook("before_cadence", cadence_name, score)

    async def after_cadence(
        self,
        cadence_name: str,
        score: ScoreT,
        duration: float,
        error: Exception | None = None,
    ) -> None:
        await self._call_hook("after_cadence", cadence_name, score, duration, error)

    async def before_note(self, note_name: str, score: ScoreT) -> None:
        await self._call_hook("before_note", note_name, score)

    async def after_note(
        self,
        note_name: str,
        score: ScoreT,
        duration: float,
        error: Exception | None = None,
    ) -> None:
        await self._call_hook("after_note", note_name, score, duration, error)

    async def on_error(
        self,
        note_name: str,
        score: ScoreT,
        error: Exception,
    ) -> bool:
        """Returns True if any hook suppressed the error."""
        results = await self._call_hook("on_error", note_name, score, error)
        return any(r is True for r in (results or []))

    async def on_retry(
        self,
        note_name: str,
        score: ScoreT,
        attempt: int,
        max_attempts: int,
        error: Exception,
    ) -> None:
        await self._call_hook("on_retry", note_name, score, attempt, max_attempts, error)


# --- Built-in Hooks ---


class LoggingHooks(CadenceHooks):
    """
    Hooks that log cadence and note execution.

    Uses Python's logging module.

    Args:
        logger_name: Logger name (default: "cadence")
        level: Log level for normal operations (default: INFO)
        error_level: Log level for errors (default: ERROR)
    """

    def __init__(
        self,
        logger_name: str = "cadence",
        level: int = logging.INFO,
        error_level: int = logging.ERROR,
    ) -> None:
        self._logger = logging.getLogger(logger_name)
        self._level = level
        self._error_level = error_level

    async def before_cadence(self, cadence_name: str, score: ScoreT) -> None:
        self._logger.log(self._level, f"[{cadence_name}] Starting cadence")

    async def after_cadence(
        self,
        cadence_name: str,
        score: ScoreT,
        duration: float,
        error: Exception | None = None,
    ) -> None:
        if error:
            self._logger.log(
                self._error_level,
                f"[{cadence_name}] Cadence failed after {duration:.3f}s: {error}",
            )
        else:
            self._logger.log(
                self._level,
                f"[{cadence_name}] Cadence completed in {duration:.3f}s",
            )

    async def before_note(self, note_name: str, score: ScoreT) -> None:
        self._logger.log(self._level, f"  → {note_name}")

    async def after_note(
        self,
        note_name: str,
        score: ScoreT,
        duration: float,
        error: Exception | None = None,
    ) -> None:
        if error:
            self._logger.log(
                self._error_level,
                f"  ✗ {note_name} failed after {duration:.3f}s: {error}",
            )
        else:
            self._logger.log(
                self._level,
                f"  ✓ {note_name} ({duration:.3f}s)",
            )


class TimingHooks(CadenceHooks):
    """
    Hooks that collect timing metrics.

    Stores timing data for later analysis.

    Example:
        hooks = TimingHooks()
        cadence = Cadence("test", score).with_hooks(hooks)
        await cadence.run()

        print(hooks.get_report())
        print(f"Total: {hooks.total_duration:.3f}s")
    """

    def __init__(self) -> None:
        self._cadence_name: str | None = None
        self._cadence_start: float = 0.0
        self._note_times: dict[str, float] = {}
        self._total_duration: float = 0.0

    async def before_cadence(self, cadence_name: str, score: ScoreT) -> None:
        self._cadence_name = cadence_name
        self._cadence_start = time.perf_counter()
        self._note_times.clear()

    async def after_cadence(
        self,
        cadence_name: str,
        score: ScoreT,
        duration: float,
        error: Exception | None = None,
    ) -> None:
        self._total_duration = duration

    async def after_note(
        self,
        note_name: str,
        score: ScoreT,
        duration: float,
        error: Exception | None = None,
    ) -> None:
        self._note_times[note_name] = duration

    @property
    def note_times(self) -> dict[str, float]:
        """Get timing data for all notes."""
        return self._note_times.copy()

    @property
    def total_duration(self) -> float:
        """Get total cadence duration."""
        return self._total_duration

    def get_report(self) -> str:
        """Get a formatted timing report."""
        lines = [f"=== Timing Report: {self._cadence_name} ==="]
        for note_name, duration in self._note_times.items():
            pct = (duration / self._total_duration * 100) if self._total_duration > 0 else 0
            lines.append(f"  {note_name}: {duration:.3f}s ({pct:.1f}%)")
        lines.append(f"  TOTAL: {self._total_duration:.3f}s")
        return "\n".join(lines)


class MetricsHooks(CadenceHooks):
    """
    Hooks that collect metrics for monitoring.

    Tracks:
    - Cadence execution count (success/failure)
    - Note execution count (success/failure)
    - Latency histograms
    - Error rates

    Example:
        hooks = MetricsHooks()
        # Use with multiple cadences
        cadence1 = Cadence("a", score).with_hooks(hooks)
        cadence2 = Cadence("b", score).with_hooks(hooks)

        # Export metrics
        print(hooks.get_metrics())
    """

    def __init__(self) -> None:
        self._cadence_counts: dict[str, dict[str, int]] = {}
        self._note_counts: dict[str, dict[str, int]] = {}
        self._cadence_durations: dict[str, list[float]] = {}
        self._note_durations: dict[str, list[float]] = {}
        self._retry_counts: dict[str, int] = {}

    async def before_cadence(self, cadence_name: str, score: ScoreT) -> None:
        if cadence_name not in self._cadence_counts:
            self._cadence_counts[cadence_name] = {"success": 0, "failure": 0}
            self._cadence_durations[cadence_name] = []

    async def after_cadence(
        self,
        cadence_name: str,
        score: ScoreT,
        duration: float,
        error: Exception | None = None,
    ) -> None:
        if error:
            self._cadence_counts[cadence_name]["failure"] += 1
        else:
            self._cadence_counts[cadence_name]["success"] += 1
        self._cadence_durations[cadence_name].append(duration)

    async def after_note(
        self,
        note_name: str,
        score: ScoreT,
        duration: float,
        error: Exception | None = None,
    ) -> None:
        if note_name not in self._note_counts:
            self._note_counts[note_name] = {"success": 0, "failure": 0}
            self._note_durations[note_name] = []

        if error:
            self._note_counts[note_name]["failure"] += 1
        else:
            self._note_counts[note_name]["success"] += 1
        self._note_durations[note_name].append(duration)

    async def on_retry(
        self,
        note_name: str,
        score: ScoreT,
        attempt: int,
        max_attempts: int,
        error: Exception,
    ) -> None:
        self._retry_counts[note_name] = self._retry_counts.get(note_name, 0) + 1

    def get_metrics(self) -> dict[str, Any]:
        """Get all collected metrics."""
        return {
            "cadences": {
                name: {
                    "success": counts["success"],
                    "failure": counts["failure"],
                    "total": counts["success"] + counts["failure"],
                    "success_rate": (
                        counts["success"] / (counts["success"] + counts["failure"])
                        if (counts["success"] + counts["failure"]) > 0
                        else 0.0
                    ),
                    "avg_duration": (
                        sum(self._cadence_durations[name]) / len(self._cadence_durations[name])
                        if self._cadence_durations[name]
                        else 0.0
                    ),
                }
                for name, counts in self._cadence_counts.items()
            },
            "notes": {
                name: {
                    "success": counts["success"],
                    "failure": counts["failure"],
                    "success_rate": (
                        counts["success"] / (counts["success"] + counts["failure"])
                        if (counts["success"] + counts["failure"]) > 0
                        else 0.0
                    ),
                    "avg_duration": (
                        sum(self._note_durations[name]) / len(self._note_durations[name])
                        if self._note_durations[name]
                        else 0.0
                    ),
                }
                for name, counts in self._note_counts.items()
            },
            "retries": self._retry_counts.copy(),
        }

    def reset(self) -> None:
        """Reset all metrics."""
        self._cadence_counts.clear()
        self._note_counts.clear()
        self._cadence_durations.clear()
        self._note_durations.clear()
        self._retry_counts.clear()


class TracingHooks(CadenceHooks):
    """
    Hooks for distributed tracing integration.

    Creates spans for cadences and notes. Works with any tracing backend
    that follows the OpenTelemetry-style API.

    Example:
        from opentelemetry import trace

        tracer = trace.get_tracer("myapp")
        hooks = TracingHooks(tracer)

        cadence = Cadence("checkout", score).with_hooks(hooks)
    """

    def __init__(self, tracer: Any) -> None:
        """
        Initialize with a tracer.

        Args:
            tracer: An OpenTelemetry-compatible tracer
        """
        self._tracer = tracer
        self._cadence_span: Any | None = None
        self._note_spans: dict[str, Any] = {}

    async def before_cadence(self, cadence_name: str, score: ScoreT) -> None:
        self._cadence_span = self._tracer.start_span(f"cadence:{cadence_name}")
        self._cadence_span.set_attribute("cadence.name", cadence_name)

    async def after_cadence(
        self,
        cadence_name: str,
        score: ScoreT,
        duration: float,
        error: Exception | None = None,
    ) -> None:
        if self._cadence_span:
            if error:
                self._cadence_span.set_status(
                    status_code=2,  # ERROR
                    description=str(error),
                )
                self._cadence_span.record_exception(error)
            self._cadence_span.end()
            self._cadence_span = None

    async def before_note(self, note_name: str, score: ScoreT) -> None:
        span = self._tracer.start_span(
            f"note:{note_name}",
            parent=self._cadence_span,
        )
        span.set_attribute("note.name", note_name)
        self._note_spans[note_name] = span

    async def after_note(
        self,
        note_name: str,
        score: ScoreT,
        duration: float,
        error: Exception | None = None,
    ) -> None:
        span = self._note_spans.pop(note_name, None)
        if span:
            span.set_attribute("note.duration_ms", duration * 1000)
            if error:
                span.set_status(
                    status_code=2,
                    description=str(error),
                )
                span.record_exception(error)
            span.end()


class DebugHooks(CadenceHooks):
    """
    Hooks for debugging cadence execution.

    Prints detailed information about each note, including score changes.

    Args:
        show_score: Whether to print score after each note
        show_timing: Whether to print timing info
    """

    def __init__(
        self,
        show_score: bool = True,
        show_timing: bool = True,
    ) -> None:
        self._show_score = show_score
        self._show_timing = show_timing

    async def before_cadence(self, cadence_name: str, score: ScoreT) -> None:
        print(f"\n{'=' * 60}")
        print(f"CADENCE: {cadence_name}")
        print(f"{'=' * 60}")
        if self._show_score:
            print(f"Initial score: {score}")
        print()

    async def after_cadence(
        self,
        cadence_name: str,
        score: ScoreT,
        duration: float,
        error: Exception | None = None,
    ) -> None:
        print()
        if error:
            print(f"CADENCE FAILED: {error}")
        else:
            print("CADENCE COMPLETED")
        if self._show_timing:
            print(f"Duration: {duration:.3f}s")
        if self._show_score:
            print(f"Final score: {score}")
        print(f"{'=' * 60}\n")

    async def before_note(self, note_name: str, score: ScoreT) -> None:
        print(f"→ {note_name}")

    async def after_note(
        self,
        note_name: str,
        score: ScoreT,
        duration: float,
        error: Exception | None = None,
    ) -> None:
        status = "✗" if error else "✓"
        timing = f" ({duration:.3f}s)" if self._show_timing else ""
        print(f"  {status}{timing}")
        if error:
            print(f"    Error: {error}")
        if self._show_score:
            print(f"    Score: {score}")


# --- Functional Hooks ---


def before_note(callback: Callable[..., Any]) -> CadenceHooks:
    """Create a hooks instance with just a before_note callback."""

    class CallbackHooks(CadenceHooks):
        async def before_note(self, note_name: str, score: ScoreT) -> None:
            result = callback(note_name, score)
            if inspect.iscoroutine(result):
                await result

    return CallbackHooks()


def after_note(callback: Callable[..., Any]) -> CadenceHooks:
    """Create a hooks instance with just an after_note callback."""

    class CallbackHooks(CadenceHooks):
        async def after_note(
            self,
            note_name: str,
            score: ScoreT,
            duration: float,
            error: Exception | None = None,
        ) -> None:
            result = callback(note_name, score, duration, error)
            if inspect.iscoroutine(result):
                await result

    return CallbackHooks()


def on_error(callback: Callable[..., Any]) -> CadenceHooks:
    """Create a hooks instance with just an on_error callback."""

    class CallbackHooks(CadenceHooks):
        async def on_error(
            self,
            note_name: str,
            score: ScoreT,
            error: Exception,
        ) -> bool | None:
            result = callback(note_name, score, error)
            if inspect.iscoroutine(result):
                result = await result
            return bool(result) if result is not None else None

    return CallbackHooks()
