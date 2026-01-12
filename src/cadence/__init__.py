"""
Cadence - A declarative Python framework for orchestrating service logic with rhythm and precision.

Build APIs and services with explicit, composable control flow.

Example:
    from cadence import Cadence, Context, beat

    @dataclass
    class OrderContext(Context):
        order_id: str
        items: list = None

    @beat
    async def fetch_items(ctx: OrderContext):
        ctx.items = await db.get_items(ctx.order_id)

    cadence = (
        Cadence("checkout", OrderContext(order_id="123"))
        .then("fetch", fetch_items)
        .sync("enrich", [get_prices, get_stock])
        .run()
    )
"""

from cadence.diagram import (
    print_cadence,
    render_svg,
    save_diagram,
    to_dot,
    to_mermaid,
)
from cadence.exceptions import BeatError, CadenceError, RetryExhaustedError, TimeoutError
from cadence.flow import Cadence
from cadence.hooks import (
    CadenceHooks,
    DebugHooks,
    HooksManager,
    LoggingHooks,
    MetricsHooks,
    TimingHooks,
    TracingHooks,
)
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
from cadence.state import (
    Atomic,
    AtomicDict,
    AtomicList,
    Context,
    ImmutableContext,
    MergeConflict,
    MergeStrategy,
    merge_snapshots,
)
from cadence.step import Beat, beat

__version__ = "0.3.0"

__all__ = [
    # Core
    "Cadence",
    "Context",
    "ImmutableContext",
    "beat",
    "Beat",
    # Atomic wrappers
    "Atomic",
    "AtomicList",
    "AtomicDict",
    # Context merging
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
    "BeatError",
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
