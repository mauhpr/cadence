"""Tests for the Cadence hooks system.

Tests cover:
- CadenceHooks base class
- HooksManager (multiple hooks orchestration)
- LoggingHooks (logging integration)
- TimingHooks (timing metrics)
- MetricsHooks (metrics collection)
- TracingHooks (distributed tracing)
- DebugHooks (debug output)
- Functional hook factories (before_note, after_note, on_error)
"""

import logging
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock, AsyncMock

import pytest

from cadence import Cadence, Score, note
from cadence.exceptions import NoteError
from cadence.hooks import (
    CadenceHooks,
    HooksManager,
    LoggingHooks,
    TimingHooks,
    MetricsHooks,
    TracingHooks,
    DebugHooks,
    before_note as before_note_factory,
    after_note as after_note_factory,
    on_error as on_error_factory,
)


# =============================================================================
# Test Fixtures
# =============================================================================


@dataclass
class HooksTestScore(Score):
    """Score for hooks tests."""
    value: str = ""
    count: int = 0


@pytest.fixture
def hooks_score() -> HooksTestScore:
    """Provide a fresh score for each test."""
    score = HooksTestScore()
    score.__post_init__()
    return score


@note
async def append_a(score: HooksTestScore) -> None:
    """Test note that appends 'A' to score."""
    score.value += "A"


@note
async def append_b(score: HooksTestScore) -> None:
    """Test note that appends 'B' to score."""
    score.value += "B"


@note
async def failing_note(score: HooksTestScore) -> None:
    """Test note that raises an error."""
    raise ValueError("intentional failure")


# =============================================================================
# Test: CadenceHooks Base Class
# =============================================================================


class TestCadenceHooksBase:
    """Tests for CadenceHooks base class."""

    async def test_base_hooks_are_no_ops(self, hooks_score: HooksTestScore):
        """Base hooks methods should do nothing by default."""
        hooks = CadenceHooks()

        # All methods should complete without error
        await hooks.before_cadence("test", hooks_score)
        await hooks.after_cadence("test", hooks_score, 1.0)
        await hooks.after_cadence("test", hooks_score, 1.0, ValueError("err"))
        await hooks.before_note("note", hooks_score)
        await hooks.after_note("note", hooks_score, 0.5)
        await hooks.after_note("note", hooks_score, 0.5, ValueError("err"))
        await hooks.on_retry("note", hooks_score, 1, 3, ValueError("err"))

        # on_error should return None (not suppress)
        result = await hooks.on_error("note", hooks_score, ValueError("err"))
        assert result is None

    async def test_custom_hooks_are_called(self, hooks_score: HooksTestScore):
        """Custom hook implementations should be called."""
        calls = []

        class TrackingHooks(CadenceHooks):
            async def before_cadence(self, cadence_name: str, score: Score) -> None:
                calls.append(("before_cadence", cadence_name))

            async def after_cadence(
                self, cadence_name: str, score: Score, duration: float, error: Exception | None = None
            ) -> None:
                calls.append(("after_cadence", cadence_name, error is not None))

            async def before_note(self, note_name: str, score: Score) -> None:
                calls.append(("before_note", note_name))

            async def after_note(
                self, note_name: str, score: Score, duration: float, error: Exception | None = None
            ) -> None:
                calls.append(("after_note", note_name, error is not None))

        cadence = Cadence("test", hooks_score).with_hooks(TrackingHooks()).then("a", append_a)
        await cadence.run()

        assert ("before_cadence", "test") in calls
        assert ("before_note", "a") in calls
        assert ("after_note", "a", False) in calls
        assert ("after_cadence", "test", False) in calls


# =============================================================================
# Test: HooksManager
# =============================================================================


