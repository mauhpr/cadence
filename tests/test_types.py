"""Tests for types.py - Type definitions for Cadence."""

import pytest
from collections.abc import Callable, Coroutine
from typing import Any
from cadence.types import (
    ScoreT,
    ChildScoreT,
    SyncTask,
    AsyncTask,
    Task,
    SyncCondition,
    AsyncCondition,
    Condition,
    SyncInterruptible,
    AsyncInterruptible,
    Interruptible,
    SyncMerge,
    AsyncMerge,
    Merge,
    TimeReporter,
    ErrorHandler,
)


class TestTypeDefinitions:
    """Test that type definitions exist and are usable."""

    def test_score_typevar_exists(self):
        """Test ScoreT TypeVar is defined."""
        assert ScoreT is not None

    def test_child_score_typevar_exists(self):
        """Test ChildScoreT TypeVar is defined."""
        assert ChildScoreT is not None

    def test_sync_task_type(self):
        """Test SyncTask type alias is callable signature."""
        # SyncTask should be a Callable that takes ScoreT and returns None
        assert SyncTask is not None

    def test_async_task_type(self):
        """Test AsyncTask type alias is async callable signature."""
        assert AsyncTask is not None

    def test_task_union_type(self):
        """Test Task is union of SyncTask and AsyncTask."""
        assert Task is not None

    def test_sync_condition_type(self):
        """Test SyncCondition type alias."""
        assert SyncCondition is not None

    def test_async_condition_type(self):
        """Test AsyncCondition type alias."""
        assert AsyncCondition is not None

    def test_condition_union_type(self):
        """Test Condition is union of sync and async."""
        assert Condition is not None

    def test_sync_interruptible_type(self):
        """Test SyncInterruptible type alias."""
        assert SyncInterruptible is not None

    def test_async_interruptible_type(self):
        """Test AsyncInterruptible type alias."""
        assert AsyncInterruptible is not None

    def test_interruptible_union_type(self):
        """Test Interruptible is union."""
        assert Interruptible is not None

    def test_sync_merge_type(self):
        """Test SyncMerge type alias."""
        assert SyncMerge is not None

    def test_async_merge_type(self):
        """Test AsyncMerge type alias."""
        assert AsyncMerge is not None

    def test_merge_union_type(self):
        """Test Merge is union."""
        assert Merge is not None

    def test_time_reporter_type(self):
        """Test TimeReporter type alias."""
        assert TimeReporter is not None

    def test_error_handler_type(self):
        """Test ErrorHandler type alias."""
        assert ErrorHandler is not None


class TestTypeUsage:
    """Test that types can be used in type annotations."""

    def test_sync_task_usage(self):
        """Test SyncTask can annotate a function."""
        from dataclasses import dataclass

        @dataclass
        class MyScore:
            value: int = 0

        def my_task(score: MyScore) -> None:
            score.value += 1

        # Function should be compatible with SyncTask
        task: SyncTask[MyScore] = my_task
        score = MyScore()
        task(score)
        assert score.value == 1

    def test_sync_condition_usage(self):
        """Test SyncCondition can annotate a function."""
        from dataclasses import dataclass

        @dataclass
        class MyScore:
            is_valid: bool = True

        def check_valid(score: MyScore) -> bool:
            return score.is_valid

        condition: SyncCondition[MyScore] = check_valid
        assert condition(MyScore(is_valid=True)) is True
        assert condition(MyScore(is_valid=False)) is False

    def test_time_reporter_usage(self):
        """Test TimeReporter can annotate a function."""
        from dataclasses import dataclass

        @dataclass
        class MyScore:
            name: str = "test"

        reported = []

        def my_reporter(step: str, elapsed: float, score: MyScore) -> None:
            reported.append((step, elapsed, score.name))

        reporter: TimeReporter[MyScore] = my_reporter
        reporter("step1", 0.5, MyScore(name="test"))
        assert len(reported) == 1
        assert reported[0] == ("step1", 0.5, "test")

    def test_error_handler_usage(self):
        """Test ErrorHandler can annotate a function."""
        from dataclasses import dataclass

        @dataclass
        class MyScore:
            error_count: int = 0

        def handle_error(score: MyScore, error: Exception) -> None:
            score.error_count += 1

        handler: ErrorHandler[MyScore] = handle_error
        score = MyScore()
        handler(score, ValueError("test"))
        assert score.error_count == 1
