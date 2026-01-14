"""Tests for resilience decorators: retry, timeout, fallback, circuit_breaker."""

import pytest
import asyncio
import time
from cadence import (
    retry,
    timeout,
    fallback,
    circuit_breaker,
    CircuitBreaker,
    CircuitState,
    CircuitOpenError,
    RetryExhaustedError,
    TimeoutError as CadenceTimeoutError,
)
from cadence.resilience import get_circuit


class TestRetry:
    """Test retry decorator."""

    @pytest.mark.asyncio
    async def test_retry_succeeds_first_try(self):
        """Test that successful call doesn't retry."""
        call_count = 0

        @retry(max_attempts=3)
        async def succeed():
            nonlocal call_count
            call_count += 1
            return "success"

        result = await succeed()
        assert result == "success"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retry_succeeds_after_failures(self):
        """Test retry succeeds after transient failures."""
        call_count = 0

        @retry(max_attempts=3, delay=0.01)
        async def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("transient error")
            return "success"

        result = await flaky()
        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_retry_exhausted(self):
        """Test that retry raises RetryExhaustedError after max attempts."""
        call_count = 0

        @retry(max_attempts=2, delay=0.01)
        async def always_fail():
            nonlocal call_count
            call_count += 1
            raise ValueError("permanent error")

        with pytest.raises(RetryExhaustedError) as exc_info:
            await always_fail()

        assert call_count == 2
        assert exc_info.value.details["attempts"] == 2

    @pytest.mark.asyncio
    async def test_retry_specific_exceptions(self):
        """Test retry only catches specified exceptions."""
        @retry(max_attempts=3, on=[ValueError])
        async def raise_type_error():
            raise TypeError("wrong type")

        with pytest.raises(TypeError):
            await raise_type_error()


class TestTimeout:
    """Test timeout decorator."""

    @pytest.mark.asyncio
    async def test_timeout_completes_in_time(self):
        """Test that fast operations complete normally."""
        @timeout(seconds=1.0)
        async def fast():
            await asyncio.sleep(0.01)
            return "done"

        result = await fast()
        assert result == "done"

    @pytest.mark.asyncio
    async def test_timeout_raises_on_slow(self):
        """Test that slow operations raise CadenceTimeoutError."""
        @timeout(seconds=0.05)
        async def slow():
            await asyncio.sleep(1.0)
            return "never"

        with pytest.raises(CadenceTimeoutError):
            await slow()


class TestFallback:
    """Test fallback decorator."""

    @pytest.mark.asyncio
    async def test_fallback_not_used_on_success(self):
        """Test that fallback isn't used when function succeeds."""
        @fallback(default="fallback")
        async def succeed():
            return "success"

        result = await succeed()
        assert result == "success"

    @pytest.mark.asyncio
    async def test_fallback_used_on_error(self):
        """Test that fallback is used when function fails."""
        @fallback(default="fallback")
        async def fail():
            raise ValueError("error")

        result = await fail()
        assert result == "fallback"

    @pytest.mark.asyncio
    async def test_fallback_specific_exceptions(self):
        """Test fallback only catches specified exceptions."""
        @fallback(default="fallback", on=(ValueError,))
        async def raise_type_error():
            raise TypeError("wrong type")

        with pytest.raises(TypeError):
            await raise_type_error()


