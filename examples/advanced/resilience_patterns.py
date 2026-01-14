"""
Resilience Patterns Example

This example demonstrates all of Cadence's resilience decorators:
- @retry: Automatic retries with backoff
- @timeout: Time limits on execution
- @fallback: Default values on failure
- @circuit_breaker: Prevent cascading failures
"""

import asyncio
import random
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

from cadence import (
    Cadence,
    Score,
    note,
    retry,
    timeout,
    fallback,
    circuit_breaker,
    CircuitBreaker,
    CircuitState,
    CircuitOpenError,
    RetryExhaustedError,
    TimeoutError,
)


# --- Score Definition ---


@dataclass
class DataFetchScore(Score):
    """Score for data fetching cadence."""
    request_id: str

    # Results from various services
    primary_data: Optional[Dict[str, Any]] = None
    backup_data: Optional[Dict[str, Any]] = None
    enrichment: Optional[Dict[str, Any]] = None
    analytics: Optional[Dict[str, Any]] = None
    cache_result: Optional[Dict[str, Any]] = None


# --- Simulated External Services ---


class UnreliableService:
    """A service that fails randomly."""

    def __init__(self, name: str, failure_rate: float = 0.5):
        self.name = name
        self.failure_rate = failure_rate
        self.call_count = 0

    async def call(self) -> Dict[str, Any]:
        self.call_count += 1
        await asyncio.sleep(0.01)

        if random.random() < self.failure_rate:
            raise ConnectionError(f"{self.name} is temporarily unavailable")

        return {"source": self.name, "call": self.call_count, "data": "success"}


class SlowService:
    """A service that sometimes takes too long."""

    def __init__(self, name: str, slow_probability: float = 0.3):
        self.name = name
        self.slow_probability = slow_probability

    async def call(self, timeout_seconds: float = 1.0) -> Dict[str, Any]:
        if random.random() < self.slow_probability:
            # Simulate a slow response
            await asyncio.sleep(timeout_seconds + 0.5)
        else:
            await asyncio.sleep(0.02)

        return {"source": self.name, "data": "completed"}


class OverloadedService:
    """A service that fails under load and needs circuit breaking."""

    def __init__(self, name: str):
        self.name = name
        self.consecutive_failures = 0
        self._recovering = False

    async def call(self) -> Dict[str, Any]:
        await asyncio.sleep(0.01)

        # Simulate service degradation under load
        if self.consecutive_failures < 3:
            self.consecutive_failures += 1
            raise ConnectionError(f"{self.name} overloaded!")

        # Eventually recover
        if self.consecutive_failures >= 3:
            self._recovering = True
            self.consecutive_failures = 0

        return {"source": self.name, "status": "recovered"}


# Initialize services
unreliable_svc = UnreliableService("UnreliableAPI", failure_rate=0.6)
slow_svc = SlowService("SlowAPI", slow_probability=0.4)
overloaded_svc = OverloadedService("OverloadedAPI")


# --- Retry Pattern ---


@note
@retry(max_attempts=5, backoff="exponential", delay=0.1, max_delay=2.0)
async def fetch_with_retry(score: DataFetchScore) -> None:
    """
    Fetch data with automatic retries.

    Uses exponential backoff: 0.1s, 0.2s, 0.4s, 0.8s, 1.6s (capped at 2s)
    """
    print(f"  Attempting to fetch (call #{unreliable_svc.call_count + 1})...")
    score.primary_data = await unreliable_svc.call()


@note
@retry(max_attempts=3, backoff="linear", delay=0.2)
async def fetch_with_linear_retry(score: DataFetchScore) -> None:
    """
    Fetch data with linear backoff retries.

    Delays: 0.2s, 0.4s, 0.6s
    """
    print(f"  Linear retry attempt...")
    score.backup_data = await unreliable_svc.call()


# --- Timeout Pattern ---


@note
@timeout(0.5)  # 500ms timeout
async def fetch_with_timeout(score: DataFetchScore) -> None:
    """
    Fetch data with a strict timeout.

    If the service doesn't respond within 500ms, abort.
    """
    print("  Fetching with timeout...")
    score.enrichment = await slow_svc.call(timeout_seconds=0.5)


