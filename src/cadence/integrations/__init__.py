"""Framework integrations for Cadence."""

# Lazy imports to avoid requiring optional dependencies

def __getattr__(name: str):
    if name == "fastapi":
        from cadence.integrations import fastapi as fastapi_module
        return fastapi_module
    if name in ("CadenceRoute", "cadence_endpoint", "with_cadence", "CadenceDependency", "CadenceMiddleware"):
        from cadence.integrations.fastapi import (
            CadenceDependency,
            CadenceMiddleware,
            CadenceRoute,
            cadence_endpoint,
            with_cadence,
        )
        return locals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
