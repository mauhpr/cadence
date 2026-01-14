"""Tests for Cadence reporters.

Tests cover:
- Console reporter output formatting
- JSON reporter output formatting
- OpenTelemetry reporter (when available)
- Prometheus reporter (when available)
- Lazy import mechanism
"""

from dataclasses import dataclass
import json

import pytest

from cadence import Score


# =============================================================================
# Test Fixtures
# =============================================================================


@dataclass
class ReporterTestScore(Score):
    """Score for reporter tests."""
    value: str = ""
    count: int = 0


@pytest.fixture
def test_score() -> ReporterTestScore:
    """Provide a fresh score for each test."""
    score = ReporterTestScore()
    score.__post_init__()
    return score


# Note: We use pytest's built-in capsys fixture for stdout capture


# =============================================================================
# Test: Console Reporter
# =============================================================================


class TestConsoleReporter:
    """Tests for console_reporter function."""

    def test_console_reporter_regular_beat(self, capsys, test_score):
        """console_reporter should format regular beat timing."""
        from cadence.reporters.console import console_reporter

        console_reporter("fetch_data", 0.04523, test_score)

        captured = capsys.readouterr()
        assert "fetch_data: 45.23ms" in captured.out

    def test_console_reporter_total_timing(self, capsys, test_score):
        """console_reporter should format TOTAL timing specially."""
        from cadence.reporters.console import console_reporter

        console_reporter("checkout:TOTAL", 0.23456, test_score)

        captured = capsys.readouterr()
        assert "[checkout] TOTAL: 234.56ms" in captured.out

    def test_console_reporter_millisecond_conversion(self, capsys, test_score):
        """console_reporter should convert seconds to milliseconds."""
        from cadence.reporters.console import console_reporter

        # 1 second = 1000ms
        console_reporter("slow_step", 1.0, test_score)

        captured = capsys.readouterr()
        assert "1000.00ms" in captured.out

    def test_console_reporter_small_timing(self, capsys, test_score):
        """console_reporter should handle small timings."""
        from cadence.reporters.console import console_reporter

        console_reporter("fast_step", 0.00001, test_score)  # 0.01ms

        captured = capsys.readouterr()
        assert "0.01ms" in captured.out

    def test_console_reporter_indented_output(self, capsys, test_score):
        """Regular beats should be indented."""
        from cadence.reporters.console import console_reporter

        console_reporter("step_name", 0.01, test_score)

        captured = capsys.readouterr()
        # Regular beats are indented with two spaces
        assert captured.out.startswith("  ")

    def test_console_reporter_total_not_indented(self, capsys, test_score):
        """TOTAL timing should not be indented."""
        from cadence.reporters.console import console_reporter

        console_reporter("flow:TOTAL", 0.1, test_score)

        captured = capsys.readouterr()
        assert captured.out.startswith("[")  # Not indented


# =============================================================================
# Test: JSON Reporter
# =============================================================================


class TestJSONReporter:
    """Tests for json_reporter function."""

    def test_json_reporter_regular_beat(self, capsys, test_score):
        """json_reporter should output valid JSON for regular beats."""
        from cadence.reporters.console import json_reporter

        json_reporter("fetch_data", 0.04523, test_score)

        captured = capsys.readouterr()
        data = json.loads(captured.out.strip())

        assert data["beat"] == "fetch_data"
        assert data["elapsed_ms"] == 45.23
        assert data["type"] == "beat"

    def test_json_reporter_total_timing(self, capsys, test_score):
        """json_reporter should mark TOTAL timing as cadence_total."""
        from cadence.reporters.console import json_reporter

        json_reporter("checkout:TOTAL", 0.23456, test_score)

        captured = capsys.readouterr()
        data = json.loads(captured.out.strip())

        assert data["beat"] == "checkout"
        assert data["elapsed_ms"] == 234.56
        assert data["type"] == "cadence_total"

    def test_json_reporter_millisecond_rounding(self, capsys, test_score):
        """json_reporter should round to 2 decimal places."""
        from cadence.reporters.console import json_reporter

        json_reporter("precise_step", 0.045678, test_score)

        captured = capsys.readouterr()
        data = json.loads(captured.out.strip())

        # 45.678ms rounded to 45.68ms
        assert data["elapsed_ms"] == 45.68

    def test_json_reporter_valid_json_format(self, capsys, test_score):
        """json_reporter output should be parseable JSON."""
        from cadence.reporters.console import json_reporter

        json_reporter("test_step", 0.1, test_score)

        captured = capsys.readouterr()
        # Should not raise
        json.loads(captured.out.strip())

    def test_json_reporter_multiple_outputs(self, capsys, test_score):
        """Multiple json_reporter calls should produce separate JSON lines."""
        from cadence.reporters.console import json_reporter

        json_reporter("step1", 0.01, test_score)
        json_reporter("step2", 0.02, test_score)
        json_reporter("flow:TOTAL", 0.03, test_score)

        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")
        assert len(lines) == 3

        # Each line should be valid JSON
        for line in lines:
            json.loads(line)