@note
@retry(max_attempts=3, delay=0.1)
@timeout(0.5)
async def fetch_with_retry_and_timeout(score: DataFetchScore) -> None:
    """
    Combine retry with timeout.

    Each attempt has a 500ms timeout, with 3 total attempts.
    """
    print("  Fetching with retry + timeout...")
    score.analytics = await slow_svc.call(timeout_seconds=0.5)


# --- Fallback Pattern ---


@note
@fallback({"source": "fallback", "data": "default_value"})
async def fetch_with_fallback(score: DataFetchScore) -> None:
    """
    Fetch data with a fallback value on failure.

    If the service fails, use a default value instead of failing.
    """
    print("  Fetching with fallback...")
    raise ConnectionError("Service unavailable")
    score.cache_result = {"never": "reached"}  # This line won't execute


@note
@retry(max_attempts=2, delay=0.05)
@fallback({"source": "cache", "stale": True})
async def fetch_with_retry_then_fallback(score: DataFetchScore) -> None:
    """
    Try with retries first, then fall back to cache.

    Retry twice, and if still failing, use stale cache data.
    """
    print("  Fetching with retry then fallback...")
    score.cache_result = await unreliable_svc.call()


# --- Circuit Breaker Pattern ---


# Create a shared circuit breaker instance
api_circuit = CircuitBreaker(
    name="api_circuit",       # Required name for the circuit
    failure_threshold=3,      # Open after 3 failures
    recovery_timeout=5.0,     # Try to recover after 5 seconds
    half_open_max_calls=1,    # Allow 1 test call in half-open state
)


@note
@circuit_breaker(api_circuit)
async def fetch_with_circuit_breaker(score: DataFetchScore) -> None:
    """
    Fetch data with circuit breaker protection.

    After 3 failures, the circuit opens and calls fail fast.
    After 5 seconds, it enters half-open state to test recovery.
    """
    print(f"  Circuit state: {api_circuit.state.name}")
    score.enrichment = await overloaded_svc.call()


# --- Demo Functions ---


async def demo_retry():
    """Demonstrate the retry pattern."""
    print("\n" + "=" * 60)
    print("DEMO: @retry - Automatic Retries with Backoff")
    print("=" * 60)

    # Reset service
    unreliable_svc.call_count = 0
    unreliable_svc.failure_rate = 0.6

    score = DataFetchScore(request_id="retry-demo")

    cadence = (
        Cadence("retry_demo", score)
        .then("fetch", fetch_with_retry)
    )

    try:
        result = await cadence.run()
        print(f"\n✓ Success after {unreliable_svc.call_count} attempts")
        print(f"  Data: {result.primary_data}")
    except RetryExhaustedError as e:
        print(f"\n✗ Failed after {unreliable_svc.call_count} attempts: {e}")


async def demo_timeout():
    """Demonstrate the timeout pattern."""
    print("\n" + "=" * 60)
    print("DEMO: @timeout - Time-Limited Execution")
    print("=" * 60)

    score = DataFetchScore(request_id="timeout-demo")

    cadence = (
        Cadence("timeout_demo", score)
        .then("fetch", fetch_with_timeout)
    )

    try:
        result = await cadence.run()
        print(f"\n✓ Completed within timeout")
        print(f"  Data: {result.enrichment}")
    except TimeoutError as e:
        print(f"\n✗ Timed out: {e}")


async def demo_fallback():
    """Demonstrate the fallback pattern."""
    print("\n" + "=" * 60)
    print("DEMO: @fallback - Graceful Degradation")
    print("=" * 60)

    score = DataFetchScore(request_id="fallback-demo")

    @note
    @fallback({"source": "default", "message": "Service unavailable"})
    async def always_fails(score: DataFetchScore) -> None:
        raise ConnectionError("Service down!")

    cadence = (
        Cadence("fallback_demo", score)
        .then("fetch", always_fails)
    )

    result = await cadence.run()
    print(f"\n✓ Fallback provided default value")
    print(f"  This beat 'failed' but the cadence continued with fallback data")


