"""
Parallel Execution Example

This example demonstrates Cadence's parallel execution capabilities:
- Running multiple notes concurrently
- Score isolation between parallel branches
- Merge strategies for combining results
- Atomic collections for safe concurrent access
"""

import asyncio
import random
from dataclasses import dataclass, field

from cadence import (
    Cadence,
    Score,
    note,
    timeout,
    fallback,
    AtomicList,
    AtomicDict,
    MergeStrategy,
    TimingHooks,
)


# --- Score Definitions ---


@dataclass
class DataAggregationScore(Score):
    """Score for data aggregation from multiple sources."""
    query: str

    # Results from parallel fetches (each note writes to different field)
    database_results: list[dict] | None = None
    cache_results: list[dict] | None = None
    api_results: list[dict] | None = None
    search_results: list[dict] | None = None

    # Combined results
    total_count: int = 0
    merged_data: list[dict] = field(default_factory=list)


@dataclass
class ConcurrentWriteScore(Score):
    """Score demonstrating safe concurrent writes with AtomicList."""
    task_count: int = 5

    # Atomic collections for safe concurrent access
    results: AtomicList[dict] = field(default_factory=AtomicList)
    errors: AtomicList[str] = field(default_factory=AtomicList)
    metrics: AtomicDict[float] = field(default_factory=AtomicDict)


@dataclass
class MergeStrategyScore(Score):
    """Score demonstrating different merge strategies."""
    # These will be modified by parallel tasks
    counter: int = 0
    items: list[str] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)


# --- Mock Data Sources ---


async def fetch_from_database(query: str) -> list[dict]:
    """Simulate database query."""
    await asyncio.sleep(random.uniform(0.05, 0.1))
    return [
        {"id": 1, "source": "database", "data": f"db_result_1 for {query}"},
        {"id": 2, "source": "database", "data": f"db_result_2 for {query}"},
    ]


async def fetch_from_cache(query: str) -> list[dict]:
    """Simulate cache lookup."""
    await asyncio.sleep(random.uniform(0.01, 0.03))
    return [
        {"id": 3, "source": "cache", "data": f"cached_result for {query}"},
    ]


async def fetch_from_api(query: str) -> list[dict]:
    """Simulate external API call."""
    await asyncio.sleep(random.uniform(0.08, 0.15))
    return [
        {"id": 4, "source": "api", "data": f"api_result_1 for {query}"},
        {"id": 5, "source": "api", "data": f"api_result_2 for {query}"},
    ]


async def fetch_from_search(query: str) -> list[dict]:
    """Simulate search engine query."""
    await asyncio.sleep(random.uniform(0.06, 0.12))
    return [
        {"id": 6, "source": "search", "data": f"search_result for {query}"},
    ]


# --- Example 1: Basic Parallel Execution ---


@note
@timeout(1.0)
async def fetch_database(score: DataAggregationScore) -> None:
    """Fetch from database."""
    score.database_results = await fetch_from_database(score.query)


@note
@timeout(0.5)
async def fetch_cache(score: DataAggregationScore) -> None:
    """Fetch from cache."""
    score.cache_results = await fetch_from_cache(score.query)


@note
@timeout(2.0)
@fallback([])
async def fetch_api(score: DataAggregationScore) -> None:
    """Fetch from external API (with fallback on failure)."""
    score.api_results = await fetch_from_api(score.query)


@note
@timeout(1.5)
@fallback([])
async def fetch_search(score: DataAggregationScore) -> None:
    """Fetch from search engine (with fallback on failure)."""
    score.search_results = await fetch_from_search(score.query)


@note
def merge_results(score: DataAggregationScore) -> None:
    """Merge results from all sources."""
    all_results = []
    for results in [score.database_results, score.cache_results, score.api_results, score.search_results]:
        if results:
            all_results.extend(results)

    score.merged_data = all_results
    score.total_count = len(all_results)


async def demo_basic_parallel():
    """Demonstrate basic parallel execution with separate result fields."""
    print("\n" + "=" * 60)
    print("DEMO 1: Basic Parallel Execution")
    print("=" * 60)
    print("\nFetching data from 4 sources in parallel...")
    print("(Each source writes to a different score field)\n")

    score = DataAggregationScore(query="cadence")
    timing = TimingHooks()

    cadence = (
        Cadence("data_aggregation", score)
        .with_hooks(timing)
        .sync("fetch_all", [
            fetch_database,
            fetch_cache,
            fetch_api,
            fetch_search,
        ])
        .then("merge", merge_results)
    )

    result = await cadence.run()

    print(f"\nResults by source:")
    print(f"  Database: {len(result.database_results or [])} items")
    print(f"  Cache:    {len(result.cache_results or [])} items")
    print(f"  API:      {len(result.api_results or [])} items")
    print(f"  Search:   {len(result.search_results or [])} items")
    print(f"  Total:    {result.total_count} items")

    print(f"\n{timing.get_report()}")