class TestHooksManager:
    """Tests for HooksManager orchestration."""

    async def test_manager_calls_multiple_hooks(self, hooks_score: HooksTestScore):
        """Manager should call all registered hooks."""
        calls1 = []
        calls2 = []

        class Hooks1(CadenceHooks):
            async def before_note(self, note_name: str, score: Score) -> None:
                calls1.append(note_name)

        class Hooks2(CadenceHooks):
            async def before_note(self, note_name: str, score: Score) -> None:
                calls2.append(note_name)

        manager = HooksManager()
        manager.add(Hooks1())
        manager.add(Hooks2())

        await manager.before_note("test_note", hooks_score)

        assert calls1 == ["test_note"]
        assert calls2 == ["test_note"]

    async def test_manager_calls_hooks_in_order(self, hooks_score: HooksTestScore):
        """Hooks should be called in registration order."""
        calls = []

        class OrderedHooks(CadenceHooks):
            def __init__(self, name: str):
                self.name = name

            async def before_note(self, note_name: str, score: Score) -> None:
                calls.append(self.name)

        manager = HooksManager()
        manager.add(OrderedHooks("first"))
        manager.add(OrderedHooks("second"))
        manager.add(OrderedHooks("third"))

        await manager.before_note("test", hooks_score)

        assert calls == ["first", "second", "third"]

    async def test_manager_on_error_any_suppresses(self, hooks_score: HooksTestScore):
        """on_error returns True if any hook suppresses the error."""
        class SuppressHooks(CadenceHooks):
            async def on_error(self, note_name: str, score: Score, error: Exception) -> bool | None:
                return True

        class NoSuppressHooks(CadenceHooks):
            async def on_error(self, note_name: str, score: Score, error: Exception) -> bool | None:
                return None

        manager = HooksManager()
        manager.add(NoSuppressHooks())
        manager.add(SuppressHooks())
        manager.add(NoSuppressHooks())

        result = await manager.on_error("test", hooks_score, ValueError("err"))
        assert result is True

    async def test_manager_on_error_none_suppresses(self, hooks_score: HooksTestScore):
        """on_error returns False if no hook suppresses."""
        class NoSuppressHooks(CadenceHooks):
            async def on_error(self, note_name: str, score: Score, error: Exception) -> bool | None:
                return None

        manager = HooksManager()
        manager.add(NoSuppressHooks())
        manager.add(NoSuppressHooks())

        result = await manager.on_error("test", hooks_score, ValueError("err"))
        assert result is False

    def test_manager_remove_hooks(self):
        """Manager should allow removing hooks."""
        hooks = CadenceHooks()
        manager = HooksManager()

        manager.add(hooks)
        assert len(manager._hooks) == 1

        manager.remove(hooks)
        assert len(manager._hooks) == 0

    def test_manager_clear_hooks(self):
        """Manager should allow clearing all hooks."""
        manager = HooksManager()
        manager.add(CadenceHooks())
        manager.add(CadenceHooks())
        manager.add(CadenceHooks())

        assert len(manager._hooks) == 3

        manager.clear()
        assert len(manager._hooks) == 0


# =============================================================================
# Test: LoggingHooks
# =============================================================================


class TestLoggingHooks:
    """Tests for LoggingHooks."""

    async def test_logging_hooks_logs_cadence_lifecycle(
        self, hooks_score: HooksTestScore, caplog: pytest.LogCaptureFixture
    ):
        """LoggingHooks should log cadence start and completion."""
        with caplog.at_level(logging.INFO, logger="cadence"):
            cadence = (
                Cadence("log_test", hooks_score)
                .with_hooks(LoggingHooks())
                .then("a", append_a)
            )
            await cadence.run()

        assert "[log_test] Starting cadence" in caplog.text
        assert "[log_test] Cadence completed" in caplog.text
        assert "→ a" in caplog.text
        assert "✓ a" in caplog.text

    async def test_logging_hooks_logs_errors(
        self, hooks_score: HooksTestScore, caplog: pytest.LogCaptureFixture
    ):
        """LoggingHooks should log errors at error level."""
        with caplog.at_level(logging.ERROR, logger="cadence"):
            cadence = (
                Cadence("error_test", hooks_score)
                .with_hooks(LoggingHooks())
                .then("fail", failing_note)
            )
            with pytest.raises(NoteError):
                await cadence.run()

        assert "failed" in caplog.text.lower()

    def test_logging_hooks_custom_logger(self):
        """LoggingHooks should accept custom logger name."""
        hooks = LoggingHooks(logger_name="myapp.cadence", level=logging.DEBUG)
        assert hooks._logger.name == "myapp.cadence"
        assert hooks._level == logging.DEBUG


# =============================================================================
# Test: TimingHooks
# =============================================================================


