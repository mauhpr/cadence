"""
Parallel Execution Example

This example demonstrates Cadence's parallel execution capabilities:
- Running multiple beats concurrently
- Context isolation between parallel branches
- Merge strategies for combining results
- Atomic collections for safe concurrent access
"""

import asyncio
import random
from dataclasses import dataclass, field

from cadence import (
    Cadence,
    Context,
    beat,
    timeout,
    fallback,
    AtomicList,
    AtomicDict,
    MergeStrategy,
    TimingHooks,
)


# --- Context Definitions ---


@dataclass
class DataAggregationContext(Context):
    """Context for data aggregation from multiple sources."""
    query: str

    # Results from parallel fetches (each beat writes to different field)
    database_results: list[dict] | None = None
    cache_results: list[dict] | None = None
    api_results: list[dict] | None = None
    search_results: list[dict] | None = None

    # Combined results
    total_count: int = 0
    merged_data: list[dict] = field(default_factory=list)


@dataclass
class ConcurrentWriteContext(Context):
    """Context demonstrating safe concurrent writes with AtomicList."""
    task_count: int = 5

    # Atomic collections for safe concurrent access
    results: AtomicList[dict] = field(default_factory=AtomicList)
    errors: AtomicList[str] = field(default_factory=AtomicList)
    metrics: AtomicDict[float] = field(default_factory=AtomicDict)


@dataclass
class MergeStrategyContext(Context):
    """Context demonstrating different merge strategies."""
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


@beat
@timeout(1.0)
async def fetch_database(ctx: DataAggregationContext) -> None:
    """Fetch from database."""
    ctx.database_results = await fetch_from_database(ctx.query)


@beat
@timeout(0.5)
async def fetch_cache(ctx: DataAggregationContext) -> None:
    """Fetch from cache."""
    ctx.cache_results = await fetch_from_cache(ctx.query)


@beat
@timeout(2.0)
@fallback([])
async def fetch_api(ctx: DataAggregationContext) -> None:
    """Fetch from external API (with fallback on failure)."""
    ctx.api_results = await fetch_from_api(ctx.query)


@beat
@timeout(1.5)
@fallback([])
async def fetch_search(ctx: DataAggregationContext) -> None:
    """Fetch from search engine (with fallback on failure)."""
    ctx.search_results = await fetch_from_search(ctx.query)


@beat
def merge_results(ctx: DataAggregationContext) -> None:
    """Merge results from all sources."""
    all_results = []
    for results in [ctx.database_results, ctx.cache_results, ctx.api_results, ctx.search_results]:
        if results:
            all_results.extend(results)

    ctx.merged_data = all_results
    ctx.total_count = len(all_results)


