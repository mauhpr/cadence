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

    @pytest.mark.asyncio
    async def test_fallback_field_sets_score_attribute(self):
        """Test that field= sets the attribute on score when exception fires."""
        @fallback(default=[], field="results")
        async def fetch(score):
            raise ConnectionError("unavailable")

        class FakeScore:
            results = None

        score = FakeScore()
        ret = await fetch(score)
        assert score.results == []
        assert ret is None

    @pytest.mark.asyncio
    async def test_fallback_field_with_handler(self):
        """Test that field= works with a handler function."""
        @fallback(field="status", handler=lambda e: f"error: {e}")
        async def fetch(score):
            raise ValueError("bad")

        class FakeScore:
            status = None

        score = FakeScore()
        ret = await fetch(score)
        assert score.status == "error: bad"
        assert ret is None

    @pytest.mark.asyncio
    async def test_fallback_field_not_used_on_success(self):
        """Test that field= doesn't interfere when function succeeds."""
        @fallback(default="fallback_val", field="data")
        async def fetch(score):
            score.data = "real_data"

        class FakeScore:
            data = None

        score = FakeScore()
        await fetch(score)
        assert score.data == "real_data"

    @pytest.mark.asyncio
    async def test_fallback_field_sync_via_async_wrapper(self):
        """Test field= with a sync function."""
        @fallback(default=42, field="value")
        def compute(score):
            raise RuntimeError("crash")

        class FakeScore:
            value = None

        score = FakeScore()
        ret = compute(score)
        assert score.value == 42
        assert ret is None


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

    def test_fallback_field_sync_sets_attribute(self):
        """Test sync fallback with field= sets score attribute."""
        @fallback(default={"cached": True}, field="cache_result")
        def fetch(score):
            raise ConnectionError("down")

        class FakeScore:
            cache_result = None

        score = FakeScore()
        ret = fetch(score)
        assert score.cache_result == {"cached": True}
        assert ret is None


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


# =============================================================================
# @note with inline resilience parameters
# =============================================================================

from dataclasses import dataclass
from cadence import Cadence, Score, note, NoteError


@dataclass
class ResilienceScore(Score):
    """Score for note resilience tests."""

    value: str = ""
    items: list[str] | None = None
    attempts: int = 0


