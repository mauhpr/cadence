"""
Branching and Conditional Logic Example

This example demonstrates Cadence's branching capabilities:
- Conditional execution with .split()
- Multiple branch conditions
- Nested cadences with .child()
- Complex decision trees
"""

import asyncio
from dataclasses import dataclass, field
from enum import Enum

from cadence import Cadence, Score, note, retry, timeout


# --- Enums and Types ---


class OrderType(Enum):
    STANDARD = "standard"
    EXPRESS = "express"
    PREMIUM = "premium"


class PaymentMethod(Enum):
    CREDIT_CARD = "credit_card"
    PAYPAL = "paypal"
    BANK_TRANSFER = "bank_transfer"
    CRYPTO = "crypto"


class CustomerTier(Enum):
    BASIC = "basic"
    SILVER = "silver"
    GOLD = "gold"
    PLATINUM = "platinum"


# --- Score Definitions ---


@dataclass
class OrderScore(Score):
    """Score for order processing with branching logic."""
    order_id: str
    customer_id: str
    order_type: OrderType
    payment_method: PaymentMethod
    customer_tier: CustomerTier
    amount: float
    items: list[dict] = field(default_factory=list)

    # Computed/populated by beats
    requires_review: bool = False
    discount_applied: float = 0.0
    final_amount: float = 0.0
    shipping_method: str = ""
    estimated_days: int = 0
    payment_processed: bool = False
    fraud_score: float = 0.0
    notifications_sent: list[str] = field(default_factory=list)


# --- Condition Functions ---


def is_high_value_order(score: OrderScore) -> bool:
    """Check if order exceeds high-value threshold."""
    return score.amount > 1000


def requires_fraud_check(score: OrderScore) -> bool:
    """Check if order requires fraud verification."""
    return score.amount > 500 or score.customer_tier == CustomerTier.BASIC


def is_express_or_premium(score: OrderScore) -> bool:
    """Check if order is express or premium type."""
    return score.order_type in (OrderType.EXPRESS, OrderType.PREMIUM)


def is_crypto_payment(score: OrderScore) -> bool:
    """Check if payment method is cryptocurrency."""
    return score.payment_method == PaymentMethod.CRYPTO


def is_platinum_customer(score: OrderScore) -> bool:
    """Check if customer is platinum tier."""
    return score.customer_tier == CustomerTier.PLATINUM


def order_needs_review(score: OrderScore) -> bool:
    """Check if order needs manual review."""
    return score.requires_review


# --- Note Definitions ---


@note
async def validate_order(score: OrderScore) -> None:
    """Validate the order details."""
    await asyncio.sleep(0.01)
    print(f"  Validating order {score.order_id}...")

    # Set requires_review flag based on business rules
    if score.amount > 5000:
        score.requires_review = True
    if score.fraud_score > 0.7:
        score.requires_review = True


@note
async def calculate_standard_discount(score: OrderScore) -> None:
    """Calculate discount for standard customers."""
    await asyncio.sleep(0.01)
    # Basic tier customers get no discount
    # Silver gets 5%, Gold gets 10%
    discounts = {
        CustomerTier.BASIC: 0.0,
        CustomerTier.SILVER: 0.05,
        CustomerTier.GOLD: 0.10,
        CustomerTier.PLATINUM: 0.15,  # Should use premium path
    }
    score.discount_applied = score.amount * discounts.get(score.customer_tier, 0)
    score.final_amount = score.amount - score.discount_applied
    print(f"  Standard discount: ${score.discount_applied:.2f}")


@note
async def calculate_premium_discount(score: OrderScore) -> None:
    """Calculate enhanced discount for platinum customers."""
    await asyncio.sleep(0.01)
    # Platinum customers get 15% + additional bonuses
    base_discount = score.amount * 0.15

    # Extra discount for high-value orders
    if score.amount > 1000:
        base_discount += score.amount * 0.05

    score.discount_applied = base_discount
    score.final_amount = score.amount - score.discount_applied
    print(f"  Premium discount: ${score.discount_applied:.2f} (Platinum bonus!)")


@note
async def set_standard_shipping(score: OrderScore) -> None:
    """Set standard shipping (5-7 days)."""
    await asyncio.sleep(0.01)
    score.shipping_method = "Standard Ground"
    score.estimated_days = 7
    print(f"  Shipping: {score.shipping_method} ({score.estimated_days} days)")


@note
async def set_express_shipping(score: OrderScore) -> None:
    """Set express shipping (2-3 days)."""
    await asyncio.sleep(0.01)
    score.shipping_method = "Express Air"
    score.estimated_days = 2
    print(f"  Shipping: {score.shipping_method} ({score.estimated_days} days)")


@note
async def set_premium_shipping(score: OrderScore) -> None:
    """Set premium shipping (next day)."""
    await asyncio.sleep(0.01)
    score.shipping_method = "Premium Next-Day"
    score.estimated_days = 1
    print(f"  Shipping: {score.shipping_method} ({score.estimated_days} days)")


