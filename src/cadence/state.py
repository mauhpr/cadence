"""Thread-safe context management for Cadence.

This module provides context containers that work safely in both async and sync
parallel execution contexts using a Copy-on-Write pattern.
"""

from __future__ import annotations

import copy
from collections.abc import Callable, Iterator
from contextvars import ContextVar
from dataclasses import replace
from threading import Lock
from typing import (
    Any,
    Generic,
    TypeVar,
)

T = TypeVar("T")


# Context variable to track mutations during parallel execution
_parallel_mutations: ContextVar[dict[str, Any] | None] = ContextVar(
    "parallel_mutations", default=None
)


class Context:
    """
    Base context container for cadence execution.

    Works with @dataclass to provide easy field definition. In parallel
    execution, uses copy-on-write semantics to avoid race conditions.

    Example:
        from dataclasses import dataclass

        @dataclass
        class OrderContext(Context):
            order_id: str
            items: list = None
            total: float = None

        ctx = OrderContext(order_id="123")
    """

    def __post_init__(self) -> None:
        """Called after dataclass __init__ - initialize tracking."""
        object.__setattr__(self, "_initialized", True)
        object.__setattr__(self, "_original_values", {})

    def _snapshot(self) -> Context:
        """Create a shallow copy for parallel task isolation."""
        # Use copy to preserve the dataclass structure
        snapshot = copy.copy(self)
        # Track original values at snapshot time for conflict detection
        original = {}
        for field in self._get_fields():
            try:
                original[field] = copy.copy(getattr(self, field))
            except AttributeError:
                pass
        object.__setattr__(snapshot, "_original_values", original)
        return snapshot

    def _get_fields(self) -> list[str]:
        """Get all public field names."""
        if hasattr(self, "__dataclass_fields__"):
            return list(self.__dataclass_fields__.keys())
        return [k for k in self.__dict__.keys() if not k.startswith("_")]

    def _get_changes(self) -> dict[str, Any]:
        """Get fields that changed since snapshot."""
        changes = {}
        original = getattr(self, "_original_values", {})
        for field in self._get_fields():
            try:
                current = getattr(self, field)
                if field in original:
                    if current != original[field]:
                        changes[field] = current
                else:
                    # New field
                    changes[field] = current
            except AttributeError:
                pass
        return changes


class MergeConflict(Exception):
    """Raised when parallel tasks modify the same field with different values."""

    def __init__(self, field: str, values: list[Any]):
        self.field = field
        self.values = values
        super().__init__(
            f"Conflict on field '{field}': multiple tasks wrote different values: {values}"
        )


class MergeStrategy:
    """Strategies for merging parallel task results."""

    @staticmethod
    def last_write_wins(
        original: Context,
        snapshots: list[Context],
        changes: list[dict[str, Any]],
    ) -> None:
        """Last snapshot's value wins for each field."""
        for change_set in changes:
            for field, value in change_set.items():
                object.__setattr__(original, field, value)

    @staticmethod
    def fail_on_conflict(
        original: Context,
        snapshots: list[Context],
        changes: list[dict[str, Any]],
    ) -> None:
        """Raise error if same field modified with different values."""
        # Collect all values per field
        field_values: dict[str, list[Any]] = {}
        for change_set in changes:
            for field, value in change_set.items():
                if field not in field_values:
                    field_values[field] = []
                field_values[field].append(value)

        # Check for conflicts
        for field, values in field_values.items():
            unique_values = []
            for v in values:
                if v not in unique_values:
                    unique_values.append(v)
            if len(unique_values) > 1:
                raise MergeConflict(field, unique_values)

        # Apply changes
        for field, values in field_values.items():
            object.__setattr__(original, field, values[-1])

    @staticmethod
    def smart_merge(
        original: Context,
        snapshots: list[Context],
        changes: list[dict[str, Any]],
    ) -> None:
        """
        Smart merge based on field types:
        - Lists: extend with all values
        - Sets: union all values
        - Numbers: sum if all numeric
        - Others: fail on conflict
        """
        field_values: dict[str, list[Any]] = {}
        for change_set in changes:
            for field, value in change_set.items():
                if field not in field_values:
                    field_values[field] = []
                field_values[field].append(value)

        for field, values in field_values.items():
            if len(values) == 1:
                object.__setattr__(original, field, values[0])
                continue

            first = values[0]

            # List: extend
            if isinstance(first, list):
                merged = []
                for v in values:
                    if isinstance(v, list):
                        merged.extend(v)
                    else:
                        merged.append(v)
                object.__setattr__(original, field, merged)

            # Set: union
            elif isinstance(first, set):
                merged = set()
                for v in values:
                    if isinstance(v, set):
                        merged.update(v)
                    else:
                        merged.add(v)
                object.__setattr__(original, field, merged)

            # Dict: merge (later values override)
            elif isinstance(first, dict):
                merged = {}
                for v in values:
                    if isinstance(v, dict):
                        merged.update(v)
                object.__setattr__(original, field, merged)

            # Same value: no conflict
            elif all(v == first for v in values):
                object.__setattr__(original, field, first)

            # Different values: conflict
            else:
                raise MergeConflict(field, values)