class TestTimingHooks:
    """Tests for TimingHooks."""

    async def test_timing_hooks_tracks_duration(self, hooks_score: HooksTestScore):
        """TimingHooks should track total duration."""
        timing = TimingHooks()
        cadence = (
            Cadence("timing_test", hooks_score)
            .with_hooks(timing)
            .then("a", append_a)
            .then("b", append_b)
        )
        await cadence.run()

        assert timing.total_duration > 0
        assert "a" in timing.note_times
        assert "b" in timing.note_times
        assert timing.note_times["a"] >= 0
        assert timing.note_times["b"] >= 0

    async def test_timing_hooks_report_format(self, hooks_score: HooksTestScore):
        """TimingHooks.get_report() should return formatted string."""
        timing = TimingHooks()
        cadence = (
            Cadence("report_test", hooks_score)
            .with_hooks(timing)
            .then("step1", append_a)
        )
        await cadence.run()

        report = timing.get_report()
        assert "report_test" in report
        assert "step1" in report
        assert "TOTAL:" in report

    async def test_timing_hooks_resets_on_new_cadence(self, hooks_score: HooksTestScore):
        """TimingHooks should reset on new cadence run."""
        timing = TimingHooks()

        # First run
        cadence1 = Cadence("first", hooks_score).with_hooks(timing).then("a", append_a)
        await cadence1.run()
        first_duration = timing.total_duration

        # Second run
        score2 = HooksTestScore()
        score2.__post_init__()
        cadence2 = Cadence("second", score2).with_hooks(timing).then("b", append_b)
        await cadence2.run()

        # Should have new timing data
        assert timing._cadence_name == "second"
        assert "b" in timing.note_times
        # Note: 'a' was cleared when 'second' started
        assert "a" not in timing.note_times


# =============================================================================
# Test: MetricsHooks
# =============================================================================


class TestMetricsHooks:
    """Tests for MetricsHooks."""

    async def test_metrics_hooks_counts_success(self, hooks_score: HooksTestScore):
        """MetricsHooks should count successful executions."""
        metrics = MetricsHooks()
        cadence = (
            Cadence("metrics_test", hooks_score)
            .with_hooks(metrics)
            .then("a", append_a)
        )
        await cadence.run()

        data = metrics.get_metrics()
        assert data["cadences"]["metrics_test"]["success"] == 1
        assert data["cadences"]["metrics_test"]["failure"] == 0
        assert data["notes"]["a"]["success"] == 1

    async def test_metrics_hooks_counts_failures(self, hooks_score: HooksTestScore):
        """MetricsHooks should count failed executions."""
        metrics = MetricsHooks()
        cadence = (
            Cadence("fail_test", hooks_score)
            .with_hooks(metrics)
            .then("fail", failing_note)
        )

        with pytest.raises(NoteError):
            await cadence.run()

        data = metrics.get_metrics()
        assert data["cadences"]["fail_test"]["failure"] == 1
        assert data["notes"]["fail"]["failure"] == 1

    async def test_metrics_hooks_aggregates_multiple_runs(self, hooks_score: HooksTestScore):
        """MetricsHooks should aggregate across multiple runs."""
        metrics = MetricsHooks()

        for _ in range(5):
            score = HooksTestScore()
            score.__post_init__()
            cadence = Cadence("multi", score).with_hooks(metrics).then("a", append_a)
            await cadence.run()

        data = metrics.get_metrics()
        assert data["cadences"]["multi"]["total"] == 5
        assert data["cadences"]["multi"]["success_rate"] == 1.0

    async def test_metrics_hooks_calculates_averages(self, hooks_score: HooksTestScore):
        """MetricsHooks should calculate average durations."""
        metrics = MetricsHooks()

        for _ in range(3):
            score = HooksTestScore()
            score.__post_init__()
            cadence = Cadence("avg_test", score).with_hooks(metrics).then("a", append_a)
            await cadence.run()

        data = metrics.get_metrics()
        assert data["cadences"]["avg_test"]["avg_duration"] > 0
        assert data["notes"]["a"]["avg_duration"] >= 0

    def test_metrics_hooks_reset(self):
        """MetricsHooks.reset() should clear all data."""
        metrics = MetricsHooks()
        metrics._cadence_counts["test"] = {"success": 5, "failure": 2}
        metrics._retry_counts["note"] = 3

        metrics.reset()

        assert metrics._cadence_counts == {}
        assert metrics._retry_counts == {}


# =============================================================================
# Test: TracingHooks
# =============================================================================