@note
@retry(max_attempts=3)
@timeout(2.0)
async def process_credit_card(score: OrderScore) -> None:
    """Process credit card payment."""
    await asyncio.sleep(0.05)
    print(f"  Processing credit card payment: ${score.final_amount:.2f}")
    score.payment_processed = True


@note
@retry(max_attempts=3)
@timeout(5.0)
async def process_paypal(score: OrderScore) -> None:
    """Process PayPal payment."""
    await asyncio.sleep(0.08)
    print(f"  Processing PayPal payment: ${score.final_amount:.2f}")
    score.payment_processed = True


@note
@timeout(10.0)
async def process_bank_transfer(score: OrderScore) -> None:
    """Process bank transfer (takes longer)."""
    await asyncio.sleep(0.1)
    print(f"  Processing bank transfer: ${score.final_amount:.2f}")
    score.payment_processed = True


@note
@retry(max_attempts=5)
@timeout(30.0)
async def process_crypto(score: OrderScore) -> None:
    """Process cryptocurrency payment (may take time for confirmations)."""
    await asyncio.sleep(0.15)
    print(f"  Processing crypto payment: ${score.final_amount:.2f}")
    print("    Waiting for blockchain confirmations...")
    score.payment_processed = True


@note
async def perform_fraud_check(score: OrderScore) -> None:
    """Perform fraud analysis on the order."""
    await asyncio.sleep(0.03)
    # Simulate fraud score calculation
    import random
    score.fraud_score = random.uniform(0.0, 0.5)  # Keep it low for demo
    print(f"  Fraud check: score = {score.fraud_score:.2f}")


@note
async def skip_fraud_check(score: OrderScore) -> None:
    """Skip fraud check for trusted customers."""
    score.fraud_score = 0.0
    print("  Fraud check: skipped (trusted customer)")


@note
async def flag_for_manual_review(score: OrderScore) -> None:
    """Flag order for manual review."""
    await asyncio.sleep(0.01)
    print("  ⚠ Order flagged for manual review")
    score.notifications_sent.append("review_team_notified")


@note
async def auto_approve(score: OrderScore) -> None:
    """Auto-approve the order."""
    await asyncio.sleep(0.01)
    print("  ✓ Order auto-approved")


@note
async def send_confirmation(score: OrderScore) -> None:
    """Send order confirmation."""
    await asyncio.sleep(0.01)
    print(f"  Confirmation sent for order {score.order_id}")
    score.notifications_sent.append("confirmation_email")


@note
async def send_premium_confirmation(score: OrderScore) -> None:
    """Send premium confirmation with concierge contact."""
    await asyncio.sleep(0.01)
    print(f"  Premium confirmation sent for order {score.order_id}")
    print("    Includes: Concierge contact + tracking link")
    score.notifications_sent.append("premium_confirmation_email")
    score.notifications_sent.append("sms_notification")


# --- Cadence Builders ---


def create_order_processing_cadence(score: OrderScore) -> Cadence[OrderScore]:
    """
    Create a complete order processing cadence with multiple branches.

    Cadence structure:
    1. Validate order
    2. Branch: Fraud check or skip (based on customer tier)
    3. Branch: Discount calculation (standard vs platinum)
    4. Branch: Shipping selection (based on order type)
    5. Branch: Payment processing (based on payment method)
    6. Branch: Review or auto-approve
    7. Branch: Confirmation (standard vs premium)
    """
    # Determine shipping beat based on order type
    def get_shipping_beat(c: OrderScore):
        if c.order_type == OrderType.PREMIUM:
            return set_premium_shipping
        elif c.order_type == OrderType.EXPRESS:
            return set_express_shipping
        else:
            return set_standard_shipping

    # Get the appropriate payment beat
    payment_beats = {
        PaymentMethod.CREDIT_CARD: process_credit_card,
        PaymentMethod.PAYPAL: process_paypal,
        PaymentMethod.BANK_TRANSFER: process_bank_transfer,
        PaymentMethod.CRYPTO: process_crypto,
    }
    payment_beat = payment_beats.get(score.payment_method, process_credit_card)

    return (
        Cadence("order_processing", score)
        # Beat 1: Validate
        .then("validate", validate_order)

        # Beat 2: Fraud check branch
        .split(
            "fraud_check",
            condition=requires_fraud_check,
            if_true=[perform_fraud_check],
            if_false=[skip_fraud_check],
        )

        # Beat 3: Discount calculation branch
        .split(
            "discount",
            condition=is_platinum_customer,
            if_true=[calculate_premium_discount],
            if_false=[calculate_standard_discount],
        )

        # Beat 4: Shipping selection (using dynamic beat selection)
        .then("shipping", get_shipping_beat(score))

        # Beat 5: Payment processing
        .then("payment", payment_beat)

        # Beat 6: Review or auto-approve
        .split(
            "review_decision",
            condition=order_needs_review,
            if_true=[flag_for_manual_review],
            if_false=[auto_approve],
        )

        # Beat 7: Confirmation
        .split(
            "confirmation",
            condition=is_platinum_customer,
            if_true=[send_premium_confirmation],
            if_false=[send_confirmation],
        )
    )




