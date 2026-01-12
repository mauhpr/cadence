"""Built-in reporters for observability."""

from cadence.reporters.console import console_reporter, json_reporter

__all__ = ["console_reporter", "json_reporter"]


# Lazy imports for optional dependencies
def __getattr__(name: str):
    if name in ("OpenTelemetryReporter", "opentelemetry_reporter", "TracingContext"):
        from cadence.reporters.opentelemetry import (
            OpenTelemetryReporter,
            TracingContext,
            opentelemetry_reporter,
        )
        return locals()[name]
    if name in ("PrometheusReporter", "prometheus_reporter", "MetricsMiddleware"):
        from cadence.reporters.prometheus import (
            MetricsMiddleware,
            PrometheusReporter,
            prometheus_reporter,
        )
        return locals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