# --- Example 2: Atomic Collections for Concurrent Writes ---


async def demo_atomic_collections():
    """Demonstrate using AtomicList and AtomicDict for safe concurrent writes."""
    print("\n" + "=" * 60)
    print("DEMO 2: Atomic Collections for Safe Concurrent Writes")
    print("=" * 60)
    print("\nMultiple parallel tasks writing to shared AtomicList and AtomicDict...")

    @note
    async def process_task_1(score: ConcurrentWriteScore) -> None:
        await asyncio.sleep(random.uniform(0.01, 0.05))
        score.results.append({"task": 1, "value": "result_1"})
        score.metrics.set("task_1_time", random.uniform(10, 50))

    @note
    async def process_task_2(score: ConcurrentWriteScore) -> None:
        await asyncio.sleep(random.uniform(0.01, 0.05))
        score.results.append({"task": 2, "value": "result_2"})
        score.metrics.set("task_2_time", random.uniform(10, 50))

    @note
    async def process_task_3(score: ConcurrentWriteScore) -> None:
        await asyncio.sleep(random.uniform(0.01, 0.05))
        # Simulate an error being logged
        score.errors.append("Task 3 had a warning")
        score.results.append({"task": 3, "value": "result_3"})
        score.metrics.set("task_3_time", random.uniform(10, 50))

    @note
    async def process_task_4(score: ConcurrentWriteScore) -> None:
        await asyncio.sleep(random.uniform(0.01, 0.05))
        score.results.append({"task": 4, "value": "result_4"})
        score.metrics.set("task_4_time", random.uniform(10, 50))

    @note
    async def process_task_5(score: ConcurrentWriteScore) -> None:
        await asyncio.sleep(random.uniform(0.01, 0.05))
        score.results.append({"task": 5, "value": "result_5"})
        score.metrics.set("task_5_time", random.uniform(10, 50))

    score = ConcurrentWriteScore()

    cadence = (
        Cadence("concurrent_writes", score)
        .sync("process_all", [
            process_task_1,
            process_task_2,
            process_task_3,
            process_task_4,
            process_task_5,
        ])
    )

    result = await cadence.run()

    print(f"\nResults collected (order may vary due to concurrency):")
    for item in result.results:
        print(f"  Task {item['task']}: {item['value']}")

    print(f"\nMetrics collected:")
    for key, value in result.metrics.get_all().items():
        print(f"  {key}: {value:.2f}ms")

    print(f"\nErrors/Warnings: {list(result.errors)}")


# --- Example 3: Merge Strategies ---


async def demo_merge_strategies():
    """Demonstrate different merge strategies for parallel execution."""
    print("\n" + "=" * 60)
    print("DEMO 3: Merge Strategies")
    print("=" * 60)

    # Strategy 1: last_write_wins (default)
    print("\n--- Strategy: last_write_wins ---")
    print("When multiple tasks modify the same field, last write wins.\n")

    @note
    async def modify_all_a(score: MergeStrategyScore) -> None:
        await asyncio.sleep(0.01)
        score.counter = 10
        score.items.append("from_task_a")
        score.metadata["task_a"] = "completed"

    @note
    async def modify_all_b(score: MergeStrategyScore) -> None:
        await asyncio.sleep(0.02)  # Finishes later
        score.counter = 20
        score.items.append("from_task_b")
        score.metadata["task_b"] = "completed"

    score1 = MergeStrategyScore()
    cadence1 = (
        Cadence("merge_last_write", score1)
        .sync("modify", [modify_all_a, modify_all_b],
              merge_strategy=MergeStrategy.last_write_wins)
    )

    result1 = await cadence1.run()
    print(f"  counter = {result1.counter} (last writer wins)")
    print(f"  items = {result1.items} (last list wins)")
    print(f"  metadata = {result1.metadata}")

    # Strategy 2: smart_merge (with compatible changes)
    print("\n--- Strategy: smart_merge ---")
    print("Lists are concatenated, dicts are merged, scalars must match.\n")

    @note
    async def append_list_a(score: MergeStrategyScore) -> None:
        await asyncio.sleep(0.01)
        score.items.append("from_task_a")
        score.metadata["task_a"] = "completed"

    @note
    async def append_list_b(score: MergeStrategyScore) -> None:
        await asyncio.sleep(0.02)
        score.items.append("from_task_b")
        score.metadata["task_b"] = "completed"

    score2 = MergeStrategyScore()
    cadence2 = (
        Cadence("merge_smart", score2)
        .sync("modify", [append_list_a, append_list_b],
              merge_strategy=MergeStrategy.smart_merge)
    )

    result2 = await cadence2.run()
    print(f"  counter = {result2.counter} (unchanged)")
    print(f"  items = {result2.items} (lists concatenated)")
    print(f"  metadata = {result2.metadata} (dicts merged)")


