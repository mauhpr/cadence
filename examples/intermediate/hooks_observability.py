"""
Hooks and Observability Example

This example demonstrates using Cadence's hooks system for
logging, timing, metrics collection, and debugging.
"""

import asyncio
import logging
import random
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

from cadence import (
    Cadence,
    Score,
    note,
    retry,
    timeout,
    CadenceHooks,
    LoggingHooks,
    TimingHooks,
    MetricsHooks,
    DebugHooks,
)


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


# --- Score Definition ---


@dataclass
class OrderScore(Score):
    """Score for order processing cadence."""
    order_id: str
    customer_id: str
    items: List[Dict[str, Any]] = field(default_factory=list)

    # Populated by notes
    validated: bool = False
    total: float = 0.0
    payment_status: Optional[str] = None
    shipment_id: Optional[str] = None
    notifications_sent: bool = False


# --- Custom Hooks ---


class AlertingHooks(CadenceHooks):
    """
    Custom hooks that send alerts on failures.

    In production, this would integrate with PagerDuty, Slack, etc.
    """

    def __init__(self, alert_threshold: int = 3):
        self._failure_counts: Dict[str, int] = {}
        self._alert_threshold = alert_threshold

    async def on_error(
        self,
        note_name: str,
        context: Any,
        error: Exception,
    ) -> Optional[bool]:
        """Track failures and alert if threshold exceeded."""
        self._failure_counts[note_name] = self._failure_counts.get(note_name, 0) + 1

        if self._failure_counts[note_name] >= self._alert_threshold:
            print(f"\n🚨 ALERT: Note '{note_name}' has failed {self._failure_counts[note_name]} times!")
            print(f"   Error: {error}")
            # In production: send to alerting system
            # await pagerduty.create_incident(...)

        return None  # Don't suppress the error

    async def on_retry(
        self,
        note_name: str,
        context: Any,
        attempt: int,
        max_attempts: int,
        error: Exception,
    ) -> None:
        """Log retry attempts."""
        print(f"   ⟳ Retry {attempt}/{max_attempts} for '{note_name}': {error}")


class AuditHooks(CadenceHooks):
    """
    Custom hooks that maintain an audit log of all operations.

    Useful for compliance and debugging.
    """

    def __init__(self):
        self._audit_log: List[Dict[str, Any]] = []

    async def before_cadence(self, cadence_name: str, context: Any) -> None:
        self._audit_log.append({
            "event": "cadence_started",
            "cadence": cadence_name,
            "context": str(context),
        })

    async def after_cadence(
        self,
        cadence_name: str,
        context: Any,
        duration: float,
        error: Optional[Exception] = None,
    ) -> None:
        self._audit_log.append({
            "event": "cadence_completed",
            "cadence": cadence_name,
            "duration": duration,
            "success": error is None,
            "error": str(error) if error else None,
        })

    async def before_note(self, note_name: str, context: Any) -> None:
        self._audit_log.append({
            "event": "note_started",
            "note": note_name,
        })

    async def after_note(
        self,
        note_name: str,
        context: Any,
        duration: float,
        error: Optional[Exception] = None,
    ) -> None:
        self._audit_log.append({
            "event": "note_completed",
            "note": note_name,
            "duration": duration,
            "success": error is None,
        })

    def get_audit_log(self) -> List[Dict[str, Any]]:
        """Get the complete audit log."""
        return self._audit_log.copy()


# --- Notes ---


@note
async def validate_order(score: OrderScore) -> None:
    """Validate the order items and customer."""
    await asyncio.sleep(0.02)
    if not score.items:
        raise ValueError("Order must have at least one item")
    score.validated = True


@note
async def calculate_total(score: OrderScore) -> None:
    """Calculate order total."""
    await asyncio.sleep(0.015)
    score.total = sum(item.get("price", 0) * item.get("quantity", 1) for item in score.items)


@note
@retry(max_attempts=3, backoff="exponential", base_delay=0.1)
@timeout(2.0)
async def process_payment(score: OrderScore) -> None:
    """Process payment - may fail randomly to demonstrate retries."""
    await asyncio.sleep(0.03)

    # Simulate occasional failures
    if random.random() < 0.4:  # 40% failure rate
        raise ConnectionError("Payment gateway timeout")

    score.payment_status = "completed"


@note
@timeout(1.0)
async def create_shipment(score: OrderScore) -> None:
    """Create shipment for the order."""
    await asyncio.sleep(0.02)
    score.shipment_id = f"SHIP-{score.order_id}"


@note
async def send_notifications(score: OrderScore) -> None:
    """Send order confirmation notifications."""
    await asyncio.sleep(0.01)
    score.notifications_sent = True


# --- Cadence Definition ---


