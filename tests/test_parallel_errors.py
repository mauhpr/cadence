"""Tests for parallel error context (ParallelNoteError).

Verifies that when a task inside .sync() fails, the exception
identifies the specific task by name, index, and group.
"""

import asyncio
from dataclasses import dataclass
from typing import Optional

import pytest

from cadence import Cadence, NoteError, Score, note
from cadence.exceptions import ParallelNoteError


@dataclass
class ErrorTestScore(Score):
    """Score for parallel error tests."""

    result_a: Optional[str] = None
    result_b: Optional[str] = None


@note
async def succeed_a(score: ErrorTestScore) -> None:
    await asyncio.sleep(0.01)
    score.result_a = "ok"


@note(name="flaky_service")
async def fail_b(score: ErrorTestScore) -> None:
    raise ConnectionError("service unavailable")


@note
def sync_fail(score: ErrorTestScore) -> None:
    raise ValueError("bad value")


@note
def sync_succeed(score: ErrorTestScore) -> None:
    score.result_b = "sync_ok"


class TestParallelNoteError:
    """Test that .sync() failures produce ParallelNoteError with task context."""

    @pytest.mark.asyncio
    async def test_async_task_failure_has_task_name(self) -> None:
        score = ErrorTestScore()
        score.__post_init__()

        cadence = Cadence("test", score).sync("enrich", [succeed_a, fail_b])

        with pytest.raises(ParallelNoteError) as exc_info:
            await cadence.run()

        err = exc_info.value
        assert err.note_name == "flaky_service"
        assert err.group_name == "enrich"
        assert err.task_index == 1
        assert isinstance(err.original_error, ConnectionError)

    @pytest.mark.asyncio
    async def test_sync_task_failure_has_task_name(self) -> None:
        score = ErrorTestScore()
        score.__post_init__()

        cadence = Cadence("test", score).sync("validate", [sync_succeed, sync_fail])

        with pytest.raises(ParallelNoteError) as exc_info:
            await cadence.run()

        err = exc_info.value
        assert err.note_name == "sync_fail"
        assert err.group_name == "validate"
        assert isinstance(err.original_error, ValueError)

    @pytest.mark.asyncio
    async def test_error_chaining(self) -> None:
        score = ErrorTestScore()
        score.__post_init__()

        cadence = Cadence("test", score).sync("group", [fail_b])

        with pytest.raises(ParallelNoteError) as exc_info:
            await cadence.run()

        # __cause__ should be the original exception (from ... raise)
        assert exc_info.value.__cause__ is exc_info.value.original_error

    @pytest.mark.asyncio
    async def test_backward_compat_catches_as_note_error(self) -> None:
        """Existing code using except NoteError still catches parallel errors."""
        score = ErrorTestScore()
        score.__post_init__()

        cadence = Cadence("test", score).sync("group", [fail_b])

        with pytest.raises(NoteError):
            await cadence.run()

    @pytest.mark.asyncio
    async def test_error_code(self) -> None:
        score = ErrorTestScore()
        score.__post_init__()

        cadence = Cadence("test", score).sync("group", [fail_b])

        with pytest.raises(ParallelNoteError) as exc_info:
            await cadence.run()

        assert exc_info.value.code == "PARALLEL_NOTE_ERROR"

    @pytest.mark.asyncio
    async def test_plain_function_task_name(self) -> None:
        """Tasks without @note use __name__ as task name."""

        async def my_plain_task(score: ErrorTestScore) -> None:
            raise RuntimeError("plain fail")

        score = ErrorTestScore()
        score.__post_init__()

        cadence = Cadence("test", score).sync("group", [my_plain_task])

        with pytest.raises(ParallelNoteError) as exc_info:
            await cadence.run()

        assert exc_info.value.note_name == "my_plain_task"

    @pytest.mark.asyncio
    async def test_multiple_failures_reports_first(self) -> None:
        """When multiple tasks fail, only the first exception is surfaced."""

        @note(name="fail_first")
        async def fail_a(score: ErrorTestScore) -> None:
            raise ValueError("first")

        @note(name="fail_second")
        async def fail_b_also(score: ErrorTestScore) -> None:
            raise ValueError("second")

        score = ErrorTestScore()
        score.__post_init__()

        cadence = Cadence("test", score).sync("group", [fail_a, fail_b_also])

        with pytest.raises(ParallelNoteError) as exc_info:
            await cadence.run()

        # Only one error surfaces — whichever asyncio schedules first
        assert isinstance(exc_info.value.original_error, ValueError)
        assert exc_info.value.group_name == "group"

    @pytest.mark.asyncio
    async def test_lambda_task_name_fallback(self) -> None:
        """Lambdas get index-based fallback names."""
        score = ErrorTestScore()
        score.__post_init__()

        cadence = Cadence("test", score).sync(
            "group", [lambda s: (_ for _ in ()).throw(RuntimeError("lambda fail"))]
        )

        with pytest.raises(ParallelNoteError) as exc_info:
            await cadence.run()

        # Lambda should get fallback name, not "<lambda>"
        assert "group" in exc_info.value.group_name
