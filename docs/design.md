# Cadence Design Documents

This document describes the architectural decisions and design philosophy behind Cadence.

## Table of Contents

- [Overview](#overview)
- [Design Philosophy](#design-philosophy)
- [Core Concepts](#core-concepts)
- [Architecture](#architecture)
- [Score Management](#score-management)
- [Parallel Execution Model](#parallel-execution-model)
- [Resilience Patterns](#resilience-patterns)
- [Extensibility](#extensibility)

---

## Overview

Cadence is a declarative Python framework for orchestrating service logic. It provides a fluent API for building complex workflows with explicit control flow, resilience patterns, and observability built-in.

### Goals

1. **Clarity** - Make service orchestration logic explicit and readable
2. **Safety** - Provide safe parallel execution with score isolation
3. **Resilience** - Built-in patterns for handling failures gracefully
4. **Observability** - First-class support for logging, metrics, and tracing
5. **Simplicity** - Zero required dependencies, easy to integrate

### Non-Goals

- Distributed workflow orchestration (use Temporal, Airflow for that)
- Long-running background jobs
- Complex DAG scheduling

---

## Design Philosophy

### Explicit Over Implicit

Cadence favors explicit declaration of workflow structure over implicit behavior:

```python
# Explicit: You can see the entire flow structure
cadence = (
    Cadence("checkout", score)
    .then("validate", validate_order)
    .sync("enrich", [fetch_user, fetch_inventory])
    .split("route", is_premium, [priority], [standard])
    .then("finalize", finalize)
)
```

### Composition Over Inheritance

Build complex workflows by composing simple pieces:

```python
# Compose child cadences
main_cadence = (
    Cadence("main", score)
    .child("auth", auth_cadence, merge_auth)
    .child("process", process_cadence, merge_result)
)
```

### Fail Fast, Recover Gracefully

Cadence encourages explicit error handling rather than silent failures:

```python
# Explicit error handling
cadence = (
    Cadence("risky", score)
    .then("attempt", risky_operation)
    .on_error(handle_failure, stop=False)
    .then("cleanup", cleanup)
)
```

---

## Core Concepts

### Cadence

A Cadence represents a sequence of operations (notes) that transform a score. It's the main unit of orchestration.

```
Cadence = Name + Score + [Note1, Note2, ..., NoteN]
```

### Note

A Note is a single unit of work in a cadence. Notes are functions that receive and modify score.

```python
@note
async def process_payment(score: OrderScore) -> None:
    score.payment_status = await charge(score.total)
```

### Score

Score is the shared state that flows through a cadence. It's a mutable dataclass that notes read and modify.

```python
@dataclass
class OrderScore(Score):
    order_id: str
    items: list = None
    total: float = 0.0
```

---

## Architecture

### Component Diagram

```
┌─────────────────────────────────────────────────────────┐
│                        Cadence                          │
│  ┌─────────────────────────────────────────────────┐   │
│  │                   Measures                       │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────────────┐│   │
│  │  │ Single   │ │ Parallel │ │ Branch           ││   │
│  │  │ Measure  │ │ Measure  │ │ Measure          ││   │
│  │  │ • then() │ │ • sync() │ │ • split()        ││   │
│  │  └──────────┘ └──────────┘ └──────────────────┘│   │
│  │  ┌──────────┐ ┌──────────┐                     │   │
│  │  │ Sequence │ │ChildCade │                     │   │
│  │  │ Measure  │ │nceMeasure│                     │   │
│  │  │          │ │          │                     │   │
│  │  │•sequence │ │ • child()│                     │   │
│  │  └──────────┘ └──────────┘                     │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │ HooksManager│  │ Reporter    │  │ErrorHandler │    │
│  └─────────────┘  └─────────────┘  └─────────────┘    │
└─────────────────────────────────────────────────────────┘

┌─────────────────┐  ┌─────────────────┐
│      Score      │  │   Resilience    │
│  ┌───────────┐  │  │  ┌───────────┐  │
│  │ Score     │  │  │  │ @retry    │  │
│  │ Immutable │  │  │  │ @timeout  │  │
│  │ Atomic*   │  │  │  │ @fallback │  │
│  └───────────┘  │  │  │ @circuit  │  │
└─────────────────┘  │  └───────────┘  │
                     └─────────────────┘
```

### Execution Flow

```
1. Cadence.run() called
   │
2. ├─► before_cadence hooks
   │
3. ├─► For each measure:
   │    │
   │    ├─► before_note hooks
   │    │
   │    ├─► Execute measure
   │    │   • SingleMeasure: Run task
   │    │   • ParallelMeasure: Fork, run, merge
   │    │   • BranchMeasure: Evaluate, choose path
   │    │   • ChildCadenceMeasure: Run child, merge
   │    │
   │    ├─► after_note hooks
   │    │
   │    └─► Check for interrupt signal
   │
4. ├─► Report total time
   │
5. └─► after_cadence hooks
```

---

## Score Management

### Mutable Score

The default `Score` class is mutable and designed for straightforward use:

```python
@dataclass
class MyScore(Score):
    value: int = 0

score = MyScore()
score.value = 42  # Direct mutation
```

### Copy-on-Write for Parallel Execution

When running notes in parallel via `.sync()`, Cadence uses copy-on-write semantics:

1. **Snapshot**: Before parallel execution, create a snapshot of the score
2. **Isolate**: Each parallel task gets its own copy
3. **Track**: Track which fields each task modifies
4. **Merge**: After completion, merge changes back to the original

```
Original Score
     │
     ▼
┌─────────┐
│Snapshot │
└─────────┘
     │
     ├──────────┬──────────┐
     ▼          ▼          ▼
  Copy A     Copy B     Copy C
     │          │          │
   Task A    Task B    Task C
     │          │          │
     ▼          ▼          ▼
  Changes   Changes    Changes
     │          │          │
     └──────────┴──────────┘
                │
                ▼
          Merge Strategy
                │
                ▼
          Final Score
```

### Merge Strategies

| Strategy | Behavior |
|----------|----------|
| `fail_on_conflict` | Raise error if multiple tasks modify same field |
| `last_write_wins` | Last task to complete wins |
| `smart_merge` | Merge lists (extend), dicts (update), fail on scalar conflicts |

### Atomic Types

For truly concurrent access (not just parallel notes), use atomic types:

```python
@dataclass
class AggregatorScore(Score):
    results: AtomicList = field(default_factory=AtomicList)
    cache: AtomicDict = field(default_factory=AtomicDict)
```

These use locks internally to ensure thread-safety.

---

## Parallel Execution Model

### Async Tasks

For async tasks, Cadence uses `asyncio.gather()`:

```python
results = await asyncio.gather(
    task_a(score_copy_a),
    task_b(score_copy_b),
    task_c(score_copy_c),
)
```

### Sync Tasks

For sync tasks in a `.sync()` block, Cadence uses `ThreadPoolExecutor`:

```python
with ThreadPoolExecutor() as executor:
    futures = [
        executor.submit(task, score_copy)
        for task, score_copy in zip(tasks, copies)
    ]
    results = [f.result() for f in futures]
```

### Mixed Async/Sync

When mixing async and sync tasks, sync tasks are wrapped in `asyncio.to_thread()`:

```python
await asyncio.gather(
    async_task(score_a),
    asyncio.to_thread(sync_task, score_b),
)
```

---

## Resilience Patterns

### Retry

The `@retry` decorator implements exponential backoff:

```
Attempt 1 → Fail → Wait delay
Attempt 2 → Fail → Wait delay * backoff
Attempt 3 → Fail → Wait delay * backoff²
...
Attempt N → Fail → Raise exception
```

### Circuit Breaker

State machine for fault tolerance:

```
     ┌──────────────────────────────────────┐
     │                                      │
     ▼                                      │
┌─────────┐  failure_threshold  ┌────────┐  │
│ CLOSED  │ ─────────────────► │  OPEN  │  │
└─────────┘                     └────────┘  │
     ▲                              │       │
     │                    recovery_timeout  │
     │                              │       │
     │                              ▼       │
     │                        ┌──────────┐  │
     │      success           │HALF-OPEN │ ─┘
     └─────────────────────── └──────────┘
                                   │
                              failure
                                   │
                                   ▼
                              (back to OPEN)
```

### Timeout

Uses `asyncio.wait_for()` for async tasks and threading for sync tasks.

### Fallback

Catches specified exceptions and returns default value or calls handler.

---

## Extensibility

### Custom Hooks

Implement `CadenceHooks` to intercept execution:

```python
class MyHooks(CadenceHooks):
    async def before_note(self, name, score):
        # Custom logic before each note
        pass
```

### Custom Reporters

Any callable matching the reporter signature:

```python
def my_reporter(note_name: str, elapsed: float, score: Any) -> None:
    # Custom reporting logic
    pass
```

### Custom Merge Strategies

Any callable matching the merge signature:

```python
def my_merge(original: Score, changes: list[dict]) -> None:
    # Custom merge logic
    pass
```

---

## Comparison with Alternatives

| Feature | Cadence | Prefect | Temporal | Raw asyncio |
|---------|---------|---------|----------|-------------|
| In-process | ✓ | ✓ | ✗ | ✓ |
| Distributed | ✗ | ✓ | ✓ | ✗ |
| Zero deps | ✓ | ✗ | ✗ | ✓ |
| Type safety | ✓ | ✓ | ✓ | Manual |
| Resilience | Built-in | Built-in | Built-in | Manual |
| Learning curve | Low | Medium | High | Low |

### When to Use Cadence

✓ In-process service orchestration
✓ API endpoint workflows
✓ Request/response pipelines
✓ Microservice business logic

### When NOT to Use Cadence

✗ Long-running background jobs
✗ Distributed workflows across services
✗ Complex DAG scheduling
✗ Workflow persistence/resumption

---

## Future Directions

- **Workflow Visualization** - Interactive diagram rendering
- **Debugging Tools** - Step-through execution
- **Performance Profiling** - Built-in profiling hooks
- **OpenAPI Integration** - Generate API specs from cadences
