"""Child Cadence Composition Example.

This example demonstrates how to compose cadences using child cadences,
allowing you to build modular, reusable workflow components.

Key Concepts:
- Child cadences execute with their own score
- Merge functions transfer results from child to parent
- Child cadences can be nested (child within child)
- Each child maintains its own hooks and reporters
"""

import asyncio
from dataclasses import dataclass, field

from cadence import Cadence, Score, note


# =============================================================================
# Score Definitions
# =============================================================================


@dataclass
class OrderScore(Score):
    """Parent score for an order processing workflow."""
    order_id: str = ""
    customer_id: str = ""
    items: list[dict] | None = None
    subtotal: float = 0.0
    tax: float = 0.0
    shipping: float = 0.0
    total: float = 0.0
    payment_status: str = ""
    fulfillment_status: str = ""
    errors: list[str] = field(default_factory=list)


@dataclass
class PaymentScore(Score):
    """Child score for payment processing."""
    customer_id: str = ""
    amount: float = 0.0
    payment_method: str = ""
    transaction_id: str = ""
    status: str = "pending"
    error: str | None = None


@dataclass
class FulfillmentScore(Score):
    """Child score for order fulfillment."""
    order_id: str = ""
    items: list[dict] | None = None
    warehouse: str = ""
    tracking_number: str = ""
    status: str = "pending"


# =============================================================================
# Payment Processing (Child Cadence)
# =============================================================================


@note
async def validate_payment_method(score: PaymentScore) -> None:
    """Validate the payment method is acceptable."""
    valid_methods = {"credit_card", "debit_card", "paypal", "bank_transfer"}
    if score.payment_method not in valid_methods:
        score.error = f"Invalid payment method: {score.payment_method}"
        score.status = "failed"
        return
    print(f"  Payment method '{score.payment_method}' validated")


@note
async def process_payment(score: PaymentScore) -> None:
    """Process the actual payment."""
    if score.status == "failed":
        return  # Skip if validation failed

    # Simulate payment processing
    await asyncio.sleep(0.1)
    score.transaction_id = f"TXN-{score.customer_id}-{hash(score.amount) % 10000:04d}"
    score.status = "completed"
    print(f"  Payment processed: {score.transaction_id}")


def create_payment_cadence(customer_id: str, amount: float, method: str) -> Cadence:
    """Factory function to create a payment processing cadence."""
    payment_score = PaymentScore(
        customer_id=customer_id,
        amount=amount,
        payment_method=method,
    )
    payment_score.__post_init__()

    return (
        Cadence("payment_processing", payment_score)
        .then("validate", validate_payment_method)
        .then("process", process_payment)
    )


# =============================================================================
# Fulfillment Processing (Child Cadence)
# =============================================================================


@note
async def select_warehouse(score: FulfillmentScore) -> None:
    """Select the best warehouse for fulfillment."""
    # Simulate warehouse selection logic
    score.warehouse = "WAREHOUSE-WEST"
    print(f"  Selected warehouse: {score.warehouse}")


@note
async def reserve_inventory(score: FulfillmentScore) -> None:
    """Reserve inventory for the order."""
    if score.items:
        item_count = sum(item.get("quantity", 1) for item in score.items)
        print(f"  Reserved {item_count} items from {score.warehouse}")


@note
async def generate_tracking(score: FulfillmentScore) -> None:
    """Generate tracking number."""
    score.tracking_number = f"TRK-{score.order_id}-{score.warehouse[-4:]}"
    score.status = "shipped"
    print(f"  Tracking generated: {score.tracking_number}")


def create_fulfillment_cadence(order_id: str, items: list[dict]) -> Cadence:
    """Factory function to create a fulfillment cadence."""
    fulfillment_score = FulfillmentScore(
        order_id=order_id,
        items=items,
    )
    fulfillment_score.__post_init__()

    return (
        Cadence("fulfillment", fulfillment_score)
        .then("select_warehouse", select_warehouse)
        .then("reserve", reserve_inventory)
        .then("tracking", generate_tracking)
    )


# =============================================================================
# Merge Functions
# =============================================================================


def merge_payment_result(parent: OrderScore, child: PaymentScore) -> None:
    """Merge payment processing results into the order."""
    parent.payment_status = child.status
    if child.error:
        parent.errors.append(f"Payment error: {child.error}")
    print(f"  Payment merged: status={child.status}")


def merge_fulfillment_result(parent: OrderScore, child: FulfillmentScore) -> None:
    """Merge fulfillment results into the order."""
    parent.fulfillment_status = child.status
    print(f"  Fulfillment merged: status={child.status}, tracking={child.tracking_number}")


# =============================================================================
# Parent Order Processing Cadence
# =============================================================================


@note
async def initialize_order(score: OrderScore) -> None:
    """Initialize order with sample data."""
    score.items = [
        {"sku": "WIDGET-001", "name": "Premium Widget", "price": 29.99, "quantity": 2},
        {"sku": "GADGET-002", "name": "Super Gadget", "price": 49.99, "quantity": 1},
    ]
    score.subtotal = sum(item["price"] * item["quantity"] for item in score.items)
    print(f"Order {score.order_id}: Initialized with subtotal ${score.subtotal:.2f}")


@note
async def calculate_tax(score: OrderScore) -> None:
    """Calculate tax for the order."""
    tax_rate = 0.08  # 8% tax
    score.tax = score.subtotal * tax_rate
    print(f"Order {score.order_id}: Tax calculated ${score.tax:.2f}")