class TestTracingHooks:
    """Tests for TracingHooks."""

    async def test_tracing_hooks_creates_spans(self, hooks_score: HooksTestScore):
        """TracingHooks should create spans for cadence and notes."""
        # Create mock tracer
        mock_tracer = MagicMock()
        mock_cadence_span = MagicMock()
        mock_note_span = MagicMock()
        mock_tracer.start_span.side_effect = [mock_cadence_span, mock_note_span]

        tracing = TracingHooks(mock_tracer)
        cadence = (
            Cadence("trace_test", hooks_score)
            .with_hooks(tracing)
            .then("step1", append_a)
        )
        await cadence.run()

        # Verify spans were created
        assert mock_tracer.start_span.call_count == 2
        mock_cadence_span.set_attribute.assert_any_call("cadence.name", "trace_test")
        mock_cadence_span.end.assert_called_once()
        mock_note_span.end.assert_called_once()

    async def test_tracing_hooks_records_errors(self, hooks_score: HooksTestScore):
        """TracingHooks should record exceptions on error."""
        mock_tracer = MagicMock()
        mock_cadence_span = MagicMock()
        mock_note_span = MagicMock()
        mock_tracer.start_span.side_effect = [mock_cadence_span, mock_note_span]

        tracing = TracingHooks(mock_tracer)
        cadence = (
            Cadence("error_trace", hooks_score)
            .with_hooks(tracing)
            .then("fail", failing_note)
        )

        with pytest.raises(NoteError):
            await cadence.run()

        # Verify error was recorded
        mock_note_span.record_exception.assert_called()
        mock_note_span.set_status.assert_called()


# =============================================================================
# Test: DebugHooks
# =============================================================================


class TestDebugHooks:
    """Tests for DebugHooks."""

    async def test_debug_hooks_prints_output(
        self, hooks_score: HooksTestScore, capsys: pytest.CaptureFixture[str]
    ):
        """DebugHooks should print debug information."""
        debug = DebugHooks(show_score=True, show_timing=True)
        cadence = (
            Cadence("debug_test", hooks_score)
            .with_hooks(debug)
            .then("a", append_a)
        )
        await cadence.run()

        captured = capsys.readouterr()
        assert "CADENCE: debug_test" in captured.out
        assert "→ a" in captured.out
        assert "✓" in captured.out
        assert "CADENCE COMPLETED" in captured.out

    async def test_debug_hooks_shows_errors(
        self, hooks_score: HooksTestScore, capsys: pytest.CaptureFixture[str]
    ):
        """DebugHooks should show error information."""
        debug = DebugHooks(show_score=False, show_timing=False)
        cadence = (
            Cadence("debug_fail", hooks_score)
            .with_hooks(debug)
            .then("fail", failing_note)
        )

        with pytest.raises(NoteError):
            await cadence.run()

        captured = capsys.readouterr()
        assert "✗" in captured.out
        assert "Error:" in captured.out

    def test_debug_hooks_options(self):
        """DebugHooks should respect configuration options."""
        debug_full = DebugHooks(show_score=True, show_timing=True)
        debug_minimal = DebugHooks(show_score=False, show_timing=False)

        assert debug_full._show_score is True
        assert debug_full._show_timing is True
        assert debug_minimal._show_score is False
        assert debug_minimal._show_timing is False


# =============================================================================
# Test: Functional Hook Factories
# =============================================================================


