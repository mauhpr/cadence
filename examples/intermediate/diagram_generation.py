"""
Diagram Generation Example

This example demonstrates Cadence's diagram generation capabilities:
- Generating Mermaid diagrams for documentation
- Generating DOT (Graphviz) diagrams
- Saving diagrams to files
- Text-based cadence visualization
- Customizing diagram appearance
"""

import asyncio
from dataclasses import dataclass, field

from cadence import Cadence, Score, note
from cadence.diagram import (
    to_mermaid,
    to_dot,
    print_cadence,
    save_diagram,
)


# --- Score Definitions ---


@dataclass
class OrderScore(Score):
    """Score for order processing cadence."""
    order_id: str
    customer_id: str
    is_premium: bool = False
    items: list[dict] = field(default_factory=list)
    total: float = 0.0
    discount: float = 0.0
    shipping_cost: float = 0.0
    status: str = "pending"


@dataclass
class PaymentScore(Score):
    """Score for payment processing sub-cadence."""
    amount: float = 0.0
    method: str = "credit_card"
    processed: bool = False
    transaction_id: str = ""


# --- Note Definitions ---


@note
async def validate_order(score: OrderScore) -> None:
    """Validate the order details."""
    await asyncio.sleep(0.01)
    print(f"  Validating order {score.order_id}")


@note
async def fetch_customer(score: OrderScore) -> None:
    """Fetch customer information."""
    await asyncio.sleep(0.01)
    print(f"  Fetching customer {score.customer_id}")


@note
async def fetch_inventory(score: OrderScore) -> None:
    """Check inventory availability."""
    await asyncio.sleep(0.01)
    print("  Checking inventory")


@note
async def calculate_shipping(score: OrderScore) -> None:
    """Calculate shipping costs."""
    await asyncio.sleep(0.01)
    score.shipping_cost = 9.99 if not score.is_premium else 0.0
    print(f"  Shipping: ${score.shipping_cost}")


@note
async def apply_premium_discount(score: OrderScore) -> None:
    """Apply premium customer discount."""
    await asyncio.sleep(0.01)
    score.discount = score.total * 0.15
    print(f"  Premium discount: ${score.discount:.2f}")


@note
async def apply_standard_pricing(score: OrderScore) -> None:
    """Apply standard pricing (no discount)."""
    await asyncio.sleep(0.01)
    score.discount = 0.0
    print("  Standard pricing applied")


@note
async def process_payment(score: OrderScore) -> None:
    """Process the payment."""
    await asyncio.sleep(0.01)
    print("  Processing payment")


@note
async def send_confirmation(score: OrderScore) -> None:
    """Send order confirmation."""
    await asyncio.sleep(0.01)
    score.status = "confirmed"
    print(f"  Order {score.order_id} confirmed!")


@note
async def update_analytics(score: OrderScore) -> None:
    """Update analytics."""
    await asyncio.sleep(0.01)
    print("  Analytics updated")


# --- Condition Functions ---


def is_premium_customer(score: OrderScore) -> bool:
    """Check if customer is premium."""
    return score.is_premium


# --- Cadence Builders ---


def create_simple_cadence(score: OrderScore) -> Cadence[OrderScore]:
    """Create a simple sequential cadence for basic diagram demo."""
    return (
        Cadence("simple_checkout", score)
        .then("validate", validate_order)
        .then("process_payment", process_payment)
        .then("confirm", send_confirmation)
    )


def create_parallel_cadence(score: OrderScore) -> Cadence[OrderScore]:
    """Create a cadence with parallel execution for diagram demo."""
    return (
        Cadence("parallel_checkout", score)
        .then("validate", validate_order)
        .sync("fetch_data", [
            fetch_customer,
            fetch_inventory,
            calculate_shipping,
        ])
        .then("process_payment", process_payment)
        .then("confirm", send_confirmation)
    )


