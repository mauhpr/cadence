"""Middleware and hooks system for Cadence.

Provides hooks for intercepting cadence and beat execution:
- before_cadence / after_cadence: Called at cadence start/end
- before_beat / after_beat: Called before/after each beat
- on_error: Called when a beat or cadence fails
- on_retry: Called before each retry attempt

Example:
    from cadence import Cadence
    from cadence.hooks import CadenceHooks, LoggingHooks, TimingHooks

    # Using built-in hooks
    cadence = (
        Cadence("checkout", OrderContext())
        .with_hooks(LoggingHooks())
        .with_hooks(TimingHooks())
        .then("process", process)
    )

    # Custom hooks
    class MyHooks(CadenceHooks):
        async def before_beat(self, beat_name, context):
            print(f"Starting: {beat_name}")

        async def after_beat(self, beat_name, context, duration, error=None):
            print(f"Completed: {beat_name} in {duration:.3f}s")

    cadence = cadence.with_hooks(MyHooks())
"""

from __future__ import annotations

import inspect
import logging
import time
from abc import ABC
from collections.abc import Callable
from typing import (
    Any,
    TypeVar,
)

ContextT = TypeVar("ContextT")

logger = logging.getLogger("cadence")


class CadenceHooks(ABC):
    """
    Base class for cadence hooks.

    Override methods to intercept cadence and beat execution.
    All methods are optional - override only what you need.
    """

    async def before_cadence(
        self,
        cadence_name: str,
        context: ContextT,
    ) -> None:
        """Called before cadence execution starts."""
        pass

    async def after_cadence(
        self,
        cadence_name: str,
        context: ContextT,
        duration: float,
        error: Exception | None = None,
    ) -> None:
        """Called after cadence execution completes (success or failure)."""
        pass

    async def before_beat(
        self,
        beat_name: str,
        context: ContextT,
    ) -> None:
        """Called before each beat executes."""
        pass

    async def after_beat(
        self,
        beat_name: str,
        context: ContextT,
        duration: float,
        error: Exception | None = None,
    ) -> None:
        """Called after each beat completes (success or failure)."""
        pass

    async def on_error(
        self,
        beat_name: str,
        context: ContextT,
        error: Exception,
    ) -> bool | None:
        """
        Called when a beat fails.

        Return True to suppress the error and continue.
        Return False or None to propagate the error.
        """
        return None

    async def on_retry(
        self,
        beat_name: str,
        context: ContextT,
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

    async def before_cadence(self, cadence_name: str, context: ContextT) -> None:
        await self._call_hook("before_cadence", cadence_name, context)

    async def after_cadence(
        self,
        cadence_name: str,
        context: ContextT,
        duration: float,
        error: Exception | None = None,
    ) -> None:
        await self._call_hook("after_cadence", cadence_name, context, duration, error)

    async def before_beat(self, beat_name: str, context: ContextT) -> None:
        await self._call_hook("before_beat", beat_name, context)

    async def after_beat(
        self,
        beat_name: str,
        context: ContextT,
        duration: float,
        error: Exception | None = None,
    ) -> None:
        await self._call_hook("after_beat", beat_name, context, duration, error)

    async def on_error(
        self,
        beat_name: str,
        context: ContextT,
        error: Exception,
    ) -> bool:
        """Returns True if any hook suppressed the error."""
        results = await self._call_hook("on_error", beat_name, context, error)
        return any(r is True for r in (results or []))

    async def on_retry(
        self,
        beat_name: str,
        context: ContextT,
        attempt: int,
        max_attempts: int,
        error: Exception,
    ) -> None:
        await self._call_hook("on_retry", beat_name, context, attempt, max_attempts, error)


# --- Built-in Hooks ---


class LoggingHooks(CadenceHooks):
    """
    Hooks that log cadence and beat execution.

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

    async def before_cadence(self, cadence_name: str, context: ContextT) -> None:
        self._logger.log(self._level, f"[{cadence_name}] Starting cadence")

    async def after_cadence(
        self,
        cadence_name: str,
        context: ContextT,
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

    async def before_beat(self, beat_name: str, context: ContextT) -> None:
        self._logger.log(self._level, f"  → {beat_name}")

    async def after_beat(
        self,
        beat_name: str,
        context: ContextT,
        duration: float,
        error: Exception | None = None,
    ) -> None:
        if error:
            self._logger.log(
                self._error_level,
                f"  ✗ {beat_name} failed after {duration:.3f}s: {error}",
            )
        else:
            self._logger.log(
                self._level,
                f"  ✓ {beat_name} ({duration:.3f}s)",
            )


class TimingHooks(CadenceHooks):
    """
    Hooks that collect timing metrics.

    Stores timing data for later analysis.

    Example:
        hooks = TimingHooks()
        cadence = Cadence("test", ctx).with_hooks(hooks)
        await cadence.run()

        print(hooks.get_report())
        print(f"Total: {hooks.total_duration:.3f}s")
    """

    def __init__(self) -> None:
        self._cadence_name: str | None = None
        self._cadence_start: float = 0.0
        self._beat_times: dict[str, float] = {}
        self._total_duration: float = 0.0

    async def before_cadence(self, cadence_name: str, context: ContextT) -> None:
        self._cadence_name = cadence_name
        self._cadence_start = time.perf_counter()
        self._beat_times.clear()

    async def after_cadence(
        self,
        cadence_name: str,
        context: ContextT,
        duration: float,
        error: Exception | None = None,
    ) -> None:
        self._total_duration = duration

    async def after_beat(
        self,
        beat_name: str,
        context: ContextT,
        duration: float,
        error: Exception | None = None,
    ) -> None:
        self._beat_times[beat_name] = duration

    @property
    def beat_times(self) -> dict[str, float]:
        """Get timing data for all beats."""
        return self._beat_times.copy()

    @property
    def total_duration(self) -> float:
        """Get total cadence duration."""
        return self._total_duration

    def get_report(self) -> str:
        """Get a formatted timing report."""
        lines = [f"=== Timing Report: {self._cadence_name} ==="]
        for beat_name, duration in self._beat_times.items():
            pct = (duration / self._total_duration * 100) if self._total_duration > 0 else 0
            lines.append(f"  {beat_name}: {duration:.3f}s ({pct:.1f}%)")
        lines.append(f"  TOTAL: {self._total_duration:.3f}s")
        return "\n".join(lines)


class MetricsHooks(CadenceHooks):
    """
    Hooks that collect metrics for monitoring.

    Tracks:
    - Cadence execution count (success/failure)
    - Beat execution count (success/failure)
    - Latency histograms
    - Error rates

    Example:
        hooks = MetricsHooks()
        # Use with multiple cadences
        cadence1 = Cadence("a", ctx).with_hooks(hooks)
        cadence2 = Cadence("b", ctx).with_hooks(hooks)

        # Export metrics
        print(hooks.get_metrics())
    """

    def __init__(self) -> None:
        self._cadence_counts: dict[str, dict[str, int]] = {}
        self._beat_counts: dict[str, dict[str, int]] = {}
        self._cadence_durations: dict[str, list[float]] = {}
        self._beat_durations: dict[str, list[float]] = {}
        self._retry_counts: dict[str, int] = {}

    async def before_cadence(self, cadence_name: str, context: ContextT) -> None:
        if cadence_name not in self._cadence_counts:
            self._cadence_counts[cadence_name] = {"success": 0, "failure": 0}
            self._cadence_durations[cadence_name] = []

    async def after_cadence(
        self,
        cadence_name: str,
        context: ContextT,
        duration: float,
        error: Exception | None = None,
    ) -> None:
        if error:
            self._cadence_counts[cadence_name]["failure"] += 1
        else:
            self._cadence_counts[cadence_name]["success"] += 1
        self._cadence_durations[cadence_name].append(duration)

    async def after_beat(
        self,
        beat_name: str,
        context: ContextT,
        duration: float,
        error: Exception | None = None,
    ) -> None:
        if beat_name not in self._beat_counts:
            self._beat_counts[beat_name] = {"success": 0, "failure": 0}
            self._beat_durations[beat_name] = []

        if error:
            self._beat_counts[beat_name]["failure"] += 1
        else:
            self._beat_counts[beat_name]["success"] += 1
        self._beat_durations[beat_name].append(duration)

    async def on_retry(
        self,
        beat_name: str,
        context: ContextT,
        attempt: int,
        max_attempts: int,
        error: Exception,
    ) -> None:
        self._retry_counts[beat_name] = self._retry_counts.get(beat_name, 0) + 1

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
            "beats": {
                name: {
                    "success": counts["success"],
                    "failure": counts["failure"],
                    "success_rate": (
                        counts["success"] / (counts["success"] + counts["failure"])
                        if (counts["success"] + counts["failure"]) > 0
                        else 0.0
                    ),
                    "avg_duration": (
                        sum(self._beat_durations[name]) / len(self._beat_durations[name])
                        if self._beat_durations[name]
                        else 0.0
                    ),
                }
                for name, counts in self._beat_counts.items()
            },
            "retries": self._retry_counts.copy(),
        }

    def reset(self) -> None:
        """Reset all metrics."""
        self._cadence_counts.clear()
        self._beat_counts.clear()
        self._cadence_durations.clear()
        self._beat_durations.clear()
        self._retry_counts.clear()


class TracingHooks(CadenceHooks):
    """
    Hooks for distributed tracing integration.

    Creates spans for cadences and beats. Works with any tracing backend
    that follows the OpenTelemetry-style API.

    Example:
        from opentelemetry import trace

        tracer = trace.get_tracer("myapp")
        hooks = TracingHooks(tracer)

        cadence = Cadence("checkout", ctx).with_hooks(hooks)
    """

    def __init__(self, tracer: Any) -> None:
        """
        Initialize with a tracer.

        Args:
            tracer: An OpenTelemetry-compatible tracer
        """
        self._tracer = tracer
        self._cadence_span: Any | None = None
        self._beat_spans: dict[str, Any] = {}

    async def before_cadence(self, cadence_name: str, context: ContextT) -> None:
        self._cadence_span = self._tracer.start_span(f"cadence:{cadence_name}")
        self._cadence_span.set_attribute("cadence.name", cadence_name)

    async def after_cadence(
        self,
        cadence_name: str,
        context: ContextT,
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

    async def before_beat(self, beat_name: str, context: ContextT) -> None:
        span = self._tracer.start_span(
            f"beat:{beat_name}",
            parent=self._cadence_span,
        )
        span.set_attribute("beat.name", beat_name)
        self._beat_spans[beat_name] = span

    async def after_beat(
        self,
        beat_name: str,
        context: ContextT,
        duration: float,
        error: Exception | None = None,
    ) -> None:
        span = self._beat_spans.pop(beat_name, None)
        if span:
            span.set_attribute("beat.duration_ms", duration * 1000)
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

    Prints detailed information about each beat, including context changes.

    Args:
        show_context: Whether to print context after each beat
        show_timing: Whether to print timing info
    """

    def __init__(
        self,
        show_context: bool = True,
        show_timing: bool = True,
    ) -> None:
        self._show_context = show_context
        self._show_timing = show_timing

    async def before_cadence(self, cadence_name: str, context: ContextT) -> None:
        print(f"\n{'='*60}")
        print(f"CADENCE: {cadence_name}")
        print(f"{'='*60}")
        if self._show_context:
            print(f"Initial context: {context}")
        print()

    async def after_cadence(
        self,
        cadence_name: str,
        context: ContextT,
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
        if self._show_context:
            print(f"Final context: {context}")
        print(f"{'='*60}\n")

    async def before_beat(self, beat_name: str, context: ContextT) -> None:
        print(f"→ {beat_name}")

    async def after_beat(
        self,
        beat_name: str,
        context: ContextT,
        duration: float,
        error: Exception | None = None,
    ) -> None:
        status = "✗" if error else "✓"
        timing = f" ({duration:.3f}s)" if self._show_timing else ""
        print(f"  {status}{timing}")
        if error:
            print(f"    Error: {error}")
        if self._show_context:
            print(f"    Context: {context}")


# --- Functional Hooks ---


def before_beat(callback: Callable) -> CadenceHooks:
    """Create a hooks instance with just a before_beat callback."""
    class CallbackHooks(CadenceHooks):
        async def before_beat(self, beat_name: str, context: ContextT) -> None:
            result = callback(beat_name, context)
            if inspect.iscoroutine(result):
                await result

    return CallbackHooks()


def after_beat(callback: Callable) -> CadenceHooks:
    """Create a hooks instance with just an after_beat callback."""
    class CallbackHooks(CadenceHooks):
        async def after_beat(
            self,
            beat_name: str,
            context: ContextT,
            duration: float,
            error: Exception | None = None,
        ) -> None:
            result = callback(beat_name, context, duration, error)
            if inspect.iscoroutine(result):
                await result

    return CallbackHooks()


def on_error(callback: Callable) -> CadenceHooks:
    """Create a hooks instance with just an on_error callback."""
    class CallbackHooks(CadenceHooks):
        async def on_error(
            self,
            beat_name: str,
            context: ContextT,
            error: Exception,
        ) -> bool | None:
            result = callback(beat_name, context, error)
            if inspect.iscoroutine(result):
                result = await result
            return result

    return CallbackHooks()