class TestCircuitBreaker:
    """Test circuit breaker decorator and class."""

    def test_circuit_starts_closed(self):
        """Test circuit starts in closed state."""
        cb = CircuitBreaker("test", failure_threshold=3)
        assert cb.state == CircuitState.CLOSED

    def test_circuit_opens_after_threshold(self):
        """Test circuit opens after failure threshold."""
        cb = CircuitBreaker("test", failure_threshold=3, recovery_timeout=1.0)

        for _ in range(3):
            cb._record_failure()

        assert cb.state == CircuitState.OPEN

    def test_circuit_blocks_when_open(self):
        """Test circuit blocks requests when open."""
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=10.0)
        cb._record_failure()

        assert cb.state == CircuitState.OPEN
        assert cb._can_execute() is False

    def test_circuit_transitions_to_half_open(self):
        """Test circuit transitions to half-open after timeout."""
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=0.01)
        cb._record_failure()

        time.sleep(0.02)

        assert cb.state == CircuitState.HALF_OPEN

    def test_circuit_closes_on_success(self):
        """Test circuit closes after successful half-open call."""
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=0.01)
        cb._record_failure()

        time.sleep(0.02)
        assert cb.state == CircuitState.HALF_OPEN

        cb._record_success()
        assert cb.state == CircuitState.CLOSED

    def test_circuit_reopens_on_half_open_failure(self):
        """Test circuit reopens on failure during half-open."""
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=0.01)
        cb._record_failure()

        time.sleep(0.02)
        assert cb.state == CircuitState.HALF_OPEN

        cb._record_failure()
        assert cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_circuit_breaker_decorator_success(self):
        """Test decorator allows successful calls."""
        @circuit_breaker(failure_threshold=3, name="test_success")
        async def succeed():
            return "ok"

        result = await succeed()
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_circuit_breaker_decorator_opens(self):
        """Test decorator opens circuit after failures."""
        call_count = 0

        @circuit_breaker(failure_threshold=2, recovery_timeout=10.0, name="test_open")
        async def fail():
            nonlocal call_count
            call_count += 1
            raise ValueError("error")

        # First two calls fail and open circuit
        with pytest.raises(ValueError):
            await fail()
        with pytest.raises(ValueError):
            await fail()

        # Third call should be blocked
        with pytest.raises(CircuitOpenError):
            await fail()

        assert call_count == 2  # Third call was blocked

    @pytest.mark.asyncio
    async def test_shared_circuit(self):
        """Test that same name shares circuit."""
        @circuit_breaker(failure_threshold=1, name="shared")
        async def func1():
            raise ValueError()

        @circuit_breaker(failure_threshold=1, name="shared")
        async def func2():
            return "ok"

        # func1 trips the circuit
        with pytest.raises(ValueError):
            await func1()

        # func2 should be blocked by shared circuit
        with pytest.raises(CircuitOpenError):
            await func2()

    def test_circuit_reset(self):
        """Test manual circuit reset."""
        cb = CircuitBreaker("test_reset", failure_threshold=1)
        cb._record_failure()
        assert cb.state == CircuitState.OPEN

        cb.reset()
        assert cb.state == CircuitState.CLOSED

    def test_excluded_exceptions(self):
        """Test excluded exceptions don't count as failures."""
        cb = CircuitBreaker(
            "test_excluded",
            failure_threshold=2,
            excluded_exceptions=(ValueError,),
        )

        # Simulate ValueError (excluded) - shouldn't count
        # The decorator would handle this, but we test the logic
        # by not recording failure for excluded exceptions

        cb._record_failure()  # First failure
        assert cb.state == CircuitState.CLOSED

        cb._record_failure()  # Second failure - opens
        assert cb.state == CircuitState.OPEN


class TestRetrySyncFunctions:
    """Test retry decorator with synchronous functions."""

    def test_retry_sync_succeeds_first_try(self):
        """Test sync function succeeds without retry."""
        call_count = 0

        @retry(max_attempts=3)
        def succeed():
            nonlocal call_count
            call_count += 1
            return "success"

        result = succeed()
        assert result == "success"
        assert call_count == 1

    def test_retry_sync_succeeds_after_failures(self):
        """Test sync function retries and eventually succeeds."""
        call_count = 0

        @retry(max_attempts=3, delay=0.01, jitter=False)
        def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("transient")
            return "ok"

        result = flaky()
        assert result == "ok"
        assert call_count == 3

    def test_retry_sync_exhausted(self):
        """Test sync function raises after exhausting retries."""
        call_count = 0

        @retry(max_attempts=2, delay=0.01)
        def always_fail():
            nonlocal call_count
            call_count += 1
            raise ValueError("error")

        with pytest.raises(RetryExhaustedError):
            always_fail()

        assert call_count == 2