def create_branching_cadence(score: OrderScore) -> Cadence[OrderScore]:
    """Create a cadence with branching for diagram demo."""
    return (
        Cadence("branching_checkout", score)
        .then("validate", validate_order)
        .split(
            "pricing",
            condition=is_premium_customer,
            if_true=[apply_premium_discount],
            if_false=[apply_standard_pricing],
        )
        .then("process_payment", process_payment)
        .then("confirm", send_confirmation)
    )


def create_complex_cadence(score: OrderScore) -> Cadence[OrderScore]:
    """Create a complex cadence combining all patterns."""
    return (
        Cadence("complex_checkout", score)
        # Initial validation
        .then("validate", validate_order)
        # Parallel data fetching
        .sync("enrich", [
            fetch_customer,
            fetch_inventory,
        ])
        # Conditional pricing
        .split(
            "pricing",
            condition=is_premium_customer,
            if_true=[apply_premium_discount],
            if_false=[apply_standard_pricing],
        )
        # Calculate shipping after pricing
        .then("shipping", calculate_shipping)
        # Process payment
        .then("payment", process_payment)
        # Parallel notifications
        .sync("notify", [
            send_confirmation,
            update_analytics,
        ])
    )


# --- Demo Functions ---


def demo_text_visualization():
    """Demo: Print text representation of cadences."""
    print("\n" + "=" * 60)
    print("DEMO 1: Text-Based Cadence Visualization")
    print("=" * 60)
    print("\nUsing print_cadence() for quick debugging:\n")

    score = OrderScore(order_id="ORD-001", customer_id="CUST-100")

    print("--- Simple Cadence ---")
    simple = create_simple_cadence(score)
    print_cadence(simple)

    print("--- Parallel Cadence ---")
    parallel = create_parallel_cadence(score)
    print_cadence(parallel)

    print("--- Branching Cadence ---")
    branching = create_branching_cadence(score)
    print_cadence(branching)

    print("--- Complex Cadence ---")
    complex_cadence = create_complex_cadence(score)
    print_cadence(complex_cadence)


def demo_mermaid_generation():
    """Demo: Generate Mermaid diagrams."""
    print("\n" + "=" * 60)
    print("DEMO 2: Mermaid Diagram Generation")
    print("=" * 60)

    score = OrderScore(
        order_id="ORD-001",
        customer_id="CUST-100",
        is_premium=True,
    )

    # Simple cadence
    print("\n--- Simple Cadence (Top-Down) ---\n")
    simple = create_simple_cadence(score)
    mermaid = to_mermaid(simple)
    print(mermaid)

    # Parallel cadence with left-right direction
    print("\n--- Parallel Cadence (Left-Right) ---\n")
    parallel = create_parallel_cadence(score)
    mermaid = to_mermaid(parallel, direction="LR")
    print(mermaid)

    # Complex cadence with theme
    print("\n--- Complex Cadence (with dark theme) ---\n")
    complex_cadence = create_complex_cadence(score)
    mermaid = to_mermaid(complex_cadence, theme="dark")
    print(mermaid)

    print("\n  Usage tip: Copy the above code into a Mermaid-compatible")
    print("  renderer like https://mermaid.live or GitHub markdown")
    print("  using ```mermaid ... ``` code blocks.")


def demo_dot_generation():
    """Demo: Generate DOT (Graphviz) diagrams."""
    print("\n" + "=" * 60)
    print("DEMO 3: DOT (Graphviz) Diagram Generation")
    print("=" * 60)

    score = OrderScore(order_id="ORD-001", customer_id="CUST-100")

    # Simple cadence
    print("\n--- Simple Cadence ---\n")
    simple = create_simple_cadence(score)
    dot = to_dot(simple)
    print(dot)

    # Custom colors
    print("\n--- Complex Cadence (Custom Colors) ---\n")
    complex_cadence = create_complex_cadence(score)
    dot = to_dot(
        complex_cadence,
        rankdir="LR",  # Left to right
        node_color="#6B8E23",  # Olive green
        edge_color="#8B4513",  # Saddle brown
    )
    print(dot)

    print("\n  Usage tip: Save to a .dot file and render with:")
    print("    dot -Tsvg cadence.dot -o cadence.svg")
    print("    dot -Tpng cadence.dot -o cadence.png")


