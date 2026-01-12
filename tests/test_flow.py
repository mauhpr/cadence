"""Tests for the core Cadence class."""

import pytest
from dataclasses import dataclass, field
from typing import List, Optional

from cadence import Cadence, Context, beat, MergeStrategy


@dataclass
class SampleContext(Context):
    """Test context - renamed to avoid pytest collection warning."""
    value: int = 0
    items: Optional[List[str]] = None


@beat
async def increment(ctx: SampleContext) -> None:
    ctx.value += 1


@beat
async def double(ctx: SampleContext) -> None:
    ctx.value *= 2


@beat
async def append_a(ctx: SampleContext) -> None:
    if ctx.items is None:
        ctx.items = []
    ctx.items.append("a")


@beat
async def append_b(ctx: SampleContext) -> None:
    if ctx.items is None:
        ctx.items = []
    ctx.items.append("b")


@beat
def is_even(ctx: SampleContext) -> bool:
    return ctx.value % 2 == 0


class TestCadenceBasics:
    """Test basic cadence operations."""

    @pytest.mark.asyncio
    async def test_single_beat(self):
        """Test cadence with a single beat."""
        ctx = SampleContext(value=1)
        ctx.__post_init__()  # Initialize locks
        cadence = Cadence("test", ctx).then("inc", increment)
        result = await cadence.run()
        assert result.value == 2

    @pytest.mark.asyncio
    async def test_chained_beats(self):
        """Test cadence with multiple chained beats."""
        ctx = SampleContext(value=1)
        ctx.__post_init__()
        cadence = (
            Cadence("test", ctx)
            .then("inc", increment)
            .then("double", double)
        )
        result = await cadence.run()
        assert result.value == 4  # (1 + 1) * 2

    @pytest.mark.asyncio
    async def test_sequence(self):
        """Test sequential execution."""
        ctx = SampleContext()
        ctx.__post_init__()
        cadence = (
            Cadence("test", ctx)
            .sequence("seq", [append_a, append_b])
        )
        result = await cadence.run()
        assert result.items == ["a", "b"]

    @pytest.mark.asyncio
    async def test_sync(self):
        """Test parallel execution with smart_merge for list combining."""
        ctx = SampleContext()
        ctx.__post_init__()
        cadence = (
            Cadence("test", ctx)
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
        ctx = SampleContext(value=2)
        ctx.__post_init__()
        cadence = (
            Cadence("test", ctx)
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
        ctx = SampleContext(value=3)
        ctx.__post_init__()
        cadence = (
            Cadence("test", ctx)
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
        """Test that returning True from a beat stops the cadence."""
        @beat
        async def stop_cadence(ctx: SampleContext) -> bool:
            return True

        ctx = SampleContext(value=1)
        ctx.__post_init__()
        cadence = (
            Cadence("test", ctx)
            .then("stop", stop_cadence, can_interrupt=True)
            .then("inc", increment)  # Should not run
        )
        result = await cadence.run()
        assert result.value == 1  # increment didn't run


class TestReporter:
    """Test time reporting."""

    @pytest.mark.asyncio
    async def test_reporter_called(self):
        """Test that reporter is called for each beat."""
        reports = []

        def reporter(name: str, elapsed: float, ctx: SampleContext) -> None:
            reports.append(name)

        ctx = SampleContext()
        ctx.__post_init__()
        cadence = (
            Cadence("test", ctx)
            .with_reporter(reporter)
            .then("beat1", increment)
            .then("beat2", double)
        )
        await cadence.run()

        assert "beat1" in reports
        assert "beat2" in reports
        assert "test:TOTAL" in reports
