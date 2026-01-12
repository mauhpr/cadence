"""Tests for Context, Atomic wrappers, and copy-on-write merge."""

import pytest
from dataclasses import dataclass, field
from typing import List, Optional

from cadence import (
    Context,
    ImmutableContext,
    Atomic,
    AtomicList,
    AtomicDict,
    MergeConflict,
    MergeStrategy,
    merge_snapshots,
)


@dataclass
class SampleContext(Context):
    """Test context for copy-on-write tests."""
    name: str = ""
    count: int = 0
    items: Optional[List[str]] = None
    metadata: Optional[dict] = None


class TestContext:
    """Test basic Context functionality."""

    def test_context_initialization(self):
        """Test that Context initializes properly with dataclass."""
        ctx = SampleContext(name="test", count=5)
        ctx.__post_init__()
        assert ctx.name == "test"
        assert ctx.count == 5

    def test_context_mutation(self):
        """Test that Context allows mutation."""
        ctx = SampleContext()
        ctx.__post_init__()
        ctx.name = "updated"
        ctx.count = 10
        assert ctx.name == "updated"
        assert ctx.count == 10


class TestCopyOnWrite:
    """Test copy-on-write snapshot and merge functionality."""

    def test_snapshot_creates_copy(self):
        """Test that _snapshot creates an independent copy."""
        ctx = SampleContext(name="original", count=1)
        ctx.__post_init__()

        snapshot = ctx._snapshot()
        snapshot.name = "modified"
        snapshot.count = 99

        # Original should be unchanged
        assert ctx.name == "original"
        assert ctx.count == 1

    def test_get_changes_detects_modifications(self):
        """Test that _get_changes detects modified fields."""
        ctx = SampleContext(name="original", count=1)
        ctx.__post_init__()

        snapshot = ctx._snapshot()
        snapshot.name = "modified"

        changes = snapshot._get_changes()
        assert "name" in changes
        assert changes["name"] == "modified"
        assert "count" not in changes

    def test_merge_non_conflicting_changes(self):
        """Test merging snapshots with different fields modified."""
        ctx = SampleContext(name="original")
        ctx.__post_init__()

        # Two snapshots modify different fields
        snap1 = ctx._snapshot()
        snap1.name = "task1"

        snap2 = ctx._snapshot()
        snap2.count = 42

        merge_snapshots(ctx, [snap1, snap2])

        assert ctx.name == "task1"
        assert ctx.count == 42

    def test_merge_conflict_detection(self):
        """Test that conflicting modifications raise MergeConflict."""
        ctx = SampleContext()
        ctx.__post_init__()

        snap1 = ctx._snapshot()
        snap1.name = "value1"

        snap2 = ctx._snapshot()
        snap2.name = "value2"

        with pytest.raises(MergeConflict) as exc_info:
            merge_snapshots(ctx, [snap1, snap2])

        assert exc_info.value.field == "name"
        assert "value1" in exc_info.value.values
        assert "value2" in exc_info.value.values

    def test_merge_same_value_no_conflict(self):
        """Test that same value written by multiple tasks doesn't conflict."""
        ctx = SampleContext()
        ctx.__post_init__()

        snap1 = ctx._snapshot()
        snap1.name = "same_value"

        snap2 = ctx._snapshot()
        snap2.name = "same_value"

        # Should not raise
        merge_snapshots(ctx, [snap1, snap2])
        assert ctx.name == "same_value"

    def test_last_write_wins_strategy(self):
        """Test last_write_wins merge strategy."""
        ctx = SampleContext()
        ctx.__post_init__()

        snap1 = ctx._snapshot()
        snap1.name = "first"

        snap2 = ctx._snapshot()
        snap2.name = "second"

        merge_snapshots(ctx, [snap1, snap2], MergeStrategy.last_write_wins)
        assert ctx.name == "second"

    def test_smart_merge_lists(self):
        """Test smart_merge extends lists."""
        ctx = SampleContext()
        ctx.__post_init__()

        snap1 = ctx._snapshot()
        snap1.items = ["a", "b"]

        snap2 = ctx._snapshot()
        snap2.items = ["c", "d"]

        merge_snapshots(ctx, [snap1, snap2], MergeStrategy.smart_merge)
        assert ctx.items == ["a", "b", "c", "d"]

    def test_smart_merge_dicts(self):
        """Test smart_merge merges dicts."""
        ctx = SampleContext()
        ctx.__post_init__()

        snap1 = ctx._snapshot()
        snap1.metadata = {"key1": "value1"}

        snap2 = ctx._snapshot()
        snap2.metadata = {"key2": "value2"}

        merge_snapshots(ctx, [snap1, snap2], MergeStrategy.smart_merge)
        assert ctx.metadata == {"key1": "value1", "key2": "value2"}


