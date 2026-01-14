"""Framework integrations for Cadence."""

from typing import Any

# Lazy imports to avoid requiring optional dependencies


_FASTAPI_NAMES = (
    "CadenceRoute",
    "cadence_endpoint",
    "with_cadence",
    "CadenceDependency",
    "CadenceMiddleware",
)


def __getattr__(name: str) -> Any:
    if name == "fastapi":
        from cadence.integrations import fastapi as fastapi_module

        return fastapi_module
    if name in _FASTAPI_NAMES:
        from cadence.integrations import fastapi as fastapi_module

        return getattr(fastapi_module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