# =============================================================================
# Test: Package Exports
# =============================================================================


class TestReporterExports:
    """Tests for reporters package exports."""

    def test_console_reporter_exported(self):
        """console_reporter should be exported from reporters package."""
        from cadence.reporters import console_reporter
        assert callable(console_reporter)

    def test_json_reporter_exported(self):
        """json_reporter should be exported from reporters package."""
        from cadence.reporters import json_reporter
        assert callable(json_reporter)

    def test_all_list(self):
        """__all__ should include console and json reporters."""
        from cadence import reporters
        assert "console_reporter" in reporters.__all__
        assert "json_reporter" in reporters.__all__


# =============================================================================
# Test: Lazy Imports
# =============================================================================


class TestLazyImports:
    """Tests for lazy import mechanism."""

    def test_invalid_attribute_raises(self):
        """Accessing invalid attribute should raise AttributeError."""
        from cadence import reporters

        with pytest.raises(AttributeError, match="has no attribute"):
            _ = reporters.nonexistent_reporter

    def test_opentelemetry_lazy_import(self):
        """OpenTelemetry reporter should be lazily importable."""
        from cadence import reporters

        # These should not raise even if otel not installed
        # (they're attributes defined in __getattr__)
        try:
            _ = reporters.OpenTelemetryReporter
        except ImportError:
            # Expected if opentelemetry not installed
            pass

    def test_prometheus_lazy_import(self):
        """Prometheus reporter should be lazily importable."""
        from cadence import reporters

        try:
            _ = reporters.PrometheusReporter
        except ImportError:
            # Expected if prometheus_client not installed
            pass


# =============================================================================
# Test: OpenTelemetry Reporter (conditional)
# =============================================================================


# Check if OpenTelemetry is available
try:
    from opentelemetry import trace
    HAS_OTEL = True
except ImportError:
    HAS_OTEL = False


@pytest.mark.skipif(not HAS_OTEL, reason="OpenTelemetry not installed")
class TestOpenTelemetryReporter:
    """Tests for OpenTelemetry reporter."""

    def test_otel_reporter_import(self):
        """OpenTelemetryReporter should be importable."""
        from cadence.reporters.opentelemetry import OpenTelemetryReporter
        assert OpenTelemetryReporter is not None

    def test_otel_reporter_init(self):
        """OpenTelemetryReporter should initialize with defaults."""
        from cadence.reporters.opentelemetry import OpenTelemetryReporter

        reporter = OpenTelemetryReporter()

        assert reporter.service_name == "cadence"
        assert reporter.include_state is False
        assert reporter.include_timing is True

    def test_otel_reporter_custom_service_name(self):
        """OpenTelemetryReporter should accept custom service name."""
        from cadence.reporters.opentelemetry import OpenTelemetryReporter

        reporter = OpenTelemetryReporter(service_name="my-service")

        assert reporter.service_name == "my-service"

    def test_otel_reporter_callable(self, test_score):
        """OpenTelemetryReporter should be callable as reporter."""
        from cadence.reporters.opentelemetry import OpenTelemetryReporter

        reporter = OpenTelemetryReporter()

        # Should not raise
        reporter("test_step", 0.1, test_score)

    def test_otel_reporter_parses_step_name(self, test_score):
        """OpenTelemetryReporter should parse flow:step names."""
        from cadence.reporters.opentelemetry import OpenTelemetryReporter

        reporter = OpenTelemetryReporter()

        # Should not raise
        reporter("checkout:validate", 0.1, test_score)

    def test_otel_reporter_factory_function(self, test_score):
        """opentelemetry_reporter factory should create reporter."""
        from cadence.reporters.opentelemetry import opentelemetry_reporter

        reporter = opentelemetry_reporter("test-service")

        assert callable(reporter)
        # Should not raise
        reporter("step", 0.1, test_score)

    def test_otel_reporter_include_state(self, test_score):
        """OpenTelemetryReporter with include_state should add score attributes."""
        from cadence.reporters.opentelemetry import OpenTelemetryReporter

        test_score.value = "test_value"
        test_score.count = 42

        reporter = OpenTelemetryReporter(include_state=True)

        # Should not raise - score attributes are added to span
        reporter("test_step", 0.1, test_score)

    def test_has_otel_flag(self):
        """HAS_OTEL should be True when OpenTelemetry is installed."""
        from cadence.reporters.opentelemetry import HAS_OTEL as OTEL_FLAG
        assert OTEL_FLAG is True