async def demo_basic_parallel():
    """Demonstrate basic parallel execution with separate result fields."""
    print("\n" + "=" * 60)
    print("DEMO 1: Basic Parallel Execution")
    print("=" * 60)
    print("\nFetching data from 4 sources in parallel...")
    print("(Each source writes to a different context field)\n")

    ctx = DataAggregationContext(query="cadence")
    timing = TimingHooks()

    cadence = (
        Cadence("data_aggregation", ctx)
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

    @beat
    async def process_task_1(ctx: ConcurrentWriteContext) -> None:
        await asyncio.sleep(random.uniform(0.01, 0.05))
        ctx.results.append({"task": 1, "value": "result_1"})
        ctx.metrics.set("task_1_time", random.uniform(10, 50))

    @beat
    async def process_task_2(ctx: ConcurrentWriteContext) -> None:
        await asyncio.sleep(random.uniform(0.01, 0.05))
        ctx.results.append({"task": 2, "value": "result_2"})
        ctx.metrics.set("task_2_time", random.uniform(10, 50))

    @beat
    async def process_task_3(ctx: ConcurrentWriteContext) -> None:
        await asyncio.sleep(random.uniform(0.01, 0.05))
        # Simulate an error being logged
        ctx.errors.append("Task 3 had a warning")
        ctx.results.append({"task": 3, "value": "result_3"})
        ctx.metrics.set("task_3_time", random.uniform(10, 50))

    @beat
    async def process_task_4(ctx: ConcurrentWriteContext) -> None:
        await asyncio.sleep(random.uniform(0.01, 0.05))
        ctx.results.append({"task": 4, "value": "result_4"})
        ctx.metrics.set("task_4_time", random.uniform(10, 50))

    @beat
    async def process_task_5(ctx: ConcurrentWriteContext) -> None:
        await asyncio.sleep(random.uniform(0.01, 0.05))
        ctx.results.append({"task": 5, "value": "result_5"})
        ctx.metrics.set("task_5_time", random.uniform(10, 50))

    ctx = ConcurrentWriteContext()

    cadence = (
        Cadence("concurrent_writes", ctx)
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

    @beat
    async def modify_all_a(ctx: MergeStrategyContext) -> None:
        await asyncio.sleep(0.01)
        ctx.counter = 10
        ctx.items.append("from_task_a")
        ctx.metadata["task_a"] = "completed"

    @beat
    async def modify_all_b(ctx: MergeStrategyContext) -> None:
        await asyncio.sleep(0.02)  # Finishes later
        ctx.counter = 20
        ctx.items.append("from_task_b")
        ctx.metadata["task_b"] = "completed"

    ctx1 = MergeStrategyContext()
    cadence1 = (
        Cadence("merge_last_write", ctx1)
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

    @beat
    async def append_list_a(ctx: MergeStrategyContext) -> None:
        await asyncio.sleep(0.01)
        ctx.items.append("from_task_a")
        ctx.metadata["task_a"] = "completed"

    @beat
    async def append_list_b(ctx: MergeStrategyContext) -> None:
        await asyncio.sleep(0.02)
        ctx.items.append("from_task_b")
        ctx.metadata["task_b"] = "completed"

    ctx2 = MergeStrategyContext()
    cadence2 = (
        Cadence("merge_smart", ctx2)
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
    print("\nSequential phases with parallel beats within each phase...\n")

    @dataclass
    class PipelineContext(Context):
        input_data: str
        phase1_results: list[str] = field(default_factory=list)
        phase2_results: list[str] = field(default_factory=list)
        final_result: str = ""

    @beat
    async def phase1_task_a(ctx: PipelineContext) -> None:
        await asyncio.sleep(0.02)
        ctx.phase1_results = ["p1_a_result"]

    @beat
    async def phase1_task_b(ctx: PipelineContext) -> None:
        await asyncio.sleep(0.03)
        ctx.phase1_results = ["p1_b_result"]

    @beat
    async def phase2_task_a(ctx: PipelineContext) -> None:
        await asyncio.sleep(0.02)
        ctx.phase2_results = [f"p2_a({ctx.phase1_results})"]

    @beat
    async def phase2_task_b(ctx: PipelineContext) -> None:
        await asyncio.sleep(0.01)
        ctx.phase2_results = [f"p2_b({ctx.phase1_results})"]

    @beat
    def finalize(ctx: PipelineContext) -> None:
        ctx.final_result = f"Final: {ctx.phase1_results} -> {ctx.phase2_results}"

    ctx = PipelineContext(input_data="initial")
    timing = TimingHooks()

    cadence = (
        Cadence("nested_parallel", ctx)
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
    class ErrorDemoContext(Context):
        successful_tasks: list[str] = field(default_factory=list)
        failed_tasks: list[str] = field(default_factory=list)

    @beat
    async def task_success_1(ctx: ErrorDemoContext) -> None:
        await asyncio.sleep(0.01)
        ctx.successful_tasks = ["task_1"]

    @beat
    @fallback(None)
    async def task_fails(ctx: ErrorDemoContext) -> None:
        await asyncio.sleep(0.02)
        raise ValueError("Simulated failure")

    @beat
    async def task_success_2(ctx: ErrorDemoContext) -> None:
        await asyncio.sleep(0.015)
        ctx.successful_tasks = ["task_2"]

    @beat
    @fallback(None)  # Fallback wraps timeout to catch timeout errors
    @timeout(0.001)  # Will timeout
    async def task_timeout(ctx: ErrorDemoContext) -> None:
        await asyncio.sleep(1.0)  # Too slow

    ctx = ErrorDemoContext()

    cadence = (
        Cadence("error_handling", ctx)
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
