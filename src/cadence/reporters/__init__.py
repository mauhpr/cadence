"""Built-in reporters for observability."""

from typing import Any

from cadence.reporters.console import console_reporter, json_reporter

__all__ = ["console_reporter", "json_reporter"]


# Lazy imports for optional dependencies
def __getattr__(name: str) -> Any:
    if name in ("OpenTelemetryReporter", "opentelemetry_reporter", "TracingContext"):
        from cadence.reporters import opentelemetry as otel_module

        return getattr(otel_module, name)
    if name in ("PrometheusReporter", "prometheus_reporter", "MetricsMiddleware"):
        from cadence.reporters import prometheus as prom_module

        return getattr(prom_module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
