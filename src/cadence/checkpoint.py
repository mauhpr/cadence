"""Persistence and checkpointing for Cadence workflows.

Enables crash recovery by saving score state after each successful measure.
On re-run with the same run_id, completed measures are skipped and the score
is restored from the last checkpoint.

Example:
    from cadence import Cadence, Score
    from cadence.checkpoint import InMemoryCheckpointStore

    store = InMemoryCheckpointStore()

    cadence = (
        Cadence("disburse", score)
        .with_checkpoint(store, run_id="order-123")
        .then("validate", validate)
        .then("charge", charge)
        .then("disburse", disburse)
    )
    await cadence.run()  # Resumes from last checkpoint if run_id has prior state
"""

from __future__ import annotations

import copy
import dataclasses
from typing import Any, Protocol, TypeVar, runtime_checkable

from cadence.hooks import CadenceHooks

ScoreT = TypeVar("ScoreT")


@runtime_checkable
class CheckpointStore(Protocol):
    """Protocol for persisting cadence checkpoints.

    Implement this with Redis, a database, or any durable store
    for production use. See ``InMemoryCheckpointStore`` for the interface.

    Implementor requirements:
        - ``save_checkpoint`` must be **atomic** — a partial write after a crash
          must not leave the store in an inconsistent state.
        - ``get_completed_measures`` and ``get_last_score_state`` must return
          consistent data (i.e., from the same checkpoint, not a mix).
    """

    async def save_checkpoint(
        self,
        cadence_name: str,
        run_id: str,
        measure_name: str,
        measure_index: int,
        score_state: dict[str, Any],
    ) -> None:
        """Save checkpoint after a measure completes successfully."""
        ...

    async def get_completed_measures(
        self,
        cadence_name: str,
        run_id: str,
    ) -> set[str]:
        """Get names of measures that completed in a previous run."""
        ...

    async def get_last_score_state(
        self,
        cadence_name: str,
        run_id: str,
    ) -> dict[str, Any] | None:
        """Get the score state from the last completed checkpoint."""
        ...

    async def clear_checkpoints(
        self,
        cadence_name: str,
        run_id: str,
    ) -> None:
        """Clear all checkpoints for a run (call on successful completion)."""
        ...


class InMemoryCheckpointStore:
    """In-memory checkpoint store for development and testing.

    Not durable across process restarts — use a persistent store
    (Redis, database) for production.
    """

    def __init__(self) -> None:
        self._checkpoints: dict[str, dict[str, Any]] = {}

    def _key(self, cadence_name: str, run_id: str) -> str:
        return f"{cadence_name}:{run_id}"

    async def save_checkpoint(
        self,
        cadence_name: str,
        run_id: str,
        measure_name: str,
        measure_index: int,
        score_state: dict[str, Any],
    ) -> None:
        key = self._key(cadence_name, run_id)
        if key not in self._checkpoints:
            self._checkpoints[key] = {
                "completed": set(),
                "last_score": None,
                "last_index": -1,
            }
        self._checkpoints[key]["completed"].add(measure_name)
        self._checkpoints[key]["last_score"] = score_state
        self._checkpoints[key]["last_index"] = measure_index

    async def get_completed_measures(
        self,
        cadence_name: str,
        run_id: str,
    ) -> set[str]:
        key = self._key(cadence_name, run_id)
        entry = self._checkpoints.get(key)
        if entry is None:
            return set()
        return set(entry["completed"])

    async def get_last_score_state(
        self,
        cadence_name: str,
        run_id: str,
    ) -> dict[str, Any] | None:
        key = self._key(cadence_name, run_id)
        entry = self._checkpoints.get(key)
        if entry is None:
            return None
        result: dict[str, Any] | None = entry["last_score"]
        return result

    async def clear_checkpoints(
        self,
        cadence_name: str,
        run_id: str,
    ) -> None:
        key = self._key(cadence_name, run_id)
        self._checkpoints.pop(key, None)


def serialize_score(score: Any) -> dict[str, Any]:
    """Serialize a score to a dict for checkpointing.

    Uses ``dataclasses.asdict`` for dataclass scores, falls back
    to ``vars()`` for other types. Deep-copies values to prevent
    mutation after serialization.

    .. warning::
        Score fields must be JSON-friendly types (str, int, float, bool,
        list, dict, None). ``Atomic``, ``AtomicList``, ``AtomicDict``
        wrappers contain ``threading.Lock`` and **cannot** be serialized.
        Avoid using them on scores that will be checkpointed.
    """
    if dataclasses.is_dataclass(score) and not isinstance(score, type):
        return dataclasses.asdict(score)
    return {
        k: copy.deepcopy(v)
        for k, v in vars(score).items()
        if not k.startswith("_")
    }


def restore_score(score: Any, state: dict[str, Any]) -> None:
    """Restore score state from a checkpoint dict.

    Sets each key from ``state`` onto the score using
    ``object.__setattr__`` to bypass any custom setters.
    """
    for key, value in state.items():
        if not key.startswith("_"):
            object.__setattr__(score, key, value)


class CheckpointHooks(CadenceHooks):
    """Hooks that checkpoint score state after each successful measure.

    On resume (same ``run_id``), restores the score from the last
    checkpoint and exposes ``completed_measures`` so the cadence
    can skip already-completed steps.

    Use via ``Cadence.with_checkpoint(store, run_id)``.
    """

    def __init__(self, store: CheckpointStore, run_id: str) -> None:
        self._store = store
        self._run_id = run_id
        self._cadence_name: str = ""
        self._measure_index: int = 0
        self._completed: set[str] = set()

    @property
    def completed_measures(self) -> set[str]:
        """Measure names that completed in a previous run."""
        return self._completed

    @property
    def run_id(self) -> str:
        return self._run_id

    async def before_cadence(self, cadence_name: str, score: ScoreT) -> None:
        self._cadence_name = cadence_name
        self._measure_index = 0
        self._completed = await self._store.get_completed_measures(
            cadence_name, self._run_id,
        )
        # Restore score state if resuming
        if self._completed:
            last_state = await self._store.get_last_score_state(
                cadence_name, self._run_id,
            )
            if last_state is not None:
                restore_score(score, last_state)

    async def after_note(
        self,
        note_name: str,
        score: ScoreT,
        duration: float,
        error: Exception | None = None,
    ) -> None:
        if error is None:
            self._measure_index += 1
            await self._store.save_checkpoint(
                self._cadence_name,
                self._run_id,
                note_name,
                self._measure_index,
                serialize_score(score),
            )

    async def after_cadence(
        self,
        cadence_name: str,
        score: ScoreT,
        duration: float,
        error: Exception | None = None,
    ) -> None:
        if error is None:
            # Clear checkpoints on successful completion
            await self._store.clear_checkpoints(cadence_name, self._run_id)