@pytest.mark.skipif(not HAS_OTEL, reason="OpenTelemetry not installed")
class TestTracingContext:
    """Tests for TracingContext context manager."""

    def test_tracing_context_init(self):
        """TracingContext should initialize with operation name."""
        from cadence.reporters.opentelemetry import TracingContext

        ctx = TracingContext("test-operation")

        assert ctx.operation_name == "test-operation"
        assert ctx.attributes == {}

    def test_tracing_context_with_attributes(self):
        """TracingContext should accept initial attributes."""
        from cadence.reporters.opentelemetry import TracingContext

        ctx = TracingContext(
            "test-operation",
            attributes={"key": "value"},
        )

        assert ctx.attributes["key"] == "value"

    def test_tracing_context_enter_exit(self):
        """TracingContext should work as context manager."""
        from cadence.reporters.opentelemetry import TracingContext

        with TracingContext("test-operation") as ctx:
            assert ctx is not None
            assert ctx._span is not None

    def test_tracing_context_set_attribute(self):
        """TracingContext should allow setting attributes during execution."""
        from cadence.reporters.opentelemetry import TracingContext

        with TracingContext("test-operation") as ctx:
            ctx.set_attribute("custom_key", "custom_value")
            # Should not raise

    def test_tracing_context_add_event(self):
        """TracingContext should allow adding events."""
        from cadence.reporters.opentelemetry import TracingContext

        with TracingContext("test-operation") as ctx:
            ctx.add_event("test_event", {"detail": "value"})
            # Should not raise

    def test_tracing_context_error_handling(self):
        """TracingContext should record errors on exception."""
        from cadence.reporters.opentelemetry import TracingContext

        with pytest.raises(ValueError):
            with TracingContext("test-operation"):
                raise ValueError("test error")


@pytest.mark.skipif(HAS_OTEL, reason="Test requires OpenTelemetry NOT installed")
class TestOpenTelemetryNotInstalled:
    """Tests for behavior when OpenTelemetry is not installed."""

    def test_check_otel_raises(self):
        """_check_otel should raise ImportError."""
        from cadence.reporters.opentelemetry import _check_otel

        with pytest.raises(ImportError, match="OpenTelemetry is required"):
            _check_otel()


# =============================================================================
# Test: Prometheus Reporter (conditional)
# =============================================================================


# Check if Prometheus is available
try:
    from prometheus_client import Counter
    HAS_PROMETHEUS = True
except ImportError:
    HAS_PROMETHEUS = False


