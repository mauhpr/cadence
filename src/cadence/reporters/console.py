"""Console reporters for development and debugging."""

from __future__ import annotations

import json
from typing import Any


def console_reporter(beat_name: str, elapsed: float, context: Any) -> None:
    """
    Simple console reporter that prints beat timing.

    Example output:
        [checkout] fetch_order: 45.23ms
        [checkout] calculate_total: 1.12ms
        [checkout] TOTAL: 234.56ms
    """
    ms = elapsed * 1000
    if ":TOTAL" in beat_name:
        cadence_name = beat_name.replace(":TOTAL", "")
        print(f"[{cadence_name}] TOTAL: {ms:.2f}ms")
    else:
        print(f"  {beat_name}: {ms:.2f}ms")


def json_reporter(beat_name: str, elapsed: float, context: Any) -> None:
    """
    JSON reporter for structured logging.

    Example output:
        {"beat": "fetch_order", "elapsed_ms": 45.23, "type": "beat"}
        {"beat": "checkout", "elapsed_ms": 234.56, "type": "cadence_total"}
    """
    ms = elapsed * 1000

    if ":TOTAL" in beat_name:
        cadence_name = beat_name.replace(":TOTAL", "")
        record = {
            "beat": cadence_name,
            "elapsed_ms": round(ms, 2),
            "type": "cadence_total",
        }
    else:
        record = {
            "beat": beat_name,
            "elapsed_ms": round(ms, 2),
            "type": "beat",
        }

    print(json.dumps(record))
