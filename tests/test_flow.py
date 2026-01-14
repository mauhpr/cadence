"""Tests for the core Cadence class."""

import pytest
from dataclasses import dataclass, field
from typing import List, Optional

from cadence import Cadence, Score, note, MergeStrategy


@dataclass
class SampleScore(Score):
    """Test score - renamed to avoid pytest collection warning."""
    value: int = 0
    items: Optional[List[str]] = None


@note
async def increment(score: SampleScore) -> None:
    score.value += 1


@note
async def double(score: SampleScore) -> None:
    score.value *= 2


@note
async def append_a(score: SampleScore) -> None:
    if score.items is None:
        score.items = []
    score.items.append("a")


@note
async def append_b(score: SampleScore) -> None:
    if score.items is None:
        score.items = []
    score.items.append("b")


@note
def is_even(score: SampleScore) -> bool:
    return score.value % 2 == 0


class TestCadenceBasics:
    """Test basic cadence operations."""

    @pytest.mark.asyncio
    async def test_single_note(self):
        """Test cadence with a single note."""
        score = SampleScore(value=1)
        score.__post_init__()  # Initialize locks
        cadence = Cadence("test", score).then("inc", increment)
        result = await cadence.run()
        assert result.value == 2

    @pytest.mark.asyncio
    async def test_chained_notes(self):
        """Test cadence with multiple chained notes."""
        score = SampleScore(value=1)
        score.__post_init__()
        cadence = (
            Cadence("test", score)
            .then("inc", increment)
            .then("double", double)
        )
        result = await cadence.run()
        assert result.value == 4  # (1 + 1) * 2

    @pytest.mark.asyncio
    async def test_sequence(self):
        """Test sequential execution."""
        score = SampleScore()
        score.__post_init__()
        cadence = (
            Cadence("test", score)
            .sequence("seq", [append_a, append_b])
        )
        result = await cadence.run()
        assert result.items == ["a", "b"]

    @pytest.mark.asyncio
    async def test_sync(self):
        """Test parallel execution with smart_merge for list combining."""
        score = SampleScore()
        score.__post_init__()
        cadence = (
            Cadence("test", score)
            .sync("par", [append_a, append_b], merge_strategy=MergeStrategy.smart_merge)
        )
        result = await cadence.run()
        # Both should be present (order may vary with smart_merge)
        assert set(result.items) == {"a", "b"}


class TestBranching:
    """Test conditional branching."""

    @pytest.mark.asyncio
    async def test_split_if_true(self):
        """Test split takes if_true path when condition is true."""
        score = SampleScore(value=2)
        score.__post_init__()
        cadence = (
            Cadence("test", score)
            .split("check",
                condition=is_even,
                if_true=[double],
                if_false=[increment])
        )
        result = await cadence.run()
        assert result.value == 4  # doubled

    @pytest.mark.asyncio
    async def test_split_if_false(self):
        """Test split takes if_false path when condition is false."""
        score = SampleScore(value=3)
        score.__post_init__()
        cadence = (
            Cadence("test", score)
            .split("check",
                condition=is_even,
                if_true=[double],
                if_false=[increment])
        )
        result = await cadence.run()
        assert result.value == 4  # incremented


class TestInterrupt:
    """Test cadence interruption."""

    @pytest.mark.asyncio
    async def test_interrupt_stops_cadence(self):
        """Test that returning True from a note stops the cadence."""
        @note
        async def stop_cadence(score: SampleScore) -> bool:
            return True

        score = SampleScore(value=1)
        score.__post_init__()
        cadence = (
            Cadence("test", score)
            .then("stop", stop_cadence, can_interrupt=True)
            .then("inc", increment)  # Should not run
        )
        result = await cadence.run()
        assert result.value == 1  # increment didn't run


class TestReporter:
    """Test time reporting."""

    @pytest.mark.asyncio
    async def test_reporter_called(self):
        """Test that reporter is called for each note."""
        reports = []

        def reporter(name: str, elapsed: float, score: SampleScore) -> None:
            reports.append(name)

        score = SampleScore()
        score.__post_init__()
        cadence = (
            Cadence("test", score)
            .with_reporter(reporter)
            .then("note1", increment)
            .then("note2", double)
        )
        await cadence.run()

        assert "note1" in reports
        assert "note2" in reports
        assert "test:TOTAL" in reports
