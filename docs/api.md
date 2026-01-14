# Cadence API Reference

Complete API documentation for the Cadence framework.

## Table of Contents

- [Core Classes](#core-classes)
  - [Cadence](#cadence)
  - [Context](#context)
  - [ImmutableContext](#immutablecontext)
- [Decorators](#decorators)
  - [@beat](#beat)
  - [@retry](#retry)
  - [@timeout](#timeout)
  - [@fallback](#fallback)
  - [@circuit_breaker](#circuit_breaker)
- [Hooks](#hooks)
  - [CadenceHooks](#cadencehooks)
  - [LoggingHooks](#logginghooks)
  - [TimingHooks](#timinghooks)
  - [MetricsHooks](#metricshooks)
  - [TracingHooks](#tracinghooks)
  - [DebugHooks](#debughooks)
- [Reporters](#reporters)
  - [PrometheusReporter](#prometheusreporter)
  - [OpenTelemetryReporter](#opentelemetryreporter)
- [Exceptions](#exceptions)
- [Atomic Types](#atomic-types)
- [Integrations](#integrations)

---

## Core Classes

### Cadence

The main class for building declarative service orchestration.

```python
from cadence import Cadence
```

#### Constructor

```python
Cadence(name: str, context: ContextT)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Human-readable name for the cadence |
| `context` | `ContextT` | Initial context object |

#### Methods

##### `.then(name, task, *, can_interrupt=False)`

Add a single task to the cadence.

```python
cadence.then("fetch_data", fetch_data_task)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Beat name for logging/tracing |
| `task` | `Callable` | Function that receives context |
| `can_interrupt` | `bool` | If `True` and task returns `True`, cadence stops |

**Returns:** `Cadence[ContextT]` (self for chaining)

##### `.sync(name, tasks, *, merge_strategy=MergeStrategy.fail_on_conflict)`

Add multiple tasks to execute in parallel (synchronized).

```python
cadence.sync("enrich", [fetch_user, fetch_prefs, fetch_history])
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Beat name for the parallel group |
| `tasks` | `list[Callable]` | Functions to execute concurrently |
| `merge_strategy` | `Callable` | Strategy for merging parallel context changes |

**Merge Strategies:**
- `MergeStrategy.fail_on_conflict` - Raise error if same field modified (default)
- `MergeStrategy.last_write_wins` - Last completed task wins
- `MergeStrategy.smart_merge` - Intelligently merge lists and dicts

**Returns:** `Cadence[ContextT]`

##### `.split(name, condition, if_true, if_false=None, *, parallel=False)`

Add conditional branching.

```python
cadence.split("route",
    condition=is_premium,
    if_true=[premium_process],
    if_false=[standard_process]
)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Beat name for the branch |
| `condition` | `Callable[[ContextT], bool]` | Function returning bool |
| `if_true` | `list[Callable]` | Tasks to run if condition is True |
| `if_false` | `list[Callable]` | Tasks to run if condition is False |
| `parallel` | `bool` | Execute branch tasks in parallel |

**Returns:** `Cadence[ContextT]`

##### `.child(name, cadence, merge)`

Compose a child cadence.

```python
cadence.child("payment", payment_cadence, merge_payment_result)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Beat name for the child cadence |
| `cadence` | `Cadence[ChildContextT]` | Child cadence to execute |
| `merge` | `Callable[[ContextT, ChildContextT], None]` | Function to merge child context into parent |

**Returns:** `Cadence[ContextT]`

##### `.with_reporter(reporter)`

Add a time reporter for observability.

```python
cadence.with_reporter(my_reporter)
```

The reporter is called after each beat with:
- `beat_name: str` - Name of the beat
- `elapsed: float` - Time in seconds
- `context: ContextT` - Current context

**Returns:** `Cadence[ContextT]`

##### `.with_hooks(hooks)`

Add hooks for intercepting cadence and beat execution.

```python
cadence.with_hooks(LoggingHooks()).with_hooks(TimingHooks())
```

Multiple hooks can be added - they are called in order.

**Returns:** `Cadence[ContextT]`

##### `.on_error(handler, *, stop=True)`

Add an error handler.

```python
cadence.on_error(handle_error, stop=False)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `handler` | `Callable[[ContextT, Exception], Any]` | Error handler function |
| `stop` | `bool` | If `True`, stop cadence on error |

**Returns:** `Cadence[ContextT]`

##### `async .run()`

Execute the cadence asynchronously.

```python
result = await cadence.run()
```

**Returns:** `ContextT` - The final context after all beats complete

**Raises:** `CadenceError` if a beat fails and no error handler is set

##### `.run_sync()`

Execute the cadence synchronously (convenience method).

```python
result = cadence.run_sync()
```

**Returns:** `ContextT`

##### `.get_context()`

Get the current context.

```python
ctx = cadence.get_context()
```

**Returns:** `ContextT`

---

### Context

Base class for mutable context objects.

```python
from cadence import Context
from dataclasses import dataclass

@dataclass
class MyContext(Context):
    user_id: str
    data: dict = None
```

Context provides copy-on-write semantics for parallel execution, ensuring each parallel task gets an isolated copy that is merged back after completion.

---

### ImmutableContext

Base class for immutable (frozen) context objects.

```python
from cadence import ImmutableContext
from dataclasses import dataclass

@dataclass(frozen=True)
class Config(ImmutableContext):
    api_key: str
    timeout: int = 30
```

#### Methods

##### `.replace(**changes)`

Create a new context with specified fields replaced.

```python
new_config = config.replace(timeout=60)
```

##### `.with_field(field, value)`

Create a new context with a single field changed.

```python
new_config = config.with_field("timeout", 60)
```

---

## Decorators

### @beat

Mark a function as a beat (task) in a cadence.

```python
from cadence import beat

@beat
async def process_order(ctx: OrderContext) -> None:
    ctx.status = "processed"
```

The decorator validates the function signature and provides metadata for observability.

---

### @retry

Add automatic retry with exponential backoff.

```python
from cadence import retry

@retry(max_attempts=3, delay=1.0, backoff=2.0, exceptions=(ConnectionError,))
@beat
async def call_api(ctx):
    ctx.data = await api.fetch()
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_attempts` | `int` | `3` | Maximum number of attempts |
| `delay` | `float` | `1.0` | Initial delay between retries (seconds) |
| `backoff` | `float` | `2.0` | Multiplier for delay after each retry |
| `exceptions` | `tuple` | `(Exception,)` | Exception types to retry on |

---

### @timeout

Add execution timeout.

```python
from cadence import timeout

@timeout(seconds=5.0)
@beat
async def slow_operation(ctx):
    ctx.result = await long_task()
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `seconds` | `float` | Maximum execution time |

**Raises:** `TimeoutError` if the operation exceeds the timeout.

---

### @fallback

Provide a fallback value on failure.

```python
from cadence import fallback

@fallback(default={"status": "unknown"})
@beat
async def get_status(ctx):
    ctx.status = await status_service.get()
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `default` | `Any` | Value to return on failure |
| `handler` | `Callable` | Optional function to compute fallback |
| `exceptions` | `tuple` | Exception types to catch |

---

### @circuit_breaker

Add circuit breaker pattern for fault tolerance.

```python
from cadence import circuit_breaker

@circuit_breaker(
    failure_threshold=5,
    recovery_timeout=30.0,
    half_open_max_calls=3
)
@beat
async def call_service(ctx):
    ctx.data = await fragile_service.fetch()
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `failure_threshold` | `int` | `5` | Failures before opening circuit |
| `recovery_timeout` | `float` | `30.0` | Seconds before trying half-open |
| `half_open_max_calls` | `int` | `3` | Test calls in half-open state |
| `exceptions` | `tuple` | `(Exception,)` | Exceptions that count as failures |
| `name` | `str` | `None` | Circuit name (for sharing across functions) |

**Circuit States:**
- **Closed**: Normal operation, requests pass through
- **Open**: Circuit tripped, requests fail immediately
- **Half-Open**: Testing if service recovered

---

## Hooks

### CadenceHooks

Base class for creating custom hooks.

```python
from cadence import CadenceHooks

class MyHooks(CadenceHooks):
    async def before_cadence(self, cadence_name: str, context: ContextT) -> None:
        """Called before cadence execution starts."""
        pass

    async def after_cadence(
        self,
        cadence_name: str,
        context: ContextT,
        duration: float,
        error: Exception | None = None
    ) -> None:
        """Called after cadence execution completes."""
        pass

    async def before_beat(self, beat_name: str, context: ContextT) -> None:
        """Called before each beat executes."""
        pass

    async def after_beat(
        self,
        beat_name: str,
        context: ContextT,
        duration: float,
        error: Exception | None = None
    ) -> None:
        """Called after each beat completes."""
        pass

    async def on_error(
        self,
        beat_name: str,
        context: ContextT,
        error: Exception
    ) -> None:
        """Called when an error occurs."""
        pass
```

### Built-in Hooks

#### LoggingHooks

Logs cadence and beat execution.

```python
from cadence import LoggingHooks

cadence.with_hooks(LoggingHooks(level="INFO"))
```

#### TimingHooks

Records execution timing.

```python
from cadence import TimingHooks

cadence.with_hooks(TimingHooks())
```

#### MetricsHooks

Collects execution metrics.

```python
from cadence import MetricsHooks

hooks = MetricsHooks()
cadence.with_hooks(hooks)

# Access metrics
print(hooks.get_metrics())
```

#### TracingHooks

Adds tracing spans.

```python
from cadence import TracingHooks

cadence.with_hooks(TracingHooks(service_name="my-service"))
```

#### DebugHooks

Detailed debug output.

```python
from cadence import DebugHooks

cadence.with_hooks(DebugHooks(include_context=True))
```

---

## Reporters

### PrometheusReporter

Prometheus metrics reporter.

```python
from cadence.reporters import PrometheusReporter

reporter = PrometheusReporter(prefix="myapp", track_active_flows=True)
cadence.with_reporter(reporter)
```

**Metrics exported:**
- `{prefix}_step_duration_seconds` - Histogram of beat durations
- `{prefix}_step_total` - Counter of beat executions
- `{prefix}_step_errors_total` - Counter of beat errors
- `{prefix}_flow_duration_seconds` - Histogram of cadence durations
- `{prefix}_flow_total` - Counter of cadence executions
- `{prefix}_active_flows` - Gauge of active cadences

### OpenTelemetryReporter

OpenTelemetry tracing reporter.

```python
from cadence.reporters import OpenTelemetryReporter

reporter = OpenTelemetryReporter(
    service_name="my-service",
    include_state=True,
    include_timing=True
)
cadence.with_reporter(reporter)
```

---

## Exceptions

### CadenceError

Base exception for all cadence errors.

```python
from cadence import CadenceError
```

### BeatError

Exception raised when a beat fails.

```python
from cadence import BeatError

try:
    await cadence.run()
except BeatError as e:
    print(f"Beat {e.beat_name} failed: {e}")
    print(f"Original error: {e.original_error}")
```

| Attribute | Type | Description |
|-----------|------|-------------|
| `beat_name` | `str` | Name of the failed beat |
| `original_error` | `Exception` | The underlying exception |

---

## Atomic Types

Thread-safe types for concurrent access.

### AtomicList

```python
from cadence import AtomicList

results = AtomicList()
results.append(item)
results.extend([item1, item2])
results.clear()
```

### AtomicDict

```python
from cadence import AtomicDict

cache = AtomicDict()
cache["key"] = value
cache.update({"a": 1, "b": 2})
value = cache.pop("key", default)
```

---

## Integrations

### FastAPI

```python
from fastapi import FastAPI
from cadence.integrations.fastapi import CadenceRouter

app = FastAPI()
router = CadenceRouter()

@router.cadence("/process/{id}")
async def process(id: str):
    return MyContext(id=id)

app.include_router(router)
```

### Flask

```python
from flask import Flask
from cadence.integrations.flask import CadenceBlueprint

app = Flask(__name__)
bp = CadenceBlueprint("api", __name__)

@bp.cadence_route("/process/<id>")
def process(id):
    return MyContext(id=id)

app.register_blueprint(bp)
```

---

## Diagram Generation

Generate visual representations of cadences.

```python
from cadence import to_mermaid, to_dot, save_diagram

# Mermaid format
mermaid_code = to_mermaid(my_cadence)

# DOT/Graphviz format
dot_code = to_dot(my_cadence)

# Save to file
save_diagram(my_cadence, "diagram.svg", format="svg")
```

---

## CLI Commands

```bash
# Initialize a new project
cadence init <project-name>

# Generate a new cadence
cadence new cadence <name>

# Generate a new beat
cadence new beat <name> [--retry N] [--timeout N] [--fallback]

# Generate diagram
cadence diagram <module:cadence> [--format mermaid|dot|svg|png]

# Validate cadence definitions
cadence validate <module>
```