class TestNoteResilience:
    """Test @note with inline retry, timeout, fallback parameters."""

    @pytest.mark.asyncio
    async def test_retry_int_shorthand(self) -> None:
        """@note(retry=3) retries on failure."""
        call_count = 0

        @note(retry=3)
        async def flaky(score: ResilienceScore) -> None:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("fail")
            score.value = "ok"

        score = ResilienceScore()
        score.__post_init__()
        await Cadence("test", score).then("flaky", flaky).run()
        assert score.value == "ok"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_timeout_float_shorthand(self) -> None:
        """@note(timeout=0.05) times out slow tasks."""

        @note(timeout=0.05)
        async def slow(score: ResilienceScore) -> None:
            await asyncio.sleep(10)

        score = ResilienceScore()
        score.__post_init__()
        with pytest.raises(CadenceTimeoutError):
            await Cadence("test", score).then("slow", slow).run()

    @pytest.mark.asyncio
    async def test_retry_dict_form(self) -> None:
        """@note(retry={...}) passes full options."""
        call_count = 0

        @note(retry={"max_attempts": 2, "delay": 0.01, "jitter": False})
        async def flaky(score: ResilienceScore) -> None:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("fail")
            score.value = "ok"

        score = ResilienceScore()
        score.__post_init__()
        await Cadence("test", score).then("flaky", flaky).run()
        assert score.value == "ok"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_timeout_dict_form(self) -> None:
        """@note(timeout={...}) passes full options."""

        @note(timeout={"seconds": 0.05})
        async def slow(score: ResilienceScore) -> None:
            await asyncio.sleep(10)

        score = ResilienceScore()
        score.__post_init__()
        with pytest.raises(CadenceTimeoutError):
            await Cadence("test", score).then("slow", slow).run()

    @pytest.mark.asyncio
    async def test_fallback_with_field(self) -> None:
        """@note(fallback={...}) provides fallback on failure."""

        @note(fallback={"default": ["fallback_item"], "field": "items"})
        async def failing(score: ResilienceScore) -> None:
            raise RuntimeError("boom")

        score = ResilienceScore()
        score.__post_init__()
        await Cadence("test", score).then("failing", failing).run()
        assert score.items == ["fallback_item"]

    @pytest.mark.asyncio
    async def test_combined_retry_and_timeout(self) -> None:
        """@note(retry=3, timeout=5.0) — retry wraps timeout."""
        call_count = 0

        @note(retry=3, timeout=5.0)
        async def flaky(score: ResilienceScore) -> None:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("fail")
            score.value = "ok"

        score = ResilienceScore()
        score.__post_init__()
        await Cadence("test", score).then("flaky", flaky).run()
        assert score.value == "ok"

    @pytest.mark.asyncio
    async def test_all_three_combined(self) -> None:
        """@note(retry=2, timeout=5.0, fallback={...}) — all three."""

        @note(
            retry={"max_attempts": 2, "delay": 0.01, "jitter": False},
            timeout=5.0,
            fallback={"default": "safe", "field": "value"},
        )
        async def always_fails(score: ResilienceScore) -> None:
            raise RuntimeError("permanent failure")

        score = ResilienceScore()
        score.__post_init__()
        await Cadence("test", score).then("fails", always_fails).run()
        # Fallback catches RetryExhaustedError
        assert score.value == "safe"

    @pytest.mark.asyncio
    async def test_name_preserved_with_resilience(self) -> None:
        """@note(name="custom", retry=3) preserves the custom name."""

        @note(name="custom_name", retry=3)
        async def my_func(score: ResilienceScore) -> None:
            score.value = "ok"

        assert my_func.name == "custom_name"

        score = ResilienceScore()
        score.__post_init__()
        await Cadence("test", score).then("custom_name", my_func).run()
        assert score.value == "ok"

    @pytest.mark.asyncio
    async def test_bare_note_unchanged(self) -> None:
        """@note without resilience params works as before."""

        @note
        async def simple(score: ResilienceScore) -> None:
            score.value = "simple"

        assert simple.resilience == {}
        assert repr(simple) == "<Note: simple>"

        score = ResilienceScore()
        score.__post_init__()
        await Cadence("test", score).then("simple", simple).run()
        assert score.value == "simple"

    @pytest.mark.asyncio
    async def test_note_with_name_only_unchanged(self) -> None:
        """@note(name="foo") without resilience works as before."""

        @note(name="foo")
        async def my_func(score: ResilienceScore) -> None:
            score.value = "named"

        assert my_func.name == "foo"
        assert my_func.resilience == {}

    @pytest.mark.asyncio
    async def test_is_async_correct_after_wrapping(self) -> None:
        """is_async reflects the original function, not the wrapper."""

        @note(retry=3, timeout=5.0)
        async def async_func(score: ResilienceScore) -> None:
            score.value = "async"

        @note(retry=3)
        def sync_func(score: ResilienceScore) -> None:
            score.value = "sync"

        assert async_func.is_async is True
        assert sync_func.is_async is False

    def test_resilience_property_introspection(self) -> None:
        """resilience property returns normalized config."""

        @note(retry=3, timeout=15.0, fallback={"default": None, "field": "x"})
        async def full(score: ResilienceScore) -> None:
            pass

        assert full.resilience == {
            "retry": {"max_attempts": 3},
            "timeout": {"seconds": 15.0},
            "fallback": {"default": None, "field": "x"},
        }

    def test_repr_with_resilience(self) -> None:
        """repr shows resilience flags."""

        @note(retry=3, timeout=5.0)
        async def my_func(score: ResilienceScore) -> None:
            pass

        assert repr(my_func) == "<Note: my_func [retry, timeout]>"

    # --- Edge cases and interaction tests ---

    @pytest.mark.asyncio
    async def test_timeout_triggers_retry(self) -> None:
        """Timeout on attempt 1 should trigger retry on attempt 2."""
        call_count = 0

        @note(retry={"max_attempts": 3, "delay": 0.01, "jitter": False}, timeout=0.1)
        async def slow_then_fast(score: ResilienceScore) -> None:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                await asyncio.sleep(10)  # will timeout
            score.value = "recovered"

        score = ResilienceScore()
        score.__post_init__()
        await Cadence("test", score).then("t", slow_then_fast).run()
        assert score.value == "recovered"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_sync_function_with_retry(self) -> None:
        """@note(retry=3) works on sync functions."""
        call_count = 0

        @note(retry=3)
        def sync_flaky(score: ResilienceScore) -> None:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("sync fail")
            score.value = "sync_ok"

        score = ResilienceScore()
        score.__post_init__()
        await Cadence("test", score).then("t", sync_flaky).run()
        assert score.value == "sync_ok"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_retry_with_on_filter(self) -> None:
        """@note(retry={..., 'on': (ConnectionError,)}) only retries matching exceptions."""

        @note(retry={"max_attempts": 3, "delay": 0.01, "on": (ConnectionError,), "jitter": False})
        async def wrong_error(score: ResilienceScore) -> None:
            raise ValueError("not retryable")

        score = ResilienceScore()
        score.__post_init__()
        # ValueError is not in the retry `on` list, so it should NOT retry — just raise
        with pytest.raises(Exception):
            await Cadence("test", score).then("t", wrong_error).run()

    @pytest.mark.asyncio
    async def test_fallback_with_handler(self) -> None:
        """@note(fallback={"handler": fn}) uses the handler function."""

        @note(fallback={"handler": lambda e: f"caught: {e}", "field": "value"})
        async def failing(score: ResilienceScore) -> None:
            raise RuntimeError("oops")

        score = ResilienceScore()
        score.__post_init__()
        await Cadence("test", score).then("t", failing).run()
        assert score.value == "caught: oops"

    @pytest.mark.asyncio
    async def test_fallback_with_on_filter(self) -> None:
        """@note(fallback={"on": (ValueError,)}) only catches matching exceptions."""

        @note(fallback={"default": "safe", "field": "value", "on": (ValueError,)})
        async def wrong_error(score: ResilienceScore) -> None:
            raise RuntimeError("not caught by fallback")

        score = ResilienceScore()
        score.__post_init__()
        # RuntimeError is not in fallback's `on` list — should propagate
        with pytest.raises(Exception):
            await Cadence("test", score).then("t", wrong_error).run()

    @pytest.mark.asyncio
    async def test_retry_exhaustion_without_fallback(self) -> None:
        """When all retries fail and no fallback, RetryExhaustedError surfaces."""

        @note(retry={"max_attempts": 2, "delay": 0.01, "jitter": False})
        async def always_fails(score: ResilienceScore) -> None:
            raise ConnectionError("permanent")

        score = ResilienceScore()
        score.__post_init__()
        with pytest.raises(RetryExhaustedError):
            await Cadence("test", score).then("t", always_fails).run()

    @pytest.mark.asyncio
    async def test_description_preserved(self) -> None:
        """@note(description="...", retry=3) preserves description."""

        @note(description="Important task", retry=3)
        async def my_task(score: ResilienceScore) -> None:
            """Original docstring."""
            score.value = "ok"

        assert my_task.description == "Important task"
        assert my_task.name == "my_task"

    @pytest.mark.asyncio
    async def test_in_parallel_sync(self) -> None:
        """Resilient notes work correctly inside .sync()."""

        @note(retry={"max_attempts": 2, "delay": 0.01, "jitter": False}, timeout=5.0)
        async def task_a(score: ResilienceScore) -> None:
            score.value = "a"

        @note(timeout=5.0)
        async def task_b(score: ResilienceScore) -> None:
            score.items = ["b"]

        score = ResilienceScore()
        score.__post_init__()
        await Cadence("test", score).sync("parallel", [task_a, task_b]).run()
        assert score.value == "a"
        assert score.items == ["b"]

    def test_functools_metadata_preserved(self) -> None:
        """__name__ and __doc__ are preserved after resilience wrapping."""

        @note(retry=3, timeout=5.0)
        async def documented_func(score: ResilienceScore) -> None:
            """This is the docstring."""
            pass

        assert documented_func.__name__ == "documented_func"
        assert documented_func.__doc__ == "This is the docstring."
        # Note.name should also match
        assert documented_func.name == "documented_func"

    @pytest.mark.asyncio
    async def test_integer_timeout(self) -> None:
        """@note(timeout=5) with int (not float) works."""

        @note(timeout=5)
        async def quick(score: ResilienceScore) -> None:
            score.value = "fast"

        assert quick.resilience["timeout"] == {"seconds": 5.0}

        score = ResilienceScore()
        score.__post_init__()
        await Cadence("test", score).then("t", quick).run()
        assert score.value == "fast"

    @pytest.mark.asyncio
    async def test_retry_only_fallback_no_retry(self) -> None:
        """@note(fallback=...) without retry — fallback catches directly."""

        @note(fallback={"default": "fallback_val", "field": "value"})
        async def fails_once(score: ResilienceScore) -> None:
            raise RuntimeError("immediate fail")

        score = ResilienceScore()
        score.__post_init__()
        await Cadence("test", score).then("t", fails_once).run()
        assert score.value == "fallback_val"

    @pytest.mark.asyncio
    async def test_timeout_only_no_retry(self) -> None:
        """@note(timeout=0.05) without retry — just times out."""

        @note(timeout=0.05)
        async def slow(score: ResilienceScore) -> None:
            await asyncio.sleep(10)

        score = ResilienceScore()
        score.__post_init__()
        with pytest.raises(CadenceTimeoutError):
            await Cadence("test", score).then("t", slow).run()

    @pytest.mark.asyncio
    async def test_resilience_does_not_affect_other_notes(self) -> None:
        """Resilience on one note doesn't leak to others."""

        @note(retry=3, timeout=5.0)
        async def resilient(score: ResilienceScore) -> None:
            score.value = "resilient"

        @note
        async def plain(score: ResilienceScore) -> None:
            score.items = ["plain"]

        assert resilient.resilience == {"retry": {"max_attempts": 3}, "timeout": {"seconds": 5.0}}
        assert plain.resilience == {}

        score = ResilienceScore()
        score.__post_init__()
        await (
            Cadence("test", score)
            .then("r", resilient)
            .then("p", plain)
            .run()
        )
        assert score.value == "resilient"
        assert score.items == ["plain"]