# --- Demo Functions ---


async def demo_standard_order():
    """Demo: Standard order for basic customer."""
    print("\n" + "=" * 60)
    print("DEMO 1: Standard Order (Basic Customer)")
    print("=" * 60 + "\n")

    score = OrderScore(
        order_id="ORD-001",
        customer_id="CUST-100",
        order_type=OrderType.STANDARD,
        payment_method=PaymentMethod.CREDIT_CARD,
        customer_tier=CustomerTier.BASIC,
        amount=150.00,
        items=[{"name": "Widget", "qty": 2}],
    )

    cadence = create_order_processing_cadence(score)
    result = await cadence.run()

    print(f"\n  Summary:")
    print(f"    Original: ${result.amount:.2f}")
    print(f"    Discount: ${result.discount_applied:.2f}")
    print(f"    Final:    ${result.final_amount:.2f}")
    print(f"    Shipping: {result.shipping_method}")


async def demo_express_gold_order():
    """Demo: Express order for gold customer."""
    print("\n" + "=" * 60)
    print("DEMO 2: Express Order (Gold Customer)")
    print("=" * 60 + "\n")

    score = OrderScore(
        order_id="ORD-002",
        customer_id="CUST-200",
        order_type=OrderType.EXPRESS,
        payment_method=PaymentMethod.PAYPAL,
        customer_tier=CustomerTier.GOLD,
        amount=500.00,
        items=[{"name": "Premium Widget", "qty": 5}],
    )

    cadence = create_order_processing_cadence(score)
    result = await cadence.run()

    print(f"\n  Summary:")
    print(f"    Original: ${result.amount:.2f}")
    print(f"    Discount: ${result.discount_applied:.2f} (10% Gold)")
    print(f"    Final:    ${result.final_amount:.2f}")
    print(f"    Shipping: {result.shipping_method}")


async def demo_premium_platinum_order():
    """Demo: Premium order for platinum customer with crypto."""
    print("\n" + "=" * 60)
    print("DEMO 3: Premium Order (Platinum Customer, Crypto)")
    print("=" * 60 + "\n")

    score = OrderScore(
        order_id="ORD-003",
        customer_id="CUST-300",
        order_type=OrderType.PREMIUM,
        payment_method=PaymentMethod.CRYPTO,
        customer_tier=CustomerTier.PLATINUM,
        amount=2500.00,
        items=[{"name": "Luxury Widget Pro", "qty": 10}],
    )

    cadence = create_order_processing_cadence(score)
    result = await cadence.run()

    print(f"\n  Summary:")
    print(f"    Original: ${result.amount:.2f}")
    print(f"    Discount: ${result.discount_applied:.2f} (15% + 5% high-value)")
    print(f"    Final:    ${result.final_amount:.2f}")
    print(f"    Shipping: {result.shipping_method}")
    print(f"    Notifications: {result.notifications_sent}")


async def demo_high_value_review():
    """Demo: High-value order requiring manual review."""
    print("\n" + "=" * 60)
    print("DEMO 4: High-Value Order (Requires Review)")
    print("=" * 60 + "\n")

    score = OrderScore(
        order_id="ORD-004",
        customer_id="CUST-400",
        order_type=OrderType.STANDARD,
        payment_method=PaymentMethod.BANK_TRANSFER,
        customer_tier=CustomerTier.SILVER,
        amount=7500.00,  # Over $5000 threshold
        items=[{"name": "Enterprise Widget Suite", "qty": 1}],
    )

    cadence = create_order_processing_cadence(score)
    result = await cadence.run()

    print(f"\n  Summary:")
    print(f"    Amount: ${result.final_amount:.2f}")
    print(f"    Requires Review: {result.requires_review}")
    print(f"    Notifications: {result.notifications_sent}")


# --- Main ---


async def main():
    print("Cadence Branching & Conditional Logic Demo")
    print("=" * 60)
    print("This demo shows different order paths based on:")
    print("  - Customer tier (Basic/Silver/Gold/Platinum)")
    print("  - Order type (Standard/Express/Premium)")
    print("  - Payment method (Credit/PayPal/Bank/Crypto)")
    print("  - Order value (high-value = requires review)")

    await demo_standard_order()
    await demo_express_gold_order()
    await demo_premium_platinum_order()
    await demo_high_value_review()

    print("\n" + "=" * 60)
    print("✓ All branching demos completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