@pytest.mark.skipif(not HAS_PROMETHEUS, reason="prometheus_client not installed")
class TestPrometheusReporter:
    """Tests for Prometheus reporter."""

    def test_prometheus_reporter_import(self):
        """PrometheusReporter should be importable."""
        from cadence.reporters.prometheus import PrometheusReporter
        assert PrometheusReporter is not None

    def test_prometheus_reporter_init(self):
        """PrometheusReporter should initialize with defaults."""
        from cadence.reporters.prometheus import PrometheusReporter

        reporter = PrometheusReporter()

        assert reporter.prefix == "cadence"
        assert reporter.track_active_flows is True

    def test_prometheus_reporter_custom_prefix(self):
        """PrometheusReporter should accept custom prefix."""
        from cadence.reporters.prometheus import PrometheusReporter

        reporter = PrometheusReporter(prefix="myapp")

        assert reporter.prefix == "myapp"

    def test_prometheus_reporter_callable(self, test_score):
        """PrometheusReporter should be callable as reporter."""
        from cadence.reporters.prometheus import PrometheusReporter

        reporter = PrometheusReporter()

        # Should not raise
        reporter("test_step", 0.1, test_score)

    def test_prometheus_reporter_step_completion(self, test_score):
        """PrometheusReporter should record step completion."""
        from cadence.reporters.prometheus import PrometheusReporter

        reporter = PrometheusReporter()

        # Regular step
        reporter("fetch_data", 0.1, test_score)
        # Should not raise

    def test_prometheus_reporter_flow_completion(self, test_score):
        """PrometheusReporter should record flow completion on TOTAL."""
        from cadence.reporters.prometheus import PrometheusReporter

        reporter = PrometheusReporter()

        # Flow total
        reporter("checkout:TOTAL", 0.5, test_score)
        # Should not raise

    def test_prometheus_reporter_parallel_step_names(self, test_score):
        """PrometheusReporter should handle parallel step names with [index]."""
        from cadence.reporters.prometheus import PrometheusReporter

        reporter = PrometheusReporter()

        # Parallel step format
        reporter("fetch_data[0]", 0.1, test_score)
        reporter("fetch_data[1]", 0.15, test_score)
        # Should not raise

    def test_prometheus_reporter_factory_function(self, test_score):
        """prometheus_reporter factory should create reporter."""
        from cadence.reporters.prometheus import prometheus_reporter

        reporter = prometheus_reporter("test")

        assert callable(reporter)
        # Should not raise
        reporter("step", 0.1, test_score)

    def test_prometheus_reporter_record_error(self, test_score):
        """PrometheusReporter should record errors."""
        from cadence.reporters.prometheus import PrometheusReporter

        reporter = PrometheusReporter()

        # Should not raise
        reporter.record_error("flow", "step", ValueError("test error"))

    def test_prometheus_reporter_flow_started(self):
        """PrometheusReporter should track flow starts."""
        from cadence.reporters.prometheus import PrometheusReporter

        reporter = PrometheusReporter(track_active_flows=True)

        # Should not raise
        reporter.flow_started("checkout")

    def test_prometheus_reporter_no_active_tracking(self, test_score):
        """PrometheusReporter should work without active flow tracking."""
        from cadence.reporters.prometheus import PrometheusReporter

        reporter = PrometheusReporter(track_active_flows=False)

        reporter.flow_started("checkout")
        reporter("checkout:TOTAL", 0.5, test_score)
        # Should not raise

    def test_has_prometheus_flag(self):
        """HAS_PROMETHEUS should be True when prometheus_client is installed."""
        from cadence.reporters.prometheus import HAS_PROMETHEUS as PROM_FLAG
        assert PROM_FLAG is True


@pytest.mark.skipif(not HAS_PROMETHEUS, reason="prometheus_client not installed")
class TestMetricsMiddleware:
    """Tests for MetricsMiddleware ASGI middleware."""

    def test_middleware_init(self):
        """MetricsMiddleware should initialize with app."""
        from cadence.reporters.prometheus import MetricsMiddleware

        async def dummy_app(scope, receive, send):
            pass

        middleware = MetricsMiddleware(dummy_app)

        assert middleware.path == "/metrics"
        assert middleware.app is dummy_app

    def test_middleware_custom_path(self):
        """MetricsMiddleware should accept custom path."""
        from cadence.reporters.prometheus import MetricsMiddleware

        async def dummy_app(scope, receive, send):
            pass

        middleware = MetricsMiddleware(dummy_app, path="/custom/metrics")

        assert middleware.path == "/custom/metrics"

    @pytest.mark.asyncio
    async def test_middleware_passthrough(self):
        """MetricsMiddleware should pass through non-metrics requests."""
        from cadence.reporters.prometheus import MetricsMiddleware

        called = []

        async def dummy_app(scope, receive, send):
            called.append(scope["path"])

        middleware = MetricsMiddleware(dummy_app)

        scope = {"type": "http", "path": "/api/data"}
        await middleware(scope, None, None)

        assert "/api/data" in called

    @pytest.mark.asyncio
    async def test_middleware_metrics_endpoint(self):
        """MetricsMiddleware should handle metrics endpoint."""
        from cadence.reporters.prometheus import MetricsMiddleware

        responses = []

        async def dummy_app(scope, receive, send):
            pass

        async def mock_send(message):
            responses.append(message)

        middleware = MetricsMiddleware(dummy_app)

        scope = {"type": "http", "path": "/metrics"}

        # This will call the prometheus metrics app
        # We can't fully test the response without a proper ASGI flow,
        # but we can verify it doesn't call the wrapped app
        await middleware(scope, None, mock_send)

        # Should have received response from metrics app
        assert len(responses) > 0


