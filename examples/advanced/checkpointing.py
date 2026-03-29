"""
Checkpointing Example

This example demonstrates using Cadence's checkpointing feature
for crash recovery. If a workflow fails mid-execution, re-running
with the same run_id resumes from the last completed step.
"""

import asyncio
from dataclasses import dataclass
from typing import Optional

from cadence import (
    Cadence,
    Score,
    note,
    NoteError,
    InMemoryCheckpointStore,
)


# --- Score Definition ---


@dataclass
class PaymentScore(Score):
    """Score for a payment processing cadence."""
    order_id: str
    validated: bool = False
    charged: bool = False
    disbursed: bool = False


# --- Failure Simulation ---

# This counter tracks how many times charge_payment has been called.
# On the first run it will "fail" to simulate a crash mid-workflow.
charge_attempt_count = 0


# --- Notes ---


@note
async def validate_payment(score: PaymentScore) -> None:
    """Step 1: Validate the payment details."""
    await asyncio.sleep(0.01)
    score.validated = True
    print(f"    [validate_payment] order {score.order_id} validated")


@note
async def charge_payment(score: PaymentScore) -> None:
    """Step 2: Charge the customer.

    On the first call this raises an error to simulate a crash.
    On subsequent calls it succeeds, demonstrating resume behavior.
    """
    global charge_attempt_count
    charge_attempt_count += 1

    await asyncio.sleep(0.01)

    if charge_attempt_count == 1:
        # Simulate a transient failure (e.g., gateway timeout)
        raise ConnectionError("Payment gateway unreachable!")

    score.charged = True
    print(f"    [charge_payment] order {score.order_id} charged")


@note
async def disburse_funds(score: PaymentScore) -> None:
    """Step 3: Disburse funds to the merchant."""
    await asyncio.sleep(0.01)
    score.disbursed = True
    print(f"    [disburse_funds] order {score.order_id} disbursed")


# --- Demo ---


async def demo_checkpoint_recovery():
    """Show how checkpointing enables crash recovery."""
    print("\n" + "=" * 60)
    print("DEMO: Checkpoint Recovery")
    print("=" * 60)

    # 1. Create a checkpoint store.
    #    InMemoryCheckpointStore is great for development and testing.
    #    For production, implement the CheckpointStore protocol with
    #    Redis, PostgreSQL, or any durable backend. The protocol
    #    requires four async methods: save_checkpoint,
    #    get_completed_measures, get_last_score_state, and
    #    clear_checkpoints.
    store = InMemoryCheckpointStore()

    # Use a fixed run_id so the second run can find the first run's
    # checkpoints and resume from where it left off.
    run_id = "payment-order-500"

    # --- First run: fails at step 2 ---
    print("\n  Run 1: First attempt (will fail at charge_payment)")
    print("  " + "-" * 50)

    score1 = PaymentScore(order_id="ORD-500")
    cadence1 = (
        Cadence("process_payment", score1)
        .with_checkpoint(store, run_id=run_id)
        .then("validate", validate_payment)
        .then("charge", charge_payment)
        .then("disburse", disburse_funds)
    )

    try:
        await cadence1.run()
    except NoteError as e:
        print(f"\n    Run 1 FAILED: {e}")
        print(f"    Score state: validated={score1.validated}, "
              f"charged={score1.charged}, disbursed={score1.disbursed}")

    # --- Second run: resumes from last checkpoint ---
    print("\n  Run 2: Re-run with same run_id (resumes after validate)")
    print("  " + "-" * 50)

    # Create a fresh score — checkpointing will restore the state
    # from the last successful checkpoint automatically.
    score2 = PaymentScore(order_id="ORD-500")
    cadence2 = (
        Cadence("process_payment", score2)
        .with_checkpoint(store, run_id=run_id)
        .then("validate", validate_payment)
        .then("charge", charge_payment)
        .then("disburse", disburse_funds)
    )

    result = await cadence2.run()

    print(f"\n    Run 2 SUCCEEDED!")
    print(f"    Score state: validated={result.validated}, "
          f"charged={result.charged}, disbursed={result.disbursed}")

    # Notice that validate_payment did NOT print during run 2 —
    # it was skipped because the checkpoint store recorded it as
    # completed during run 1.


# --- Main ---


async def main():
    global charge_attempt_count

    print("Cadence Checkpointing Demo")
    print("=" * 60)

    # Reset the failure counter so the demo is reproducible
    charge_attempt_count = 0

    await demo_checkpoint_recovery()

    print("\n" + "=" * 60)
    print("Key takeaways:")
    print("  - with_checkpoint(store, run_id) enables crash recovery")
    print("  - Completed steps are skipped on re-run (same run_id)")
    print("  - Score state is restored from the last checkpoint")
    print("  - Use InMemoryCheckpointStore for dev/testing")
    print("  - Implement CheckpointStore with Redis or a database")
    print("    for production durability")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
