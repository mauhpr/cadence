"""Tests for persistence/checkpointing.

Tests cover:
- Checkpoints saved after each successful measure
- Resume from checkpoint skips completed measures
- Score state restored on resume
- Successful completion clears checkpoints
- Serialization round-trip
- Edge cases
"""

from dataclasses import dataclass
from typing import Optional

import pytest

from cadence import Cadence, Score, note
from cadence.checkpoint import (
    CheckpointHooks,
    InMemoryCheckpointStore,
    restore_score,
    serialize_score,
)


@dataclass
class CheckpointTestScore(Score):
    """Score for checkpoint tests."""

    step1_done: bool = False
    step2_done: bool = False
    step3_done: bool = False
    value: Optional[str] = None
    items: Optional[list[str]] = None


# Track which notes actually executed
execution_log: list[str] = []


@note
async def step1(score: CheckpointTestScore) -> None:
    execution_log.append("step1")
    score.step1_done = True
    score.value = "after_step1"


@note
async def step2(score: CheckpointTestScore) -> None:
    execution_log.append("step2")
    score.step2_done = True
    score.value = "after_step2"


@note
async def step3(score: CheckpointTestScore) -> None:
    execution_log.append("step3")
    score.step3_done = True
    score.value = "after_step3"


@note
async def failing_step(score: CheckpointTestScore) -> None:
    execution_log.append("failing_step")
    raise RuntimeError("crash")


@pytest.fixture(autouse=True)
def clear_log() -> None:
    execution_log.clear()


class TestCheckpointStore:
    """Test InMemoryCheckpointStore behavior."""

    @pytest.mark.asyncio
    async def test_save_and_retrieve(self) -> None:
        store = InMemoryCheckpointStore()
        await store.save_checkpoint("cad", "run1", "step1", 0, {"val": 1})
        await store.save_checkpoint("cad", "run1", "step2", 1, {"val": 2})

        completed = await store.get_completed_measures("cad", "run1")
        assert completed == {"step1", "step2"}

        last = await store.get_last_score_state("cad", "run1")
        assert last == {"val": 2}

    @pytest.mark.asyncio
    async def test_clear(self) -> None:
        store = InMemoryCheckpointStore()
        await store.save_checkpoint("cad", "run1", "step1", 0, {"val": 1})
        await store.clear_checkpoints("cad", "run1")

        completed = await store.get_completed_measures("cad", "run1")
        assert completed == set()

    @pytest.mark.asyncio
    async def test_missing_run_returns_empty(self) -> None:
        store = InMemoryCheckpointStore()
        completed = await store.get_completed_measures("cad", "nonexistent")
        assert completed == set()

        state = await store.get_last_score_state("cad", "nonexistent")
        assert state is None


class TestSerializeScore:
    """Test score serialization and restoration."""

    def test_serialize_dataclass_score(self) -> None:
        score = CheckpointTestScore(step1_done=True, value="hello", items=["a", "b"])
        score.__post_init__()
        result = serialize_score(score)
        assert result["step1_done"] is True
        assert result["value"] == "hello"
        assert result["items"] == ["a", "b"]

    def test_restore_score(self) -> None:
        score = CheckpointTestScore()
        score.__post_init__()
        restore_score(score, {"step1_done": True, "value": "restored"})
        assert score.step1_done is True
        assert score.value == "restored"

    def test_roundtrip(self) -> None:
        original = CheckpointTestScore(
            step1_done=True, value="test", items=["x", "y"],
        )
        original.__post_init__()

        state = serialize_score(original)

        restored = CheckpointTestScore()
        restored.__post_init__()
        restore_score(restored, state)

        assert restored.step1_done == original.step1_done
        assert restored.value == original.value
        assert restored.items == original.items