class TestAtomic:
    """Test Atomic wrapper for thread-safe values."""

    def test_atomic_get_set(self):
        """Test basic get/set operations."""
        counter = Atomic(0)
        assert counter.get() == 0

        counter.set(10)
        assert counter.get() == 10

    def test_atomic_update(self):
        """Test atomic update operation."""
        counter = Atomic(5)
        result = counter.update(lambda x: x + 3)
        assert result == 8
        assert counter.get() == 8

    def test_atomic_compare_and_swap_success(self):
        """Test CAS when expected value matches."""
        value = Atomic("old")
        success = value.compare_and_swap("old", "new")
        assert success is True
        assert value.get() == "new"

    def test_atomic_compare_and_swap_failure(self):
        """Test CAS when expected value doesn't match."""
        value = Atomic("actual")
        success = value.compare_and_swap("expected", "new")
        assert success is False
        assert value.get() == "actual"


class TestAtomicList:
    """Test AtomicList wrapper."""

    def test_atomic_list_append(self):
        """Test thread-safe append."""
        items = AtomicList()
        items.append("a")
        items.append("b")
        assert items.get_all() == ["a", "b"]

    def test_atomic_list_extend(self):
        """Test thread-safe extend."""
        items = AtomicList(["a"])
        items.extend(["b", "c"])
        assert items.get_all() == ["a", "b", "c"]

    def test_atomic_list_clear(self):
        """Test clear returns items."""
        items = AtomicList(["a", "b"])
        cleared = items.clear()
        assert cleared == ["a", "b"]
        assert items.get_all() == []

    def test_atomic_list_iteration(self):
        """Test iteration over atomic list."""
        items = AtomicList(["x", "y", "z"])
        result = list(items)
        assert result == ["x", "y", "z"]


class TestAtomicDict:
    """Test AtomicDict wrapper."""

    def test_atomic_dict_get_set(self):
        """Test basic get/set operations."""
        cache = AtomicDict()
        cache.set("key", "value")
        assert cache.get("key") == "value"
        assert cache.get("missing") is None
        assert cache.get("missing", "default") == "default"

    def test_atomic_dict_update(self):
        """Test thread-safe update."""
        cache = AtomicDict({"a": 1})
        cache.update({"b": 2, "c": 3})
        assert cache.get_all() == {"a": 1, "b": 2, "c": 3}

    def test_atomic_dict_pop(self):
        """Test thread-safe pop."""
        cache = AtomicDict({"key": "value"})
        result = cache.pop("key")
        assert result == "value"
        assert "key" not in cache

    def test_atomic_dict_contains(self):
        """Test containment check."""
        cache = AtomicDict({"exists": True})
        assert "exists" in cache
        assert "missing" not in cache


class TestImmutableContext:
    """Test ImmutableContext for functional-style cadences."""

    def test_immutable_context_replace(self):
        """Test replace creates new instance."""
        @dataclass(frozen=True)
        class Counter(ImmutableContext):
            value: int = 0

        c1 = Counter(value=5)
        c2 = c1.replace(value=10)

        assert c1.value == 5
        assert c2.value == 10
        assert c1 is not c2

    def test_immutable_context_with_field(self):
        """Test with_field helper."""
        @dataclass(frozen=True)
        class Data(ImmutableContext):
            name: str = ""
            count: int = 0

        d1 = Data(name="test", count=1)
        d2 = d1.with_field("count", 99)

        assert d1.count == 1
        assert d2.count == 99