@note
async def calculate_shipping(score: OrderScore) -> None:
    """Calculate shipping cost."""
    item_count = sum(item.get("quantity", 1) for item in score.items or [])
    score.shipping = 5.99 + (1.99 * max(0, item_count - 1))
    print(f"Order {score.order_id}: Shipping ${score.shipping:.2f}")


@note
async def finalize_total(score: OrderScore) -> None:
    """Calculate final order total."""
    score.total = score.subtotal + score.tax + score.shipping
    print(f"Order {score.order_id}: Total ${score.total:.2f}")


@note
async def complete_order(score: OrderScore) -> None:
    """Mark order as complete or failed."""
    if score.errors:
        print(f"Order {score.order_id}: FAILED - {score.errors}")
    else:
        print(f"Order {score.order_id}: COMPLETED successfully!")


def create_order_cadence(order_id: str, customer_id: str) -> Cadence:
    """Create the main order processing cadence with child cadences."""
    order_score = OrderScore(order_id=order_id, customer_id=customer_id)
    order_score.__post_init__()

    # Create child cadences (these use their own scores)
    payment_cadence = create_payment_cadence(
        customer_id=customer_id,
        amount=150.0,  # Will be updated after calculation
        method="credit_card",
    )

    fulfillment_cadence = create_fulfillment_cadence(
        order_id=order_id,
        items=[],  # Will be populated by initialize_order
    )

    return (
        Cadence("order_processing", order_score)
        # Phase 1: Initialize and calculate
        .then("initialize", initialize_order)
        .then("calculate_tax", calculate_tax)
        .then("calculate_shipping", calculate_shipping)
        .then("finalize_total", finalize_total)
        # Phase 2: Payment (child cadence)
        .child("payment", payment_cadence, merge_payment_result)
        # Phase 3: Fulfillment (child cadence)
        .child("fulfillment", fulfillment_cadence, merge_fulfillment_result)
        # Phase 4: Complete
        .then("complete", complete_order)
    )


# =============================================================================
# Advanced: Nested Child Cadences
# =============================================================================


@dataclass
class NestedOuterScore(Score):
    """Outer score demonstrating nested child cadences."""
    value: int = 0
    inner_results: list[int] = field(default_factory=list)


@dataclass
class NestedMiddleScore(Score):
    """Middle score in nested hierarchy."""
    value: int = 0
    deep_result: int = 0


@dataclass
class NestedInnerScore(Score):
    """Innermost score."""
    value: int = 0


@note
async def multiply_by_two(score: NestedInnerScore) -> None:
    """Inner operation: multiply by 2."""
    score.value *= 2


@note
async def add_ten(score: NestedMiddleScore) -> None:
    """Middle operation: add 10."""
    score.value += 10


@note
async def square(score: NestedOuterScore) -> None:
    """Outer operation: square the value."""
    score.value = score.value ** 2


def merge_inner_to_middle(parent: NestedMiddleScore, child: NestedInnerScore) -> None:
    """Merge inner result to middle."""
    parent.deep_result = child.value


def merge_middle_to_outer(parent: NestedOuterScore, child: NestedMiddleScore) -> None:
    """Merge middle result to outer."""
    parent.inner_results.append(child.deep_result)


def create_nested_example(initial_value: int) -> Cadence:
    """Demonstrate triple-nested child cadences."""
    # Innermost: just multiplies by 2
    inner_score = NestedInnerScore(value=initial_value)
    inner_score.__post_init__()
    inner_cadence = Cadence("inner", inner_score).then("multiply", multiply_by_two)

    # Middle: adds 10, then runs inner
    middle_score = NestedMiddleScore(value=initial_value)
    middle_score.__post_init__()
    middle_cadence = (
        Cadence("middle", middle_score)
        .then("add", add_ten)
        .child("deep", inner_cadence, merge_inner_to_middle)
    )

    # Outer: squares, then runs middle
    outer_score = NestedOuterScore(value=initial_value)
    outer_score.__post_init__()
    return (
        Cadence("outer", outer_score)
        .then("square", square)
        .child("nested", middle_cadence, merge_middle_to_outer)
    )


# =============================================================================
# Main Entry Point
# =============================================================================


async def main():
    """Run the child composition examples."""
    print("=" * 60)
    print("CHILD CADENCE COMPOSITION EXAMPLE")
    print("=" * 60)

    # Example 1: Order Processing with Payment & Fulfillment Children
    print("\n1. Order Processing with Child Cadences")
    print("-" * 40)

    order_cadence = create_order_cadence(
        order_id="ORD-12345",
        customer_id="CUST-001",
    )
    await order_cadence.run()
    order = order_cadence.get_score()

    print(f"\nFinal Order State:")
    print(f"  Order ID: {order.order_id}")
    print(f"  Total: ${order.total:.2f}")
    print(f"  Payment: {order.payment_status}")
    print(f"  Fulfillment: {order.fulfillment_status}")

    # Example 2: Nested Child Cadences
    print("\n" + "=" * 60)
    print("2. Nested Child Cadences (3 Levels Deep)")
    print("-" * 40)

    nested_cadence = create_nested_example(initial_value=5)
    await nested_cadence.run()
    nested = nested_cadence.get_score()

    print(f"\nStarting value: 5")
    print(f"Outer (square): 5^2 = 25")
    print(f"  Middle (add 10): 5 + 10 = 15")
    print(f"    Inner (multiply by 2): 5 * 2 = 10")
    print(f"\nNested result captured: {nested.inner_results}")

    print("\n" + "=" * 60)
    print("EXAMPLES COMPLETED")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