def create_order_cadence(score: OrderScore, hooks: List[CadenceHooks]) -> Cadence[OrderScore]:
    """Create an order processing cadence with hooks."""
    cadence = Cadence("process_order", score)

    # Add all hooks
    for hook in hooks:
        cadence = cadence.with_hooks(hook)

    return (
        cadence
        .then("validate", validate_order)
        .then("calculate", calculate_total)
        .then("payment", process_payment)
        .sync("fulfill", [
            create_shipment,
            send_notifications,
        ])
    )


# --- Demo Functions ---


async def demo_logging_hooks():
    """Demonstrate logging hooks."""
    print("\n" + "=" * 60)
    print("DEMO: LoggingHooks")
    print("=" * 60 + "\n")

    score = OrderScore(
        order_id="ORD-001",
        customer_id="CUST-123",
        items=[{"name": "Widget", "price": 29.99, "quantity": 2}],
    )

    cadence = create_order_cadence(score, [LoggingHooks()])
    result = await cadence.run()

    print(f"\nOrder processed: total=${result.total:.2f}")


async def demo_timing_hooks():
    """Demonstrate timing hooks."""
    print("\n" + "=" * 60)
    print("DEMO: TimingHooks")
    print("=" * 60 + "\n")

    score = OrderScore(
        order_id="ORD-002",
        customer_id="CUST-456",
        items=[{"name": "Gadget", "price": 99.99, "quantity": 1}],
    )

    timing = TimingHooks()
    cadence = create_order_cadence(score, [timing])

    await cadence.run()

    print("\nTiming Report:")
    print(timing.get_report())


async def demo_metrics_hooks():
    """Demonstrate metrics collection."""
    print("\n" + "=" * 60)
    print("DEMO: MetricsHooks - Running 5 orders")
    print("=" * 60 + "\n")

    metrics = MetricsHooks()

    for i in range(5):
        score = OrderScore(
            order_id=f"ORD-{100 + i}",
            customer_id=f"CUST-{200 + i}",
            items=[{"name": f"Item-{i}", "price": 10.0 + i * 5, "quantity": 1}],
        )

        try:
            cadence = create_order_cadence(score, [metrics])
            await cadence.run()
            print(f"  ✓ Order {score.order_id} completed")
        except Exception as e:
            print(f"  ✗ Order {score.order_id} failed: {e}")

    print("\nMetrics Summary:")
    import json
    print(json.dumps(metrics.get_metrics(), indent=2))


async def demo_custom_hooks():
    """Demonstrate custom hooks."""
    print("\n" + "=" * 60)
    print("DEMO: Custom Hooks (Alerting + Audit)")
    print("=" * 60 + "\n")

    alerting = AlertingHooks(alert_threshold=2)
    audit = AuditHooks()

    score = OrderScore(
        order_id="ORD-003",
        customer_id="CUST-789",
        items=[{"name": "Premium Widget", "price": 199.99, "quantity": 1}],
    )

    try:
        cadence = create_order_cadence(score, [alerting, audit])
        result = await cadence.run()
        print(f"\n✓ Order processed successfully")
    except Exception as e:
        print(f"\n✗ Order failed: {e}")

    print("\nAudit Log:")
    for entry in audit.get_audit_log():
        print(f"  {entry['event']}: {entry.get('note') or entry.get('cadence')}")


async def demo_debug_hooks():
    """Demonstrate debug hooks."""
    print("\n" + "=" * 60)
    print("DEMO: DebugHooks - Detailed Execution Trace")
    print("=" * 60)

    score = OrderScore(
        order_id="ORD-004",
        customer_id="CUST-000",
        items=[{"name": "Debug Widget", "price": 49.99, "quantity": 3}],
    )

    cadence = create_order_cadence(score, [DebugHooks(show_context=True, show_timing=True)])

    try:
        await cadence.run()
    except Exception:
        pass  # DebugHooks will show the error


async def demo_combined_hooks():
    """Demonstrate combining multiple hooks."""
    print("\n" + "=" * 60)
    print("DEMO: Combined Hooks (Logging + Timing + Metrics)")
    print("=" * 60 + "\n")

    timing = TimingHooks()
    metrics = MetricsHooks()

    score = OrderScore(
        order_id="ORD-005",
        customer_id="CUST-999",
        items=[
            {"name": "Widget A", "price": 25.00, "quantity": 2},
            {"name": "Widget B", "price": 35.00, "quantity": 1},
        ],
    )

    cadence = create_order_cadence(score, [
        LoggingHooks(),
        timing,
        metrics,
    ])

    await cadence.run()

    print("\n" + timing.get_report())


# --- Main ---


async def main():
    print("Cadence Hooks & Observability Demo")
    print("=" * 60)

    # Run all demos
    await demo_logging_hooks()
    await demo_timing_hooks()
    await demo_metrics_hooks()
    await demo_custom_hooks()
    await demo_debug_hooks()
    await demo_combined_hooks()

    print("\n✓ All demos completed!")


if __name__ == "__main__":
    asyncio.run(main())