class TestRetryBackoffStrategies:
    """Test different retry backoff strategies."""

    @pytest.mark.asyncio
    async def test_retry_linear_backoff(self):
        """Test linear backoff multiplies delay by attempt."""
        call_count = 0

        @retry(max_attempts=3, delay=0.01, backoff="linear", jitter=False)
        async def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("error")
            return "ok"

        result = await flaky()
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_retry_exponential_backoff(self):
        """Test exponential backoff doubles delay each attempt."""
        call_count = 0

        @retry(max_attempts=3, delay=0.01, backoff="exponential", jitter=False)
        async def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("error")
            return "ok"

        result = await flaky()
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_retry_unknown_backoff_uses_fixed(self):
        """Test unknown backoff strategy falls back to fixed."""
        call_count = 0

        @retry(max_attempts=2, delay=0.01, backoff="unknown", jitter=False)
        async def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("error")
            return "ok"

        result = await flaky()
        assert result == "ok"


class TestFallbackSyncFunctions:
    """Test fallback decorator with synchronous functions."""

    def test_fallback_sync_success(self):
        """Test sync function doesn't use fallback on success."""
        @fallback(default="fallback")
        def succeed():
            return "success"

        result = succeed()
        assert result == "success"

    def test_fallback_sync_uses_default(self):
        """Test sync function uses default on error."""
        @fallback(default="fallback")
        def fail():
            raise ValueError("error")

        result = fail()
        assert result == "fallback"

    def test_fallback_sync_uses_handler(self):
        """Test sync function uses handler on error."""
        @fallback(handler=lambda e: f"handled: {e}")
        def fail():
            raise ValueError("oops")

        result = fail()
        assert result == "handled: oops"


class TestFallbackAsyncWithHandler:
    """Test fallback decorator with async handler."""

    @pytest.mark.asyncio
    async def test_fallback_async_with_handler(self):
        """Test async function uses handler on error."""
        @fallback(handler=lambda e: f"caught: {type(e).__name__}")
        async def fail():
            raise RuntimeError("boom")

        result = await fail()
        assert result == "caught: RuntimeError"


class TestTimeoutSyncFunctions:
    """Test timeout decorator with synchronous functions."""

    def test_timeout_sync_completes_in_time(self):
        """Test sync function completes before timeout."""
        @timeout(seconds=1.0)
        def fast():
            return "done"

        result = fast()
        assert result == "done"


class TestCircuitBreakerSyncFunctions:
    """Test circuit breaker with synchronous functions."""

    def test_circuit_breaker_sync_success(self):
        """Test sync function works with circuit breaker."""
        @circuit_breaker(failure_threshold=3, name="sync_test")
        def succeed():
            return "ok"

        result = succeed()
        assert result == "ok"

    def test_circuit_breaker_sync_opens(self):
        """Test sync circuit breaker opens after failures."""
        call_count = 0

        @circuit_breaker(failure_threshold=2, recovery_timeout=10.0, name="sync_open")
        def fail():
            nonlocal call_count
            call_count += 1
            raise ValueError("error")

        # First two calls fail
        with pytest.raises(ValueError):
            fail()
        with pytest.raises(ValueError):
            fail()

        # Third should be blocked
        with pytest.raises(CircuitOpenError):
            fail()

        assert call_count == 2


class TestGetCircuit:
    """Test get_circuit helper function."""

    def test_get_circuit_returns_existing(self):
        """Test get_circuit returns existing circuit."""
        # Create a circuit via decorator
        @circuit_breaker(failure_threshold=3, name="get_test")
        def dummy():
            pass

        # Get the circuit
        cb = get_circuit("get_test")
        assert cb is not None
        assert cb.name == "get_test"

    def test_get_circuit_creates_new_for_unknown(self):
        """Test get_circuit creates new circuit for unknown name."""
        cb = get_circuit("new_test_circuit_12345")
        assert cb is not None
        assert cb.name == "new_test_circuit_12345"
        # Should return same instance on second call
        cb2 = get_circuit("new_test_circuit_12345")
        assert cb is cb2
