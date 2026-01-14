"""Prometheus metrics integration for Cadence."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

try:
    from prometheus_client import Counter, Gauge, Histogram  # type: ignore[import-not-found]

    HAS_PROMETHEUS = True
except ImportError:
    HAS_PROMETHEUS = False
    Counter = None
    Gauge = None
    Histogram = None

ScoreT = TypeVar("ScoreT")


def _check_prometheus() -> None:
    """Check if prometheus_client is installed."""
    if not HAS_PROMETHEUS:
        raise ImportError(
            "prometheus_client is required for this reporter. "
            "Install it with: pip install cadence-flow[prometheus]"
        )


# Default metrics (created lazily)
_metrics_initialized = False
_step_duration: Histogram | None = None
_step_count: Counter | None = None
_step_errors: Counter | None = None
_flow_duration: Histogram | None = None
_flow_count: Counter | None = None
_active_flows: Gauge | None = None


def _init_metrics(prefix: str = "cadence") -> None:
    """Initialize Prometheus metrics."""
    global _metrics_initialized, _step_duration, _step_count, _step_errors
    global _flow_duration, _flow_count, _active_flows

    if _metrics_initialized:
        return

    _check_prometheus()

    _step_duration = Histogram(
        f"{prefix}_step_duration_seconds",
        "Duration of flow step execution in seconds",
        ["flow", "step"],
        buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    )

    _step_count = Counter(
        f"{prefix}_step_total",
        "Total number of step executions",
        ["flow", "step", "status"],
    )

    _step_errors = Counter(
        f"{prefix}_step_errors_total",
        "Total number of step errors",
        ["flow", "step", "error_type"],
    )

    _flow_duration = Histogram(
        f"{prefix}_flow_duration_seconds",
        "Duration of complete flow execution in seconds",
        ["flow"],
        buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
    )

    _flow_count = Counter(
        f"{prefix}_flow_total",
        "Total number of flow executions",
        ["flow", "status"],
    )

    _active_flows = Gauge(
        f"{prefix}_active_flows",
        "Number of currently executing flows",
        ["flow"],
    )

    _metrics_initialized = True


class PrometheusReporter:
    """
    Prometheus metrics reporter for Cadence.

    Records step durations, counts, and errors as Prometheus metrics.
    Exposes metrics for scraping by Prometheus server.

    Example:
        from cadence.reporters.prometheus import PrometheusReporter

        prom_reporter = PrometheusReporter(prefix="myapp")

        flow = (
            Cadence("checkout", score)
            .with_reporter(prom_reporter)
            .then("validate", validate)
            .then("process", process)
        )

        # In your FastAPI app:
        from prometheus_client import make_asgi_app
        metrics_app = make_asgi_app()
        app.mount("/metrics", metrics_app)
    """

    def __init__(
        self,
        prefix: str = "cadence",
        track_active_flows: bool = True,
    ) -> None:
        """
        Initialize Prometheus reporter.

        Args:
            prefix: Prefix for all metric names
            track_active_flows: Whether to track active flow count
        """
        _check_prometheus()
        _init_metrics(prefix)

        self.prefix = prefix
        self.track_active_flows = track_active_flows

    def __call__(
        self,
        step_name: str,
        elapsed: float,
        score: ScoreT,
    ) -> None:
        """Record step completion metrics."""
        # Parse flow and step from name
        if ":TOTAL" in step_name:
            # This is a flow completion
            flow_name = step_name.replace(":TOTAL", "")
            self._record_flow_completion(flow_name, elapsed)
        else:
            # This is a step completion
            self._record_step_completion(step_name, elapsed)

    def _record_step_completion(self, step_name: str, elapsed: float) -> None:
        """Record step metrics."""
        # Extract flow name from step name pattern like "fetch_data[0]"
        flow_name = "flow"  # Default
        actual_step = step_name

        if "[" in step_name:
            # Parallel/sequence step: fetch_data[0]
            actual_step = step_name.split("[")[0]

        # Record duration
        if _step_duration:
            _step_duration.labels(flow=flow_name, step=actual_step).observe(elapsed)

        # Record count
        if _step_count:
            _step_count.labels(flow=flow_name, step=actual_step, status="success").inc()

    def _record_flow_completion(self, flow_name: str, elapsed: float) -> None:
        """Record flow completion metrics."""
        if _flow_duration:
            _flow_duration.labels(flow=flow_name).observe(elapsed)

        if _flow_count:
            _flow_count.labels(flow=flow_name, status="success").inc()

        if self.track_active_flows and _active_flows:
            _active_flows.labels(flow=flow_name).dec()

    def record_error(
        self,
        flow_name: str,
        step_name: str,
        error: Exception,
    ) -> None:
        """Record an error for a step."""
        error_type = type(error).__name__

        if _step_errors:
            _step_errors.labels(
                flow=flow_name,
                step=step_name,
                error_type=error_type,
            ).inc()

        if _step_count:
            _step_count.labels(
                flow=flow_name,
                step=step_name,
                status="error",
            ).inc()

    def flow_started(self, flow_name: str) -> None:
        """Record flow start for active flow tracking."""
        if self.track_active_flows and _active_flows:
            _active_flows.labels(flow=flow_name).inc()


def prometheus_reporter(
    prefix: str = "cadence",
    track_active_flows: bool = True,
) -> Callable[[str, float, Any], None]:
    """
    Create a Prometheus reporter function.

    This is a convenience function that creates a PrometheusReporter
    instance and returns its callable.

    Args:
        prefix: Prefix for all metric names
        track_active_flows: Whether to track active flow count

    Returns:
        A reporter function for use with Cadence.with_reporter()

    Example:
        from cadence.reporters.prometheus import prometheus_reporter

        flow = (
            Cadence("checkout", score)
            .with_reporter(prometheus_reporter("myapp"))
            .then("process", process)
        )
    """
    return PrometheusReporter(
        prefix=prefix,
        track_active_flows=track_active_flows,
    )


class MetricsMiddleware:
    """
    ASGI middleware that exposes Prometheus metrics endpoint.

    Example:
        from cadence.reporters.prometheus import MetricsMiddleware

        app = FastAPI()
        app.add_middleware(MetricsMiddleware, path="/metrics")
    """

    def __init__(
        self,
        app: Any,
        path: str = "/metrics",
    ) -> None:
        _check_prometheus()
        from prometheus_client import make_asgi_app

        self.app = app
        self.path = path
        self._metrics_app = make_asgi_app()

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[..., Any],
        send: Callable[..., Any],
    ) -> None:
        if scope["type"] == "http" and scope["path"] == self.path:
            await self._metrics_app(scope, receive, send)
        else:
            await self.app(scope, receive, send)
