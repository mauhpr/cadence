"""
E-commerce Checkout Example

This example demonstrates a complete checkout cadence with:
- Parallel data fetching
- Conditional branching (premium vs standard)
- Child cadence composition (payment processing)
- Error handling and resilience
"""

import asyncio
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

from cadence import Cadence, Score, note, retry, timeout, fallback
from cadence.exceptions import CadenceError
from cadence.reporters import console_reporter


# --- Score Definitions ---

@dataclass
class PaymentScore(Score):
    """Score for payment sub-cadence."""
    amount: float
    card_token: str

    authorized: bool = False
    transaction_id: Optional[str] = None


@dataclass
class CheckoutScore(Score):
    """Score for the main checkout cadence."""
    user_id: str
    cart_id: str

    # Populated during cadence
    user: Optional[Dict[str, Any]] = None
    cart: Optional[Dict[str, Any]] = None
    inventory_ok: bool = False
    order_id: Optional[str] = None
    payment_id: Optional[str] = None
    shipping_estimate: Optional[str] = None


# --- Mock Services ---

class UserService:
    async def get(self, user_id: str) -> Dict[str, Any]:
        await asyncio.sleep(0.03)
        return {"id": user_id, "name": "Jane Doe", "tier": "premium"}


class CartService:
    async def get(self, cart_id: str) -> Dict[str, Any]:
        await asyncio.sleep(0.04)
        return {
            "id": cart_id,
            "items": [{"sku": "ABC", "qty": 2, "price": 29.99}],
            "total": 59.98,
        }


class InventoryService:
    async def check(self, items: List[Dict]) -> bool:
        await asyncio.sleep(0.02)
        return True  # All items available


class OrderService:
    async def create(self, user: Dict, cart: Dict) -> str:
        await asyncio.sleep(0.05)
        return "ORD-12345"


class PaymentService:
    async def authorize(self, amount: float, token: str) -> Dict:
        await asyncio.sleep(0.08)
        return {"authorized": True, "transaction_id": "TXN-67890"}


class ShippingService:
    async def estimate(self, order_id: str, tier: str) -> str:
        await asyncio.sleep(0.03)
        if tier == "premium":
            return "Next day delivery"
        return "3-5 business days"


class NotificationService:
    async def send_confirmation(self, user: Dict, order_id: str) -> None:
        await asyncio.sleep(0.02)
        print(f"  [Email sent to {user['name']}]")


# Initialize services
user_svc = UserService()
cart_svc = CartService()
inventory_svc = InventoryService()
order_svc = OrderService()
payment_svc = PaymentService()
shipping_svc = ShippingService()
notification_svc = NotificationService()


# --- Payment Cadence Notes ---

@note
@retry(max_attempts=3, on=(ConnectionError,))
async def authorize_payment(score: PaymentScore) -> None:
    """Authorize the payment."""
    result = await payment_svc.authorize(score.amount, score.card_token)
    score.authorized = result["authorized"]
    score.transaction_id = result["transaction_id"]


# --- Checkout Cadence Notes ---

@note
@timeout(2.0)
async def fetch_user(score: CheckoutScore) -> None:
    """Fetch user details."""
    score.user = await user_svc.get(score.user_id)


@note
@timeout(2.0)
async def fetch_cart(score: CheckoutScore) -> None:
    """Fetch cart contents."""
    score.cart = await cart_svc.get(score.cart_id)


@note
async def check_inventory(score: CheckoutScore) -> None:
    """Verify all items are in stock."""
    score.inventory_ok = await inventory_svc.check(score.cart["items"])
    if not score.inventory_ok:
        raise CadenceError("Items out of stock", code="OUT_OF_STOCK")


@note
async def create_order(score: CheckoutScore) -> None:
    """Create the order record."""
    score.order_id = await order_svc.create(score.user, score.cart)


@note
async def premium_shipping(score: CheckoutScore) -> None:
    """Calculate premium shipping estimate."""
    score.shipping_estimate = await shipping_svc.estimate(score.order_id, "premium")
    print(f"  [Premium: {score.shipping_estimate}]")


@note
async def standard_shipping(score: CheckoutScore) -> None:
    """Calculate standard shipping estimate."""
    score.shipping_estimate = await shipping_svc.estimate(score.order_id, "standard")
    print(f"  [Standard: {score.shipping_estimate}]")


@note
async def send_confirmation(score: CheckoutScore) -> None:
    """Send order confirmation."""
    await notification_svc.send_confirmation(score.user, score.order_id)


def is_premium_user(score: CheckoutScore) -> bool:
    """Check if user is premium tier."""
    return score.user.get("tier") == "premium"


def merge_payment(parent: CheckoutScore, child: PaymentScore) -> None:
    """Merge payment result into checkout score."""
    parent.payment_id = child.transaction_id


# --- Cadence Definitions ---

def create_payment_cadence(amount: float, card_token: str) -> Cadence[PaymentScore]:
    """Create a payment processing sub-cadence."""
    return (
        Cadence("payment", PaymentScore(amount=amount, card_token=card_token))
        .then("authorize", authorize_payment)
    )


def create_checkout_cadence(user_id: str, cart_id: str) -> Cadence[CheckoutScore]:
    """Create the main checkout cadence."""
    score = CheckoutScore(user_id=user_id, cart_id=cart_id)

    # Payment cadence will be created dynamically after we know the total
    # For this example, we use a placeholder amount
    payment_cadence = create_payment_cadence(amount=59.98, card_token="tok_visa")

    return (
        Cadence("checkout", score)
        .with_reporter(console_reporter)
        # Fetch user and cart in parallel
        .sync("fetch_data", [fetch_user, fetch_cart])
        # Verify inventory
        .then("inventory", check_inventory)
        # Create the order
        .then("create_order", create_order)
        # Process payment via child cadence
        .child("payment", payment_cadence, merge_payment)
        # Branch based on user tier for shipping
        .split("shipping",
            condition=is_premium_user,
            if_true=[premium_shipping],
            if_false=[standard_shipping])
        # Send confirmation
        .then("confirm", send_confirmation)
        .on_error(handle_checkout_error, stop=True)
    )


async def handle_checkout_error(score: CheckoutScore, error: Exception) -> None:
    """Handle checkout errors."""
    print(f"\n[ERROR] Checkout failed: {error}")
    if score.order_id:
        print(f"  Rolling back order {score.order_id}...")


# --- Main ---

async def main():
    print("Starting checkout cadence...\n")

    cadence = create_checkout_cadence(user_id="user_456", cart_id="cart_789")
    result = await cadence.run()

    print(f"\nCheckout complete!")
    print(f"  Order ID: {result.order_id}")
    print(f"  Payment ID: {result.payment_id}")
    print(f"  Shipping: {result.shipping_estimate}")


if __name__ == "__main__":
    asyncio.run(main())