class TestCheckpointIntegration:
    """Test checkpointing with full cadence execution."""

    @pytest.mark.asyncio
    async def test_full_run_creates_checkpoints(self) -> None:
        store = InMemoryCheckpointStore()
        score = CheckpointTestScore()
        score.__post_init__()

        await (
            Cadence("test", score)
            .with_checkpoint(store, run_id="run1")
            .then("step1", step1)
            .then("step2", step2)
            .run()
        )

        assert execution_log == ["step1", "step2"]
        assert score.step2_done is True

        # Checkpoints should be cleared on success
        completed = await store.get_completed_measures("test", "run1")
        assert completed == set()

    @pytest.mark.asyncio
    async def test_resume_skips_completed_measures(self) -> None:
        store = InMemoryCheckpointStore()

        # Simulate a prior partial run: step1 completed, then crashed
        await store.save_checkpoint(
            "test", "run1", "step1", 0,
            {"step1_done": True, "step2_done": False, "step3_done": False,
             "value": "after_step1", "items": None},
        )

        score = CheckpointTestScore()
        score.__post_init__()

        await (
            Cadence("test", score)
            .with_checkpoint(store, run_id="run1")
            .then("step1", step1)
            .then("step2", step2)
            .then("step3", step3)
            .run()
        )

        # step1 should have been skipped
        assert "step1" not in execution_log
        assert "step2" in execution_log
        assert "step3" in execution_log

    @pytest.mark.asyncio
    async def test_score_restored_on_resume(self) -> None:
        store = InMemoryCheckpointStore()

        # Simulate prior run with score state
        await store.save_checkpoint(
            "test", "run1", "step1", 0,
            {"step1_done": True, "step2_done": False, "step3_done": False,
             "value": "after_step1", "items": ["saved"]},
        )

        score = CheckpointTestScore()
        score.__post_init__()

        await (
            Cadence("test", score)
            .with_checkpoint(store, run_id="run1")
            .then("step1", step1)
            .then("step2", step2)
            .run()
        )

        # Score should reflect restored state + step2 execution
        assert score.step1_done is True
        assert score.value == "after_step2"  # step2 overwrote
        assert score.items == ["saved"]  # restored, not overwritten by step2

    @pytest.mark.asyncio
    async def test_crash_preserves_checkpoints(self) -> None:
        store = InMemoryCheckpointStore()
        score = CheckpointTestScore()
        score.__post_init__()

        with pytest.raises(Exception):
            await (
                Cadence("test", score)
                .with_checkpoint(store, run_id="run1")
                .then("step1", step1)
                .then("failing", failing_step)
                .then("step3", step3)
                .run()
            )

        # step1 checkpoint should be preserved (cadence failed, not cleared)
        completed = await store.get_completed_measures("test", "run1")
        assert "step1" in completed

        # step3 should not have run
        assert "step3" not in execution_log

    @pytest.mark.asyncio
    async def test_all_completed_cadence(self) -> None:
        """Edge case: all measures already completed."""
        store = InMemoryCheckpointStore()
        await store.save_checkpoint(
            "test", "run1", "step1", 0,
            {"step1_done": True, "step2_done": True, "step3_done": False,
             "value": "done", "items": None},
        )
        await store.save_checkpoint(
            "test", "run1", "step2", 1,
            {"step1_done": True, "step2_done": True, "step3_done": False,
             "value": "done", "items": None},
        )

        score = CheckpointTestScore()
        score.__post_init__()

        await (
            Cadence("test", score)
            .with_checkpoint(store, run_id="run1")
            .then("step1", step1)
            .then("step2", step2)
            .run()
        )

        # Nothing should have executed
        assert execution_log == []
        # Score restored from last checkpoint
        assert score.value == "done"

    @pytest.mark.asyncio
    async def test_different_run_ids_are_independent(self) -> None:
        store = InMemoryCheckpointStore()

        # Run 1 completes step1
        await store.save_checkpoint(
            "test", "run1", "step1", 0,
            {"step1_done": True, "step2_done": False, "step3_done": False,
             "value": "run1", "items": None},
        )

        # Run 2 starts fresh
        score = CheckpointTestScore()
        score.__post_init__()

        await (
            Cadence("test", score)
            .with_checkpoint(store, run_id="run2")
            .then("step1", step1)
            .run()
        )

        # step1 should have executed (different run_id)
        assert "step1" in execution_log

    @pytest.mark.asyncio
    async def test_checkpoint_with_sync_parallel(self) -> None:
        """Checkpoint works with .sync() parallel measures."""
        store = InMemoryCheckpointStore()

        @note
        async def par_a(score: CheckpointTestScore) -> None:
            execution_log.append("par_a")
            score.step1_done = True

        @note
        async def par_b(score: CheckpointTestScore) -> None:
            execution_log.append("par_b")
            score.step2_done = True

        # First run: parallel group completes, then crashes
        score = CheckpointTestScore()
        score.__post_init__()

        with pytest.raises(Exception):
            await (
                Cadence("test", score)
                .with_checkpoint(store, run_id="run1")
                .sync("parallel_group", [par_a, par_b])
                .then("failing", failing_step)
                .run()
            )

        completed = await store.get_completed_measures("test", "run1")
        assert "parallel_group" in completed

        # Resume: parallel group should be skipped
        execution_log.clear()
        score2 = CheckpointTestScore()
        score2.__post_init__()

        with pytest.raises(Exception):
            await (
                Cadence("test", score2)
                .with_checkpoint(store, run_id="run1")
                .sync("parallel_group", [par_a, par_b])
                .then("failing", failing_step)
                .run()
            )

        # par_a, par_b should NOT have executed again
        assert "par_a" not in execution_log
        assert "par_b" not in execution_log

    @pytest.mark.asyncio
    async def test_double_with_checkpoint_raises(self) -> None:
        """Calling with_checkpoint() twice raises CadenceError."""
        from cadence.exceptions import CadenceError

        store = InMemoryCheckpointStore()
        score = CheckpointTestScore()
        score.__post_init__()

        with pytest.raises(CadenceError, match="with_checkpoint.*twice"):
            Cadence("test", score) \
                .with_checkpoint(store, run_id="run1") \
                .with_checkpoint(store, run_id="run2")
