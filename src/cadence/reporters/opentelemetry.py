"""OpenTelemetry integration for Cadence tracing and metrics."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

try:
    from opentelemetry import trace  # type: ignore[import-not-found]
    from opentelemetry.metrics import get_meter  # type: ignore[import-not-found]
    from opentelemetry.trace import Span, Status, StatusCode  # type: ignore[import-not-found]

    HAS_OTEL = True
except ImportError:
    HAS_OTEL = False
    trace = None
    get_meter = None
    Span = None
    Status = None
    StatusCode = None

ScoreT = TypeVar("ScoreT")


def _check_otel() -> None:
    """Check if OpenTelemetry is installed."""
    if not HAS_OTEL:
        raise ImportError(
            "OpenTelemetry is required for this reporter. "
            "Install it with: pip install cadence[opentelemetry]"
        )


class OpenTelemetryReporter:
    """
    OpenTelemetry reporter for distributed tracing and metrics.

    Creates spans for each step execution, allowing you to trace
    flow execution across services.

    Example:
        from cadence.reporters.opentelemetry import OpenTelemetryReporter

        otel_reporter = OpenTelemetryReporter(
            service_name="my-service",
            include_state=True,  # Add score as span attributes
        )

        flow = (
            Cadence("checkout", score)
            .with_reporter(otel_reporter)
            .then("validate", validate)
            .then("process", process)
        )
    """

    def __init__(
        self,
        service_name: str = "cadence",
        include_state: bool = False,
        include_timing: bool = True,
        tracer_name: str | None = None,
        meter_name: str | None = None,
    ) -> None:
        """
        Initialize OpenTelemetry reporter.

        Args:
            service_name: Service name for spans
            include_state: Include score fields as span attributes
            include_timing: Record step duration as metrics
            tracer_name: Custom tracer name (default: service_name)
            meter_name: Custom meter name (default: service_name)
        """
        _check_otel()

        self.service_name = service_name
        self.include_state = include_state
        self.include_timing = include_timing

        # Get tracer and meter
        self._tracer = trace.get_tracer(tracer_name or service_name)
        if include_timing:
            self._meter = get_meter(meter_name or service_name)
            self._duration_histogram = self._meter.create_histogram(
                name="cadence.step.duration",
                description="Duration of flow step execution",
                unit="s",
            )
            self._step_counter = self._meter.create_counter(
                name="cadence.step.count",
                description="Number of step executions",
            )

        self._current_spans: dict[str, Span] = {}

    def __call__(
        self,
        step_name: str,
        elapsed: float,
        score: ScoreT,
    ) -> None:
        """Record step completion with tracing and metrics."""
        # Parse flow and step from name
        if ":" in step_name:
            flow_name, actual_step = step_name.split(":", 1)
        else:
            flow_name = "flow"
            actual_step = step_name

        # Create span
        with self._tracer.start_as_current_span(
            name=f"{flow_name}.{actual_step}",
            attributes={
                "cadence.flow.name": flow_name,
                "cadence.step.name": actual_step,
                "cadence.step.duration_ms": elapsed * 1000,
            },
        ) as span:
            # Add score attributes if enabled
            if self.include_state:
                self._add_score_attributes(span, score)

            # Record metrics
            if self.include_timing:
                self._duration_histogram.record(
                    elapsed,
                    attributes={
                        "flow": flow_name,
                        "step": actual_step,
                    },
                )
                self._step_counter.add(
                    1,
                    attributes={
                        "flow": flow_name,
                        "step": actual_step,
                    },
                )

    def _add_score_attributes(self, span: Span, score: ScoreT) -> None:
        """Add score fields as span attributes."""
        if hasattr(score, "__dataclass_fields__"):
            for field_name in score.__dataclass_fields__:
                if field_name.startswith("_"):
                    continue
                try:
                    value = getattr(score, field_name)
                    # Only add simple types
                    if isinstance(value, (str, int, float, bool)):
                        span.set_attribute(f"score.{field_name}", value)
                    elif value is None:
                        span.set_attribute(f"score.{field_name}", "null")
                except Exception:
                    pass


def opentelemetry_reporter(
    service_name: str = "cadence",
    include_state: bool = False,
    include_timing: bool = True,
) -> Callable[[str, float, Any], None]:
    """
    Create an OpenTelemetry reporter function.

    This is a convenience function that creates an OpenTelemetryReporter
    instance and returns its callable.

    Args:
        service_name: Service name for spans
        include_state: Include score fields as span attributes
        include_timing: Record step duration as metrics

    Returns:
        A reporter function for use with Cadence.with_reporter()

    Example:
        from cadence.reporters.opentelemetry import opentelemetry_reporter

        flow = (
            Cadence("checkout", score)
            .with_reporter(opentelemetry_reporter("my-service"))
            .then("process", process)
        )
    """
    return OpenTelemetryReporter(
        service_name=service_name,
        include_state=include_state,
        include_timing=include_timing,
    )


class TracingContext:
    """
    Context manager for creating a parent span around flow execution.

    Use this to wrap entire flows in a parent span, making it easier
    to trace flows in distributed systems.

    Example:
        from cadence.reporters.opentelemetry import TracingContext

        async def handle_request(order_id: str):
            with TracingContext("order-checkout", {"order_id": order_id}):
                result = await checkout_flow.run()
    """

    def __init__(
        self,
        operation_name: str,
        attributes: dict[str, Any] | None = None,
        service_name: str = "cadence",
    ) -> None:
        _check_otel()
        self.operation_name = operation_name
        self.attributes = attributes or {}
        self._tracer = trace.get_tracer(service_name)
        self._span: Span | None = None

    def __enter__(self) -> TracingContext:
        self._span = self._tracer.start_span(
            name=self.operation_name,
            attributes=self.attributes,
        )
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._span:
            if exc_type is not None:
                self._span.set_status(Status(StatusCode.ERROR, str(exc_val)))
                self._span.record_exception(exc_val)
            else:
                self._span.set_status(Status(StatusCode.OK))
            self._span.end()

    def set_attribute(self, key: str, value: Any) -> None:
        """Set an attribute on the current span."""
        if self._span:
            self._span.set_attribute(key, value)

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        """Add an event to the current span."""
        if self._span:
            self._span.add_event(name, attributes=attributes or {})