async def demo_circuit_breaker():
    """Demonstrate the circuit breaker pattern."""
    print("\n" + "=" * 60)
    print("DEMO: @circuit_breaker - Prevent Cascading Failures")
    print("=" * 60)

    # Reset circuit and service
    api_circuit._failure_count = 0
    api_circuit._state = CircuitState.CLOSED
    overloaded_svc.consecutive_failures = 0

    print("\nMaking 6 rapid calls to trigger circuit breaker...")
    print("(Circuit opens after 3 failures, then fails fast)\n")

    for i in range(6):
        score = DataFetchScore(request_id=f"circuit-demo-{i}")

        cadence = (
            Cadence(f"circuit_demo_{i}", score)
            .then("fetch", fetch_with_circuit_breaker)
        )

        try:
            await cadence.run()
            print(f"  Call {i+1}: ✓ Success")
        except CircuitOpenError:
            print(f"  Call {i+1}: ⚡ Circuit OPEN - failing fast (no actual call made)")
        except Exception as e:
            print(f"  Call {i+1}: ✗ Failed - {e}")

    print(f"\nFinal circuit state: {api_circuit.state.name}")
    print(f"Failure count: {api_circuit._failure_count}/{api_circuit.failure_threshold}")


async def demo_combined():
    """Demonstrate combining multiple resilience patterns."""
    print("\n" + "=" * 60)
    print("DEMO: Combined Patterns")
    print("=" * 60)

    # Reset
    unreliable_svc.call_count = 0
    unreliable_svc.failure_rate = 0.8  # High failure rate

    score = DataFetchScore(request_id="combined-demo")

    @note
    @retry(max_attempts=3, delay=0.05)
    @timeout(0.3)
    @fallback({"source": "emergency_cache", "stale": True})
    async def resilient_fetch(score: DataFetchScore) -> None:
        """A note with multiple resilience layers."""
        score.primary_data = await unreliable_svc.call()

    cadence = (
        Cadence("combined_demo", score)
        .then("fetch", resilient_fetch)
    )

    result = await cadence.run()
    print(f"\n✓ Cadence completed (possibly with fallback)")
    print(f"  Data: {result.primary_data}")
    print(f"  Attempts made: {unreliable_svc.call_count}")


async def demo_circuit_breaker_states():
    """Demonstrate circuit breaker state transitions."""
    print("\n" + "=" * 60)
    print("DEMO: Circuit Breaker State Machine")
    print("=" * 60)

    # Create a fresh circuit breaker for this demo
    demo_circuit = CircuitBreaker(
        failure_threshold=2,
        recovery_timeout=1.0,  # Short timeout for demo
        half_open_max_calls=1,
    )

    # Service that always fails initially
    failures_before_recovery = 4

    @note
    @circuit_breaker(demo_circuit)
    async def controlled_service(score: DataFetchScore) -> None:
        nonlocal failures_before_recovery
        if failures_before_recovery > 0:
            failures_before_recovery -= 1
            raise ConnectionError("Service error")
        score.primary_data = {"status": "recovered"}

    print("\nState transitions: CLOSED → OPEN → HALF_OPEN → (CLOSED or OPEN)")
    print()

    # Phase 1: Trigger circuit open
    print("Phase 1: Triggering failures to open circuit...")
    for i in range(3):
        score = DataFetchScore(request_id=f"state-{i}")
        cadence = Cadence(f"state_demo_{i}", score).then("call", controlled_service)
        try:
            await cadence.run()
        except (ConnectionError, CircuitOpenError) as e:
            print(f"  Call {i+1}: {demo_circuit.state.name} - {type(e).__name__}")

    # Phase 2: Wait for recovery timeout
    print(f"\nPhase 2: Waiting for recovery timeout ({demo_circuit.recovery_timeout}s)...")
    await asyncio.sleep(demo_circuit.recovery_timeout + 0.1)

    # Phase 3: Half-open test
    print("\nPhase 3: Testing in HALF_OPEN state...")
    failures_before_recovery = 0  # Service has recovered

    score = DataFetchScore(request_id="recovery")
    cadence = Cadence("recovery_demo", score).then("call", controlled_service)
    try:
        result = await cadence.run()
        print(f"  Recovery call: {demo_circuit.state.name} - Success!")
        print(f"  Data: {result.primary_data}")
    except Exception as e:
        print(f"  Recovery call: {demo_circuit.state.name} - {e}")


# --- Main ---


async def main():
    print("Cadence Resilience Patterns Demo")
    print("=" * 60)
    print("Demonstrating: @retry, @timeout, @fallback, @circuit_breaker")

    await demo_retry()
    await demo_timeout()
    await demo_fallback()
    await demo_circuit_breaker()
    await demo_combined()
    await demo_circuit_breaker_states()

    print("\n" + "=" * 60)
    print("✓ All resilience pattern demos completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