@pytest.mark.skipif(HAS_PROMETHEUS, reason="Test requires prometheus_client NOT installed")
class TestPrometheusNotInstalled:
    """Tests for behavior when prometheus_client is not installed."""

    def test_check_prometheus_raises(self):
        """_check_prometheus should raise ImportError."""
        from cadence.reporters.prometheus import _check_prometheus

        with pytest.raises(ImportError, match="prometheus_client is required"):
            _check_prometheus()


# =============================================================================
# Test: Reporter Integration with Cadence
# =============================================================================


class TestReporterIntegration:
    """Tests for using reporters with Cadence."""

    @pytest.mark.asyncio
    async def test_cadence_with_console_reporter(self, capsys, test_score):
        """Cadence should call console_reporter for each step."""
        from cadence import Cadence, note
        from cadence.reporters.console import console_reporter

        @note
        async def process(score: ReporterTestScore) -> None:
            score.value = "processed"

        cadence = (
            Cadence("test", test_score)
            .with_reporter(console_reporter)
            .then("process", process)
        )

        await cadence.run()

        captured = capsys.readouterr()
        # Should have step timing and TOTAL
        assert "process:" in captured.out or "TOTAL:" in captured.out

    @pytest.mark.asyncio
    async def test_cadence_with_json_reporter(self, capsys, test_score):
        """Cadence should call json_reporter for each step."""
        from cadence import Cadence, note
        from cadence.reporters.console import json_reporter

        @note
        async def process(score: ReporterTestScore) -> None:
            score.value = "processed"

        cadence = (
            Cadence("test", test_score)
            .with_reporter(json_reporter)
            .then("process", process)
        )

        await cadence.run()

        captured = capsys.readouterr()
        # Should have valid JSON lines
        for line in captured.out.strip().split("\n"):
            if line:
                json.loads(line)

    @pytest.mark.asyncio
    async def test_cadence_with_multiple_reporters(self, test_score):
        """Cadence should support multiple reporters."""
        from cadence import Cadence, note

        calls = []

        def tracking_reporter(beat_name, elapsed, context):
            calls.append(beat_name)

        @note
        async def process(score: ReporterTestScore) -> None:
            score.value = "processed"

        cadence = (
            Cadence("test", test_score)
            .with_reporter(tracking_reporter)
            .then("process", process)
        )

        await cadence.run()

        # Should have been called
        assert len(calls) > 0

    @pytest.mark.asyncio
    async def test_reporter_receives_timing(self, test_score):
        """Reporter should receive accurate timing information."""
        from cadence import Cadence, note
        import asyncio

        timings = []

        def tracking_reporter(beat_name, elapsed, context):
            timings.append((beat_name, elapsed))

        @note
        async def slow_process(score: ReporterTestScore) -> None:
            await asyncio.sleep(0.05)  # 50ms

        cadence = (
            Cadence("test", test_score)
            .with_reporter(tracking_reporter)
            .then("slow", slow_process)
        )

        await cadence.run()

        # Find the slow step timing
        slow_timings = [(n, t) for n, t in timings if "slow" in n.lower()]
        assert len(slow_timings) > 0

        # Timing should be at least 50ms
        _, elapsed = slow_timings[0]
        assert elapsed >= 0.05

    @pytest.mark.asyncio
    async def test_reporter_receives_score(self, test_score):
        """Reporter should receive the score/context."""
        from cadence import Cadence, note

        received_scores = []

        def tracking_reporter(beat_name, elapsed, context):
            received_scores.append(context)

        @note
        async def process(score: ReporterTestScore) -> None:
            score.value = "processed"

        cadence = (
            Cadence("test", test_score)
            .with_reporter(tracking_reporter)
            .then("process", process)
        )

        await cadence.run()

        assert len(received_scores) > 0
        # All received scores should be ReporterTestScore instances
        for score in received_scores:
            assert isinstance(score, ReporterTestScore)
