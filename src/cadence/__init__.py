"""
Cadence - A declarative Python framework for orchestrating service logic with rhythm and precision.

Build APIs and services with explicit, composable control flow.

Example:
    from cadence import Cadence, Score, note

    @dataclass
    class OrderScore(Score):
        order_id: str
        items: list = None

    @note
    async def fetch_items(score: OrderScore):
        score.items = await db.get_items(score.order_id)

    cadence = (
        Cadence("checkout", OrderScore(order_id="123"))
        .then("fetch", fetch_items)
        .sync("enrich", [get_prices, get_stock])
        .run()
    )
"""

from cadence.cadence import Cadence
from cadence.diagram import (
    print_cadence,
    render_svg,
    save_diagram,
    to_dot,
    to_mermaid,
)
from cadence.exceptions import CadenceError, NoteError, RetryExhaustedError, TimeoutError
from cadence.hooks import (
    CadenceHooks,
    DebugHooks,
    HooksManager,
    LoggingHooks,
    MetricsHooks,
    TimingHooks,
    TracingHooks,
)
from cadence.note import Note, note
from cadence.reporters import console_reporter, json_reporter
from cadence.resilience import (
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
    circuit_breaker,
    fallback,
    retry,
    timeout,
)
from cadence.result import Err, Ok, Result, err, ok
from cadence.score import (
    Atomic,
    AtomicDict,
    AtomicList,
    ImmutableScore,
    MergeConflict,
    MergeStrategy,
    Score,
    merge_snapshots,
)

__version__ = "0.4.0"

__all__ = [
    # Core
    "Cadence",
    "Score",
    "ImmutableScore",
    "note",
    "Note",
    # Atomic wrappers
    "Atomic",
    "AtomicList",
    "AtomicDict",
    # Score merging
    "MergeConflict",
    "MergeStrategy",
    "merge_snapshots",
    # Result types
    "Result",
    "Ok",
    "Err",
    "ok",
    "err",
    # Exceptions
    "CadenceError",
    "NoteError",
    "TimeoutError",
    "RetryExhaustedError",
    "CircuitOpenError",
    # Resilience
    "retry",
    "timeout",
    "fallback",
    "circuit_breaker",
    "CircuitBreaker",
    "CircuitState",
    # Reporters
    "console_reporter",
    "json_reporter",
    # Hooks
    "CadenceHooks",
    "HooksManager",
    "LoggingHooks",
    "TimingHooks",
    "MetricsHooks",
    "TracingHooks",
    "DebugHooks",
    # Diagrams
    "to_mermaid",
    "to_dot",
    "render_svg",
    "save_diagram",
    "print_cadence",
]