# --- Example 4: Nested Parallel Execution ---


async def demo_nested_parallel():
    """Demonstrate nested parallel execution patterns."""
    print("\n" + "=" * 60)
    print("DEMO 4: Nested Parallel Execution")
    print("=" * 60)
    print("\nSequential phases with parallel notes within each phase...\n")

    @dataclass
    class PipelineScore(Score):
        input_data: str
        phase1_results: list[str] = field(default_factory=list)
        phase2_results: list[str] = field(default_factory=list)
        final_result: str = ""

    @note
    async def phase1_task_a(score: PipelineScore) -> None:
        await asyncio.sleep(0.02)
        score.phase1_results = ["p1_a_result"]

    @note
    async def phase1_task_b(score: PipelineScore) -> None:
        await asyncio.sleep(0.03)
        score.phase1_results = ["p1_b_result"]

    @note
    async def phase2_task_a(score: PipelineScore) -> None:
        await asyncio.sleep(0.02)
        score.phase2_results = [f"p2_a({score.phase1_results})"]

    @note
    async def phase2_task_b(score: PipelineScore) -> None:
        await asyncio.sleep(0.01)
        score.phase2_results = [f"p2_b({score.phase1_results})"]

    @note
    def finalize(score: PipelineScore) -> None:
        score.final_result = f"Final: {score.phase1_results} -> {score.phase2_results}"

    score = PipelineScore(input_data="initial")
    timing = TimingHooks()

    cadence = (
        Cadence("nested_parallel", score)
        .with_hooks(timing)
        # Phase 1: Two parallel tasks
        .sync("phase1", [phase1_task_a, phase1_task_b],
              merge_strategy=MergeStrategy.smart_merge)
        # Phase 2: Depends on phase 1 results
        .sync("phase2", [phase2_task_a, phase2_task_b],
              merge_strategy=MergeStrategy.smart_merge)
        # Finalize
        .then("finalize", finalize)
    )

    result = await cadence.run()

    print(f"  Phase 1 results: {result.phase1_results}")
    print(f"  Phase 2 results: {result.phase2_results}")
    print(f"  Final: {result.final_result}")
    print(f"\n{timing.get_report()}")


# --- Example 5: Error Handling in Parallel Execution ---


async def demo_parallel_error_handling():
    """Demonstrate error handling in parallel execution."""
    print("\n" + "=" * 60)
    print("DEMO 5: Error Handling in Parallel Execution")
    print("=" * 60)
    print("\nSome parallel tasks succeed, some fail (with fallbacks)...\n")

    @dataclass
    class ErrorDemoScore(Score):
        successful_tasks: list[str] = field(default_factory=list)
        failed_tasks: list[str] = field(default_factory=list)

    @note
    async def task_success_1(score: ErrorDemoScore) -> None:
        await asyncio.sleep(0.01)
        score.successful_tasks = ["task_1"]

    @note
    @fallback(None)
    async def task_fails(score: ErrorDemoScore) -> None:
        await asyncio.sleep(0.02)
        raise ValueError("Simulated failure")

    @note
    async def task_success_2(score: ErrorDemoScore) -> None:
        await asyncio.sleep(0.015)
        score.successful_tasks = ["task_2"]

    @note
    @fallback(None)  # Fallback wraps timeout to catch timeout errors
    @timeout(0.001)  # Will timeout
    async def task_timeout(score: ErrorDemoScore) -> None:
        await asyncio.sleep(1.0)  # Too slow

    score = ErrorDemoScore()

    cadence = (
        Cadence("error_handling", score)
        .sync("all_tasks", [
            task_success_1,
            task_fails,
            task_success_2,
            task_timeout,
        ], merge_strategy=MergeStrategy.smart_merge)
    )

    result = await cadence.run()

    print(f"  Successful tasks: {result.successful_tasks}")
    print("  (Failed tasks gracefully handled with @fallback)")
    print("\n✓ Cadence completed despite individual task failures")


# --- Main ---


async def main():
    print("Cadence Parallel Execution Demo")
    print("=" * 60)

    await demo_basic_parallel()
    await demo_atomic_collections()
    await demo_merge_strategies()
    await demo_nested_parallel()
    await demo_parallel_error_handling()

    print("\n" + "=" * 60)
    print("✓ All parallel execution demos completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
