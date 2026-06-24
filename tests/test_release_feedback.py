"""Regression tests for feedback addressed in the v0.7 release."""

from __future__ import annotations

import inspect
from collections.abc import Coroutine
from dataclasses import dataclass
from typing import get_args, get_origin

import pytest

from cadence import Cadence, Score, Skip, note


@dataclass
class FeedbackScore(Score):
    value: int = 0
    skipped: bool = False


@dataclass
class PlainFeedbackScore:
    value: int = 0
    skipped: bool = False


@note
async def increment(score: FeedbackScore) -> None:
    score.value += 1


@note
async def is_positive(score: FeedbackScore) -> bool:
    return score.value > 0


def test_run_signature_is_visibly_awaitable() -> None:
    """Runtime introspection should not make async run() look like ScoreT."""
    signature = inspect.signature(Cadence.run)

    assert get_origin(signature.return_annotation) is Coroutine
    assert get_args(signature.return_annotation)[-1].__name__ == "ScoreT"


def test_note_supports_retry_integer_form() -> None:
    """@note(retry=2) should be accepted for the common shorthand form."""

    @note(retry=2)
    async def step(score: FeedbackScore) -> None:
        score.value += 1

    assert step.name == "step"


def test_note_supports_retry_config_form() -> None:
    """@note(retry={...}) should remain accepted for explicit retry config."""

    @note(retry={"max_attempts": 2, "delay": 0, "jitter": False})
    async def step(score: FeedbackScore) -> None:
        score.value += 1

    assert step.name == "step"


def test_note_records_inline_resilience_metadata() -> None:
    """Inline resilience options should be normalized for introspection."""

    @note(
        name="resilient",
        retry={"max_attempts": 2, "delay": 0, "jitter": False},
        timeout={"seconds": 0.5},
        fallback={"default": None, "field": "skipped"},
    )
    async def step(score: FeedbackScore) -> None:
        score.value += 1

    assert step.name == "resilient"
    assert step.resilience == {
        "retry": {"max_attempts": 2, "delay": 0, "jitter": False},
        "timeout": {"seconds": 0.5},
        "fallback": {"default": None, "field": "skipped"},
    }
    assert repr(step) == "<Note: resilient [retry, timeout, fallback]>"


def test_skip_exception_exposes_reason() -> None:
    """Skip should expose the short-circuit reason in structured fields."""
    skip = Skip("duplicate")

    assert skip.reason == "duplicate"
    assert skip.code == "SKIP"
    assert skip.details == {"reason": "duplicate"}


@pytest.mark.asyncio
async def test_split_accepts_single_task_for_each_branch() -> None:
    """The common one-task branch case should not require list wrapping."""
    score = FeedbackScore(value=1)
    cadence = Cadence("test", score).split(
        "route",
        condition=is_positive,
        if_true=increment,
        if_false=increment,
    )

    result = await cadence.run()

    assert result.value == 2


@pytest.mark.asyncio
async def test_split_accepts_missing_false_branch() -> None:
    """False branches should be optional when only the true branch does work."""
    score = FeedbackScore(value=-1)
    cadence = (
        Cadence("test", score)
        .split("route", condition=is_positive, if_true=increment)
        .then("after", increment)
    )

    result = await cadence.run()

    assert result.value == 0


@pytest.mark.asyncio
async def test_skip_stops_cadence_cleanly() -> None:
    """Raising Skip should stop remaining measures without invoking error handling."""

    @note
    async def dedupe(score: FeedbackScore) -> None:
        score.skipped = True
        raise Skip("duplicate")

    def error_handler(score: FeedbackScore, error: Exception) -> None:
        raise AssertionError(f"Skip should not be handled as an error: {error}")

    score = FeedbackScore()
    result = await (
        Cadence("test", score)
        .on_error(error_handler)
        .then("dedupe", dedupe)
        .then("increment", increment)
        .run()
    )

    assert result.skipped is True
    assert result.value == 0


@pytest.mark.asyncio
async def test_skip_from_parallel_group_stops_cadence_cleanly() -> None:
    """Skip raised inside a parallel task should not be wrapped as an error."""

    @note
    async def dedupe(score: PlainFeedbackScore) -> None:
        score.skipped = True
        raise Skip("duplicate")

    @note
    async def increment_plain(score: PlainFeedbackScore) -> None:
        score.value += 1

    score = PlainFeedbackScore()
    result = await (
        Cadence("test", score).sync("dedupe", [dedupe]).then("after", increment_plain).run()
    )

    assert result.skipped is True
    assert result.value == 0
