"""
Event Emission Example

This example demonstrates using Cadence's EventEmitter for
structured domain events during cadence execution.
"""

import asyncio
from dataclasses import dataclass
from typing import Optional

from cadence import (
    Cadence,
    Score,
    note,
    EventEmitter,
    CadenceEvent,
    NOTE_COMPLETED,
    CADENCE_COMPLETED,
)


# --- Score Definition ---


@dataclass
class OrderScore(Score):
    """Score for a simple order processing cadence."""
    order_id: str
    status: str = "pending"
    total: float = 0.0


# --- Notes ---


@note
async def validate_order(score: OrderScore) -> None:
    """Validate the order exists and is ready to process."""
    await asyncio.sleep(0.01)
    score.status = "validated"


@note
async def calculate_total(score: OrderScore) -> None:
    """Calculate the order total."""
    await asyncio.sleep(0.01)
    score.total = 42.50


@note
async def finalize_order(score: OrderScore) -> None:
    """Mark the order as finalized."""
    await asyncio.sleep(0.01)
    score.status = "finalized"


# --- Demo Functions ---


async def demo_basic_listeners():
    """Register listeners for specific event types."""
    print("\n" + "=" * 60)
    print("DEMO: Basic Event Listeners")
    print("=" * 60 + "\n")

    # 1. Create an EventEmitter instance.
    #    EventEmitter is a CadenceHooks subclass, so it plugs in
    #    via .with_hooks() and fires events automatically.
    emitter = EventEmitter()

    # 2. Register a listener for NOTE_COMPLETED ("note.completed").
    #    The listener receives a CadenceEvent dataclass with fields
    #    like event_type, cadence_name, note_name, and duration.
    def on_note_done(event: CadenceEvent) -> None:
        print(f"  [NOTE_COMPLETED] {event.note_name} "
              f"finished in {event.duration:.4f}s")

    emitter.on(NOTE_COMPLETED, on_note_done)

    # 3. Register a listener for CADENCE_COMPLETED ("cadence.completed").
    def on_cadence_done(event: CadenceEvent) -> None:
        print(f"  [CADENCE_COMPLETED] '{event.cadence_name}' "
              f"total duration {event.duration:.4f}s")

    emitter.on(CADENCE_COMPLETED, on_cadence_done)

    # 4. Build and run the cadence with the emitter attached.
    score = OrderScore(order_id="ORD-100")
    cadence = (
        Cadence("process_order", score)
        .with_hooks(emitter)
        .then("validate", validate_order)
        .then("calculate", calculate_total)
        .then("finalize", finalize_order)
    )

    result = await cadence.run()
    print(f"\n  Final status: {result.status}, total: ${result.total:.2f}")


async def demo_wildcard_listener():
    """Use a wildcard listener to observe every event."""
    print("\n" + "=" * 60)
    print("DEMO: Wildcard Listener (\"*\")")
    print("=" * 60 + "\n")

    emitter = EventEmitter()

    # A wildcard listener receives ALL events — note.started,
    # note.completed, cadence.started, cadence.completed, etc.
    # Useful for logging, auditing, or shipping to an event bus.
    def log_all_events(event: CadenceEvent) -> None:
        note_info = f" note={event.note_name}" if event.note_name else ""
        print(f"  [*] {event.event_type}{note_info}")

    emitter.on("*", log_all_events)

    score = OrderScore(order_id="ORD-200")
    cadence = (
        Cadence("process_order", score)
        .with_hooks(emitter)
        .then("validate", validate_order)
        .then("calculate", calculate_total)
        .then("finalize", finalize_order)
    )

    await cadence.run()


async def demo_async_listener():
    """Register an async listener that awaits I/O."""
    print("\n" + "=" * 60)
    print("DEMO: Async Listener")
    print("=" * 60 + "\n")

    emitter = EventEmitter()

    # Listeners can be async functions. The EventEmitter detects
    # coroutines and awaits them automatically. This is useful for
    # publishing events to a message queue or writing to a database.
    async def async_on_note_done(event: CadenceEvent) -> None:
        # Simulate async I/O (e.g., writing to an event store)
        await asyncio.sleep(0.005)
        print(f"  [async] Recorded completion of '{event.note_name}'")

    emitter.on(NOTE_COMPLETED, async_on_note_done)

    score = OrderScore(order_id="ORD-300")
    cadence = (
        Cadence("process_order", score)
        .with_hooks(emitter)
        .then("validate", validate_order)
        .then("calculate", calculate_total)
        .then("finalize", finalize_order)
    )

    await cadence.run()
    print("\n  All async listeners completed.")


async def demo_remove_listener():
    """Remove a listener with .off() mid-flow."""
    print("\n" + "=" * 60)
    print("DEMO: Removing a Listener with .off()")
    print("=" * 60 + "\n")

    emitter = EventEmitter()
    events_received: list[str] = []

    def track_notes(event: CadenceEvent) -> None:
        events_received.append(event.note_name or "unknown")
        print(f"  [listener] {event.note_name} completed")

    # Register the listener
    emitter.on(NOTE_COMPLETED, track_notes)

    # Run once — listener is active
    print("  Run 1 (listener active):")
    score1 = OrderScore(order_id="ORD-400")
    cadence1 = (
        Cadence("process_order", score1)
        .with_hooks(emitter)
        .then("validate", validate_order)
        .then("calculate", calculate_total)
        .then("finalize", finalize_order)
    )
    await cadence1.run()

    # Remove the listener with .off()
    emitter.off(NOTE_COMPLETED, track_notes)

    # Run again — listener is gone, no output expected
    print("\n  Run 2 (listener removed with .off()):")
    score2 = OrderScore(order_id="ORD-401")
    cadence2 = (
        Cadence("process_order", score2)
        .with_hooks(emitter)
        .then("validate", validate_order)
        .then("calculate", calculate_total)
        .then("finalize", finalize_order)
    )
    await cadence2.run()
    print("  (no output — listener was removed)")

    print(f"\n  Events received total: {len(events_received)} "
          f"(all from run 1)")


# --- Main ---


async def main():
    print("Cadence Event Emission Demo")
    print("=" * 60)

    await demo_basic_listeners()
    await demo_wildcard_listener()
    await demo_async_listener()
    await demo_remove_listener()

    print("\n" + "=" * 60)
    print("All event emission demos completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