def demo_save_diagrams():
    """Demo: Save diagrams to files."""
    print("\n" + "=" * 60)
    print("DEMO 4: Saving Diagrams to Files")
    print("=" * 60)

    score = OrderScore(order_id="ORD-001", customer_id="CUST-100")
    cadence = create_complex_cadence(score)

    print("\n  Saving diagrams to /tmp/ directory...\n")

    # Save Mermaid diagram
    try:
        save_diagram(cadence, "/tmp/checkout_cadence.mmd")
        print("  Saved: /tmp/checkout_cadence.mmd (Mermaid)")
    except Exception as e:
        print(f"  Error saving .mmd: {e}")

    # Save DOT diagram
    try:
        save_diagram(cadence, "/tmp/checkout_cadence.dot")
        print("  Saved: /tmp/checkout_cadence.dot (Graphviz DOT)")
    except Exception as e:
        print(f"  Error saving .dot: {e}")

    # Save SVG (requires graphviz installed)
    try:
        save_diagram(cadence, "/tmp/checkout_cadence.svg")
        print("  Saved: /tmp/checkout_cadence.svg (rendered SVG)")
    except RuntimeError as e:
        print(f"  Skipped .svg: {e}")
    except Exception as e:
        print(f"  Error saving .svg: {e}")

    # Save PNG (requires graphviz installed)
    try:
        save_diagram(cadence, "/tmp/checkout_cadence.png")
        print("  Saved: /tmp/checkout_cadence.png (rendered PNG)")
    except RuntimeError as e:
        print(f"  Skipped .png: {e}")
    except Exception as e:
        print(f"  Error saving .png: {e}")

    print("\n  Note: SVG and PNG output requires Graphviz to be installed.")
    print("  Install with: brew install graphviz (macOS)")
    print("                apt install graphviz (Linux)")


def demo_documentation_workflow():
    """Demo: Generate documentation with embedded diagrams."""
    print("\n" + "=" * 60)
    print("DEMO 5: Documentation Workflow")
    print("=" * 60)

    score = OrderScore(order_id="ORD-001", customer_id="CUST-100")
    cadence = create_complex_cadence(score)

    print("\n  Generating Markdown documentation with embedded diagram...\n")

    # Generate Mermaid diagram
    mermaid = to_mermaid(cadence)

    # Create markdown documentation
    doc = f"""# Checkout Cadence Documentation

## Overview

This document describes the checkout cadence for the e-commerce system.

## Cadence Diagram

```mermaid
{mermaid}
```

## Cadence Notes

1. **Validate Order** - Ensures order data is valid
2. **Enrich Data** (Parallel)
   - Fetch Customer - Retrieves customer profile
   - Fetch Inventory - Checks item availability
3. **Pricing** (Branch)
   - Premium customers get 15% discount
   - Standard customers pay full price
4. **Calculate Shipping** - Determines shipping cost
5. **Process Payment** - Charges the customer
6. **Notify** (Parallel)
   - Send Confirmation - Email to customer
   - Update Analytics - Track the order

## Notes

- Premium customers get free shipping
- All notes are retryable on transient failures
"""

    print(doc)

    # Save to file
    try:
        with open("/tmp/checkout_cadence.md", "w") as f:
            f.write(doc)
        print("\n  Saved documentation to: /tmp/checkout_cadence.md")
    except Exception as e:
        print(f"\n  Error saving documentation: {e}")


# --- Main ---


def main():
    print("Cadence Diagram Generation Demo")
    print("=" * 60)
    print("\nThis demo shows how to visualize your cadences as diagrams.")
    print("Supports Mermaid, DOT/Graphviz, and text-based output.")

    demo_text_visualization()
    demo_mermaid_generation()
    demo_dot_generation()
    demo_save_diagrams()
    demo_documentation_workflow()

    print("\n" + "=" * 60)
    print("All diagram generation demos completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