def merge_snapshots(
    original: Context,
    snapshots: list[Context],
    strategy: Callable[
        [Context, list[Context], list[dict[str, Any]]], None
    ] = MergeStrategy.fail_on_conflict,
) -> None:
    """
    Merge changes from parallel task snapshots back into original context.

    Args:
        original: The original context to merge into
        snapshots: List of context snapshots from parallel tasks
        strategy: Merge strategy function (default: fail_on_conflict)
    """
    changes = [snapshot._get_changes() for snapshot in snapshots]
    strategy(original, snapshots, changes)


# =============================================================================
# Atomic Wrappers for Thread-Safe Values
# =============================================================================


class Atomic(Generic[T]):
    """
    Thread-safe atomic value wrapper.

    Use for values that need concurrent access from multiple parallel tasks.

    Example:
        @dataclass
        class MyContext(Context):
            counter: Atomic[int] = field(default_factory=lambda: Atomic(0))

        # In parallel tasks:
        ctx.counter.update(lambda x: x + 1)  # Thread-safe increment
    """

    def __init__(self, value: T) -> None:
        self._value = value
        self._lock = Lock()

    def get(self) -> T:
        """Get the current value (thread-safe read)."""
        with self._lock:
            return self._value

    def set(self, value: T) -> None:
        """Set a new value (thread-safe write)."""
        with self._lock:
            self._value = value

    def update(self, fn: Callable[[T], T]) -> T:
        """
        Atomically update the value using a function.

        Args:
            fn: Function that takes current value and returns new value

        Returns:
            The new value
        """
        with self._lock:
            self._value = fn(self._value)
            return self._value

    def compare_and_swap(self, expected: T, new_value: T) -> bool:
        """
        Atomically set value if current value equals expected.

        Args:
            expected: The expected current value
            new_value: The value to set if current equals expected

        Returns:
            True if swap occurred, False otherwise
        """
        with self._lock:
            if self._value == expected:
                self._value = new_value
                return True
            return False

    def __repr__(self) -> str:
        return f"Atomic({self._value!r})"


class AtomicList(Generic[T]):
    """
    Thread-safe list wrapper with atomic operations.

    Example:
        @dataclass
        class MyContext(Context):
            errors: AtomicList[str] = field(default_factory=AtomicList)

        # In parallel tasks:
        ctx.errors.append("Error from task A")  # Thread-safe
    """

    def __init__(self, initial: list[T] | None = None) -> None:
        self._list: list[T] = list(initial) if initial else []
        self._lock = Lock()

    def append(self, item: T) -> None:
        """Thread-safe append."""
        with self._lock:
            self._list.append(item)

    def extend(self, items: list[T]) -> None:
        """Thread-safe extend."""
        with self._lock:
            self._list.extend(items)

    def get_all(self) -> list[T]:
        """Get a copy of all items."""
        with self._lock:
            return list(self._list)

    def clear(self) -> list[T]:
        """Clear and return all items."""
        with self._lock:
            items = self._list
            self._list = []
            return items

    def __len__(self) -> int:
        with self._lock:
            return len(self._list)

    def __iter__(self) -> Iterator[T]:
        # Return iterator over copy to avoid lock during iteration
        return iter(self.get_all())

    def __repr__(self) -> str:
        return f"AtomicList({self._list!r})"


class AtomicDict(Generic[T]):
    """
    Thread-safe dictionary wrapper with atomic operations.

    Example:
        @dataclass
        class MyContext(Context):
            cache: AtomicDict[str] = field(default_factory=AtomicDict)

        # In parallel tasks:
        ctx.cache.set("key", "value")  # Thread-safe
    """

    def __init__(self, initial: dict[str, T] | None = None) -> None:
        self._dict: dict[str, T] = dict(initial) if initial else {}
        self._lock = Lock()

    def get(self, key: str, default: T | None = None) -> T | None:
        """Thread-safe get."""
        with self._lock:
            return self._dict.get(key, default)

    def set(self, key: str, value: T) -> None:
        """Thread-safe set."""
        with self._lock:
            self._dict[key] = value

    def update(self, items: dict[str, T]) -> None:
        """Thread-safe update."""
        with self._lock:
            self._dict.update(items)

    def pop(self, key: str, default: T | None = None) -> T | None:
        """Thread-safe pop."""
        with self._lock:
            return self._dict.pop(key, default)

    def get_all(self) -> dict[str, T]:
        """Get a copy of all items."""
        with self._lock:
            return dict(self._dict)

    def __contains__(self, key: str) -> bool:
        with self._lock:
            return key in self._dict

    def __len__(self) -> int:
        with self._lock:
            return len(self._dict)

    def __repr__(self) -> str:
        return f"AtomicDict({self._dict!r})"


# =============================================================================
# Immutable Context (Functional Style)
# =============================================================================


class ImmutableContext:
    """
    Base class for immutable context using frozen dataclasses.

    Each beat returns a new context instance instead of mutating.
    Use with @dataclass(frozen=True).

    Example:
        from dataclasses import dataclass

        @dataclass(frozen=True)
        class PureContext(ImmutableContext):
            value: int = 0
            items: tuple = ()

        @beat
        def increment(ctx: PureContext) -> PureContext:
            return ctx.replace(value=ctx.value + 1)
    """

    def replace(self, **changes: Any) -> ImmutableContext:
        """Create a new instance with specified fields replaced."""
        return replace(self, **changes)

    def with_field(self, field: str, value: Any) -> ImmutableContext:
        """Create a new instance with one field replaced."""
        return replace(self, **{field: value})
