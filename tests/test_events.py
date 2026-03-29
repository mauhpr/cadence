"""Tests for the async event emission system.

Tests cover:
- Event listener registration and dispatch
- Wildcard listeners
- Event payloads (note_name, duration, error, etc.)
- Async listeners
- Listener removal with off()
- Multiple emitters composing
"""

from dataclasses import dataclass
from typing import Any

import pytest

from cadence import Cadence, Score, note
from cadence.events import (
    CADENCE_COMPLETED,
    CADENCE_FAILED,
    CADENCE_STARTED,
    NOTE_COMPLETED,
    NOTE_FAILED,
    NOTE_STARTED,
    CadenceEvent,
    EventEmitter,
)


@dataclass
class EventTestScore(Score):
    """Score for event tests."""

    value: str = ""


@note
async def set_value(score: EventTestScore) -> None:
    score.value = "done"


@note
async def fail_task(score: EventTestScore) -> None:
    raise RuntimeError("boom")


class TestEventEmitter:
    """Test EventEmitter hook dispatches events correctly."""

    @pytest.mark.asyncio
    async def test_note_completed_event(self) -> None:
        events: list[CadenceEvent] = []
        emitter = EventEmitter()
        emitter.on(NOTE_COMPLETED, events.append)

        score = EventTestScore()
        score.__post_init__()

        await Cadence("test", score).with_hooks(emitter).then("step", set_value).run()

        assert len(events) == 1
        assert events[0].event_type == NOTE_COMPLETED
        assert events[0].note_name == "step"
        assert events[0].cadence_name == "test"
        assert events[0].duration is not None
        assert events[0].duration >= 0
        assert events[0].error is None

    @pytest.mark.asyncio
    async def test_note_started_event(self) -> None:
        events: list[CadenceEvent] = []
        emitter = EventEmitter()
        emitter.on(NOTE_STARTED, events.append)

        score = EventTestScore()
        score.__post_init__()

        await Cadence("test", score).with_hooks(emitter).then("step", set_value).run()

        assert len(events) == 1
        assert events[0].event_type == NOTE_STARTED
        assert events[0].note_name == "step"

    @pytest.mark.asyncio
    async def test_cadence_lifecycle_events(self) -> None:
        events: list[CadenceEvent] = []
        emitter = EventEmitter()
        emitter.on(CADENCE_STARTED, events.append)
        emitter.on(CADENCE_COMPLETED, events.append)

        score = EventTestScore()
        score.__post_init__()

        await Cadence("flow", score).with_hooks(emitter).then("step", set_value).run()

        assert len(events) == 2
        assert events[0].event_type == CADENCE_STARTED
        assert events[0].cadence_name == "flow"
        assert events[1].event_type == CADENCE_COMPLETED
        assert events[1].duration is not None

    @pytest.mark.asyncio
    async def test_note_failed_event(self) -> None:
        events: list[CadenceEvent] = []
        emitter = EventEmitter()
        emitter.on(NOTE_FAILED, events.append)

        score = EventTestScore()
        score.__post_init__()

        with pytest.raises(Exception):
            await Cadence("test", score).with_hooks(emitter).then("bad", fail_task).run()

        assert len(events) == 1
        assert events[0].event_type == NOTE_FAILED
        assert events[0].note_name == "bad"
        assert events[0].error is not None

    @pytest.mark.asyncio
    async def test_cadence_failed_event(self) -> None:
        events: list[CadenceEvent] = []
        emitter = EventEmitter()
        emitter.on(CADENCE_FAILED, events.append)

        score = EventTestScore()
        score.__post_init__()

        with pytest.raises(Exception):
            await Cadence("test", score).with_hooks(emitter).then("bad", fail_task).run()

        assert len(events) == 1
        assert events[0].event_type == CADENCE_FAILED

    @pytest.mark.asyncio
    async def test_wildcard_listener(self) -> None:
        events: list[CadenceEvent] = []
        emitter = EventEmitter()
        emitter.on("*", events.append)

        score = EventTestScore()
        score.__post_init__()

        await Cadence("test", score).with_hooks(emitter).then("step", set_value).run()

        event_types = [e.event_type for e in events]
        assert CADENCE_STARTED in event_types
        assert NOTE_STARTED in event_types
        assert NOTE_COMPLETED in event_types
        assert CADENCE_COMPLETED in event_types

    @pytest.mark.asyncio
    async def test_off_removes_listener(self) -> None:
        events: list[CadenceEvent] = []
        handler = events.append
        emitter = EventEmitter()
        emitter.on(NOTE_COMPLETED, handler)
        emitter.off(NOTE_COMPLETED, handler)

        score = EventTestScore()
        score.__post_init__()

        await Cadence("test", score).with_hooks(emitter).then("step", set_value).run()

        assert len(events) == 0

    @pytest.mark.asyncio
    async def test_async_listener(self) -> None:
        events: list[CadenceEvent] = []

        async def async_handler(event: CadenceEvent) -> None:
            events.append(event)

        emitter = EventEmitter()
        emitter.on(NOTE_COMPLETED, async_handler)

        score = EventTestScore()
        score.__post_init__()

        await Cadence("test", score).with_hooks(emitter).then("step", set_value).run()

        assert len(events) == 1
        assert events[0].event_type == NOTE_COMPLETED

    @pytest.mark.asyncio
    async def test_event_timestamp(self) -> None:
        events: list[CadenceEvent] = []
        emitter = EventEmitter()
        emitter.on(NOTE_COMPLETED, events.append)

        score = EventTestScore()
        score.__post_init__()

        await Cadence("test", score).with_hooks(emitter).then("step", set_value).run()

        assert events[0].timestamp > 0

    @pytest.mark.asyncio
    async def test_multiple_emitters_compose(self) -> None:
        events_a: list[CadenceEvent] = []
        events_b: list[CadenceEvent] = []

        emitter_a = EventEmitter()
        emitter_a.on(NOTE_COMPLETED, events_a.append)

        emitter_b = EventEmitter()
        emitter_b.on(NOTE_COMPLETED, events_b.append)

        score = EventTestScore()
        score.__post_init__()

        await (
            Cadence("test", score)
            .with_hooks(emitter_a)
            .with_hooks(emitter_b)
            .then("step", set_value)
            .run()
        )

        assert len(events_a) == 1
        assert len(events_b) == 1

    @pytest.mark.asyncio
    async def test_chained_on_registration(self) -> None:
        events: list[CadenceEvent] = []
        emitter = (
            EventEmitter()
            .on(NOTE_STARTED, events.append)
            .on(NOTE_COMPLETED, events.append)
        )

        score = EventTestScore()
        score.__post_init__()

        await Cadence("test", score).with_hooks(emitter).then("step", set_value).run()

        assert len(events) == 2

    @pytest.mark.asyncio
    async def test_listener_exception_does_not_crash_cadence(self) -> None:
        """A throwing listener must not crash the cadence."""
        good_events: list[CadenceEvent] = []

        def bad_listener(event: CadenceEvent) -> None:
            raise RuntimeError("listener bug")

        emitter = EventEmitter()
        emitter.on(NOTE_COMPLETED, bad_listener)
        emitter.on(NOTE_COMPLETED, good_events.append)

        score = EventTestScore()
        score.__post_init__()

        # Should NOT raise — listener errors are swallowed
        result = await (
            Cadence("test", score).with_hooks(emitter).then("step", set_value).run()
        )

        assert result.value == "done"
        # The good listener after the bad one should still fire
        assert len(good_events) == 1

    @pytest.mark.asyncio
    async def test_async_listener_exception_does_not_crash(self) -> None:
        events: list[CadenceEvent] = []

        async def bad_async(event: CadenceEvent) -> None:
            raise RuntimeError("async listener bug")

        emitter = EventEmitter()
        emitter.on(NOTE_COMPLETED, bad_async)
        emitter.on(NOTE_COMPLETED, events.append)

        score = EventTestScore()
        score.__post_init__()

        result = await (
            Cadence("test", score).with_hooks(emitter).then("step", set_value).run()
        )

        assert result.value == "done"
        assert len(events) == 1

    @pytest.mark.asyncio
    async def test_wildcard_off(self) -> None:
        events: list[CadenceEvent] = []
        handler = events.append
        emitter = EventEmitter()
        emitter.on("*", handler)
        emitter.off("*", handler)

        score = EventTestScore()
        score.__post_init__()

        await Cadence("test", score).with_hooks(emitter).then("step", set_value).run()

        assert len(events) == 0
