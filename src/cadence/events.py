"""Async event emission for Cadence.

Provides structured domain events emitted during cadence and note execution.
Built as a CadenceHooks subclass — compose with .with_hooks().

Example:
    from cadence import Cadence, Score
    from cadence.events import EventEmitter, NOTE_COMPLETED

    emitter = EventEmitter()
    emitter.on(NOTE_COMPLETED, lambda e: print(f"{e.note_name} done"))

    cadence = (
        Cadence("checkout", score)
        .with_hooks(emitter)
        .then("process", process)
    )
    await cadence.run()
"""

from __future__ import annotations

import inspect
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

from cadence.hooks import CadenceHooks

ScoreT = TypeVar("ScoreT")
logger = logging.getLogger("cadence.events")

# Event type constants
NOTE_STARTED = "note.started"
NOTE_COMPLETED = "note.completed"
NOTE_FAILED = "note.failed"
CADENCE_STARTED = "cadence.started"
CADENCE_COMPLETED = "cadence.completed"
CADENCE_FAILED = "cadence.failed"

EventListener = Callable[["CadenceEvent"], Any]


@dataclass
class CadenceEvent:
    """Structured event emitted during cadence execution."""

    event_type: str
    cadence_name: str
    timestamp: float = field(default_factory=time.time)
    note_name: str | None = None
    duration: float | None = None
    error: Exception | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class EventEmitter(CadenceHooks):
    """
    Event-based hook that emits structured CadenceEvent objects.

    Register listeners for specific event types or use ``"*"`` for all events.
    Compose with Cadence via ``.with_hooks()``.

    Example:
        emitter = EventEmitter()
        emitter.on("note.completed", lambda e: print(e.note_name))
        emitter.on("*", lambda e: log(e))  # wildcard

        cadence = Cadence("flow", score).with_hooks(emitter)
    """

    def __init__(self) -> None:
        self._cadence_name: str = ""
        self._listeners: dict[str, list[EventListener]] = {}

    def on(self, event_type: str, listener: EventListener) -> EventEmitter:
        """Register a listener for an event type. Returns self for chaining."""
        if event_type not in self._listeners:
            self._listeners[event_type] = []
        self._listeners[event_type].append(listener)
        return self

    def off(self, event_type: str, listener: EventListener) -> EventEmitter:
        """Remove a listener. Returns self for chaining."""
        if event_type in self._listeners:
            self._listeners[event_type] = [
                existing for existing in self._listeners[event_type] if existing is not listener
            ]
        return self

    async def _emit(self, event: CadenceEvent) -> None:
        """Dispatch event to matching listeners and wildcard listeners.

        Listener exceptions are logged and swallowed so that a broken
        listener never crashes the cadence execution.
        """
        for key in (event.event_type, "*"):
            for listener in list(self._listeners.get(key, [])):
                try:
                    result = listener(event)
                    if inspect.iscoroutine(result):
                        await result
                except Exception:
                    logger.warning(
                        "EventEmitter listener error for %s",
                        event.event_type,
                        exc_info=True,
                    )

    # -- CadenceHooks interface --

    async def before_cadence(self, cadence_name: str, score: ScoreT) -> None:
        self._cadence_name = cadence_name
        await self._emit(
            CadenceEvent(
                event_type=CADENCE_STARTED,
                cadence_name=cadence_name,
            )
        )

    async def after_cadence(
        self,
        cadence_name: str,
        score: ScoreT,
        duration: float,
        error: Exception | None = None,
    ) -> None:
        event_type = CADENCE_FAILED if error else CADENCE_COMPLETED
        await self._emit(
            CadenceEvent(
                event_type=event_type,
                cadence_name=cadence_name,
                duration=duration,
                error=error,
            )
        )

    async def before_note(self, note_name: str, score: ScoreT) -> None:
        await self._emit(
            CadenceEvent(
                event_type=NOTE_STARTED,
                cadence_name=self._cadence_name,
                note_name=note_name,
            )
        )

    async def after_note(
        self,
        note_name: str,
        score: ScoreT,
        duration: float,
        error: Exception | None = None,
    ) -> None:
        event_type = NOTE_FAILED if error else NOTE_COMPLETED
        await self._emit(
            CadenceEvent(
                event_type=event_type,
                cadence_name=self._cadence_name,
                note_name=note_name,
                duration=duration,
                error=error,
            )
        )