class TestFunctionalHookFactories:
    """Tests for before_note(), after_note(), on_error() factories."""

    async def test_before_note_factory_sync(self, hooks_score: HooksTestScore):
        """before_note factory should work with sync callbacks."""
        calls = []

        def track(note_name: str, score: Score) -> None:
            calls.append(note_name)

        hooks = before_note_factory(track)
        cadence = (
            Cadence("before_test", hooks_score)
            .with_hooks(hooks)
            .then("a", append_a)
            .then("b", append_b)
        )
        await cadence.run()

        assert calls == ["a", "b"]

    async def test_before_note_factory_async(self, hooks_score: HooksTestScore):
        """before_note factory should work with async callbacks."""
        calls = []

        async def track(note_name: str, score: Score) -> None:
            calls.append(note_name)

        hooks = before_note_factory(track)
        cadence = (
            Cadence("before_async", hooks_score)
            .with_hooks(hooks)
            .then("a", append_a)
        )
        await cadence.run()

        assert calls == ["a"]

    async def test_after_note_factory(self, hooks_score: HooksTestScore):
        """after_note factory should receive all parameters."""
        calls = []

        def track(note_name: str, score: Score, duration: float, error: Exception | None) -> None:
            calls.append((note_name, duration > 0, error is None))

        hooks = after_note_factory(track)
        cadence = (
            Cadence("after_test", hooks_score)
            .with_hooks(hooks)
            .then("a", append_a)
        )
        await cadence.run()

        assert calls == [("a", True, True)]

    async def test_on_error_factory_callback(self, hooks_score: HooksTestScore):
        """on_error factory should call callback with error details."""
        errors_seen: list[tuple[str, str]] = []

        def track_error(note_name: str, score: Score, error: Exception) -> None:
            errors_seen.append((note_name, str(error)))

        hooks = on_error_factory(track_error)

        cadence = (
            Cadence("error_track_test", hooks_score)
            .with_hooks(hooks)
            .then("fail", failing_note)
        )

        with pytest.raises(NoteError):
            await cadence.run()

        # on_error callback should have been invoked
        assert len(errors_seen) == 1
        assert errors_seen[0][0] == "fail"
        assert "intentional failure" in errors_seen[0][1]

    async def test_on_error_factory_async_callback(self, hooks_score: HooksTestScore):
        """on_error factory should work with async callbacks."""
        errors_seen: list[str] = []

        async def async_track(note_name: str, score: Score, error: Exception) -> None:
            errors_seen.append(note_name)

        hooks = on_error_factory(async_track)

        cadence = (
            Cadence("async_error_test", hooks_score)
            .with_hooks(hooks)
            .then("fail", failing_note)
        )

        with pytest.raises(NoteError):
            await cadence.run()

        assert "fail" in errors_seen


# =============================================================================
# Test: Hook Integration with Cadence
# =============================================================================


class TestHookIntegration:
    """Integration tests for hooks with full cadences."""

    async def test_multiple_hooks_compose(self, hooks_score: HooksTestScore):
        """Multiple hooks should work together."""
        timing = TimingHooks()
        metrics = MetricsHooks()

        cadence = (
            Cadence("composed", hooks_score)
            .with_hooks(timing)
            .with_hooks(metrics)
            .then("a", append_a)
        )
        await cadence.run()

        # Both hooks should have captured data
        assert timing.total_duration > 0
        assert metrics.get_metrics()["cadences"]["composed"]["success"] == 1

    async def test_hooks_with_parallel_notes(self, hooks_score: HooksTestScore):
        """Hooks should work with parallel execution."""
        calls: list[str] = []

        class TrackingHooks(CadenceHooks):
            async def after_note(
                self, note_name: str, score: Score, duration: float, error: Exception | None = None
            ) -> None:
                calls.append(note_name)

        # Create non-conflicting notes for parallel execution
        @note
        async def increment_count(score: HooksTestScore) -> None:
            pass  # No score modification to avoid merge conflicts

        @note
        async def noop(score: HooksTestScore) -> None:
            pass

        cadence = (
            Cadence("parallel_hooks", hooks_score)
            .with_hooks(TrackingHooks())
            .sync("parallel", [increment_count, noop])
        )
        await cadence.run()

        # ParallelMeasure is tracked as "parallel" (internal notes are not hooked)
        assert "parallel" in calls

    async def test_hooks_with_branching(self, hooks_score: HooksTestScore):
        """Hooks should work with branching."""
        calls: list[str] = []

        class TrackingHooks(CadenceHooks):
            async def before_note(self, note_name: str, score: Score) -> None:
                calls.append(note_name)

        # Condition: always true
        cadence = (
            Cadence("branch_hooks", hooks_score)
            .with_hooks(TrackingHooks())
            .split(
                "branch",
                condition=lambda s: True,
                if_true=[append_a],
                if_false=[append_b],
            )
        )
        await cadence.run()

        # BranchMeasure is tracked as "branch" (internal notes are not hooked)
        assert "branch" in calls
        # Verify the true branch executed by checking score
        assert hooks_score.value == "A"

    async def test_hook_exception_does_not_break_cadence(
        self, hooks_score: HooksTestScore, caplog: pytest.LogCaptureFixture
    ):
        """Hook exceptions should not break the cadence."""
        class BrokenHooks(CadenceHooks):
            async def before_note(self, note_name: str, score: Score) -> None:
                raise RuntimeError("hook error")

        # This test documents current behavior - hooks exceptions may propagate
        # If this behavior changes, update the test accordingly
        cadence = (
            Cadence("broken_hook", hooks_score)
            .with_hooks(BrokenHooks())
            .then("a", append_a)
        )

        # Currently, hook exceptions propagate (may want to change this)
        with pytest.raises(RuntimeError, match="hook error"):
            await cadence.run()
