# Cadence

[![PyPI version](https://badge.fury.io/py/cadence-orchestration.svg)](https://badge.fury.io/py/cadence-orchestration)
[![Python Versions](https://img.shields.io/pypi/pyversions/cadence-orchestration.svg)](https://pypi.org/project/cadence-orchestration/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests](https://github.com/mauhpr/cadence/actions/workflows/test.yml/badge.svg)](https://github.com/mauhpr/cadence/actions/workflows/test.yml)
[![codecov](https://codecov.io/gh/mauhpr/cadence/branch/main/graph/badge.svg)](https://codecov.io/gh/mauhpr/cadence)

**A declarative Python framework for building service logic with explicit control flow.**

Cadence lets you build complex service orchestration with a clean, readable API. Define your business logic as composable notes, handle errors gracefully, and scale with confidence.

## Features

- **Declarative Cadence Definition** - Build complex workflows with a fluent, chainable API
- **Parallel Execution** - Run tasks concurrently with automatic context isolation and merging
- **Branching Logic** - Conditional execution paths with clean syntax
- **Resilience Patterns** - Built-in retry, timeout, fallback, and circuit breaker
- **Framework Integration** - First-class support for FastAPI and Flask
- **Observability** - Hooks for logging, metrics, and tracing
- **Type Safety** - Full type hints and generics support
- **Zero Dependencies** - Core library has no required dependencies

## Installation

```bash
pip install cadence-orchestration
```

With optional integrations:

```bash
# FastAPI integration
pip install cadence-orchestration[fastapi]

# Flask integration
pip install cadence-orchestration[flask]

# OpenTelemetry tracing
pip install cadence-orchestration[opentelemetry]

# Prometheus metrics
pip install cadence-orchestration[prometheus]

# All integrations
pip install cadence-orchestration[all]
```

## Quick Start

```python
from dataclasses import dataclass
from cadence import Cadence, Score, note

@dataclass
class OrderScore(Score):
    order_id: str
    items: list = None
    total: float = 0.0
    status: str = "pending"

@note
async def fetch_items(score: OrderScore):
    # Fetch order items from database
    score.items = await db.get_items(score.order_id)

@note
async def calculate_total(score: OrderScore):
    score.total = sum(item.price for item in score.items)

@note
async def process_payment(score: OrderScore):
    await payment_service.charge(score.order_id, score.total)
    score.status = "paid"

# Build and run the cadence
cadence = (
    Cadence("checkout", OrderScore(order_id="ORD-123"))
    .then("fetch_items", fetch_items)
    .then("calculate_total", calculate_total)
    .then("process_payment", process_payment)
)

result = await cadence.run()
print(f"Order {result.order_id}: {result.status}")
```

## Core Concepts

### Sequential Notes

Execute notes one after another:

```python
cadence = (
    Cadence("process", MyScore())
    .then("note1", do_first)
    .then("note2", do_second)
    .then("note3", do_third)
)
```

### Parallel Execution

Run independent tasks concurrently with automatic score isolation:

```python
cadence = (
    Cadence("enrich", UserScore(user_id="123"))
    .sync("fetch_data", [
        fetch_profile,
        fetch_preferences,
        fetch_history,
    ])
    .then("merge_results", combine_data)
)
```

### Conditional Branching

Route execution based on runtime conditions:

```python
cadence = (
    Cadence("order", OrderScore())
    .then("validate", validate_order)
    .split("route",
        condition=is_premium_customer,
        if_true=[priority_processing, express_shipping],
        if_false=[standard_processing, regular_shipping]
    )
    .then("confirm", send_confirmation)
)
```

### Child Cadences

Compose cadences for complex orchestration:

```python
payment_cadence = Cadence("payment", PaymentScore())...
shipping_cadence = Cadence("shipping", ShippingScore())...

checkout_cadence = (
    Cadence("checkout", CheckoutScore())
    .then("prepare", prepare_order)
    .child("process_payment", payment_cadence, merge_payment)
    .child("arrange_shipping", shipping_cadence, merge_shipping)
    .then("complete", finalize_order)
)
```

## Resilience Patterns

### Retry with Backoff

```python
from cadence import retry

@retry(max_attempts=3, delay=1.0, backoff=2.0)
@note
async def call_external_api(score):
    response = await http_client.get(score.api_url)
    score.data = response.json()
```

### Timeout

```python
from cadence import timeout

@timeout(seconds=5.0)
@note
async def slow_operation(score):
    score.result = await long_running_task()
```

### Fallback

```python
from cadence import fallback

@fallback(default={"status": "unknown"})
@note
async def get_status(score):
    score.status = await status_service.get(score.id)
```

### Circuit Breaker

```python
from cadence import circuit_breaker

@circuit_breaker(failure_threshold=5, recovery_timeout=30.0)
@note
async def call_fragile_service(score):
    score.data = await fragile_service.fetch()
```

## Framework Integration

### FastAPI

```python
from fastapi import FastAPI
from cadence.integrations.fastapi import CadenceRouter

app = FastAPI()
router = CadenceRouter()

@router.cadence("/orders/{order_id}", checkout_cadence)
async def create_order(order_id: str):
    return OrderScore(order_id=order_id)

app.include_router(router)
```

### Flask

```python
from flask import Flask
from cadence.integrations.flask import CadenceBlueprint

app = Flask(__name__)
bp = CadenceBlueprint("orders", __name__)

@bp.cadence_route("/orders/<order_id>", checkout_cadence)
def create_order(order_id):
    return OrderScore(order_id=order_id)

app.register_blueprint(bp)
```

## Observability

### Hooks System

```python
from cadence import Cadence, LoggingHooks, TimingHooks

cadence = (
    Cadence("monitored", MyScore())
    .with_hooks(LoggingHooks())
    .with_hooks(TimingHooks())
    .then("note1", do_work)
)
```

### Custom Hooks

```python
from cadence import CadenceHooks

class MyHooks(CadenceHooks):
    async def before_note(self, note_name, score):
        print(f"Starting: {note_name}")

    async def after_note(self, note_name, score, duration, error=None):
        print(f"Completed: {note_name} in {duration:.2f}s")

    async def on_error(self, note_name, score, error):
        alert_team(f"Error in {note_name}: {error}")
```

### Prometheus Metrics

```python
from cadence.reporters import PrometheusReporter

reporter = PrometheusReporter(prefix="myapp")

cadence = (
    Cadence("tracked", MyScore())
    .with_reporter(reporter.report)
    .then("note1", do_work)
)
```

### OpenTelemetry Tracing

```python
from cadence.reporters import OpenTelemetryReporter

reporter = OpenTelemetryReporter(service_name="my-service")

cadence = (
    Cadence("traced", MyScore())
    .with_reporter(reporter.report)
    .then("note1", do_work)
)
```

## Cadence Diagrams

Generate visual diagrams of your cadences:

```python
from cadence import to_mermaid, to_dot

# Generate Mermaid diagram
print(to_mermaid(my_cadence))

# Generate DOT/Graphviz diagram
print(to_dot(my_cadence))
```

## CLI

Cadence includes a CLI for scaffolding and utilities:

```bash
# Initialize a new project
cadence init my-project

# Generate a new cadence
cadence new cadence checkout

# Generate a new note with resilience decorators
cadence new note process-payment --retry 3 --timeout 30

# Generate cadence diagram
cadence diagram myapp.cadences:checkout_cadence --format mermaid

# Validate cadence definitions
cadence validate myapp.cadences
```

## Score Management

### Immutable Score

For functional-style cadences:

```python
from cadence import ImmutableScore

@dataclass(frozen=True)
class Config(ImmutableScore):
    api_key: str
    timeout: int = 30

# Create new score with changes
new_config = config.with_field("timeout", 60)
```

### Atomic Operations

Thread-safe score updates for parallel execution:

```python
from cadence import Score, AtomicList, AtomicDict

@dataclass
class AggregatorScore(Score):
    results: AtomicList = None
    cache: AtomicDict = None

    def __post_init__(self):
        super().__post_init__()
        self.results = AtomicList()
        self.cache = AtomicDict()

# Safe concurrent updates
score.results.append(new_result)
score.cache["key"] = value
```

## Error Handling

```python
from cadence import CadenceError, NoteError

cadence = (
    Cadence("handled", MyScore())
    .then("risky", risky_operation)
    .on_error(handle_error, stop=False)  # Continue on error
    .then("cleanup", cleanup)
)

async def handle_error(score, error):
    if isinstance(error, NoteError):
        logger.error(f"Note {error.note_name} failed: {error}")
        score.errors.append(str(error))
```

## Documentation

- [API Reference](docs/api.md)
- [Design Documents](docs/design.md)
- [Examples](examples/)

## Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

## License

Cadence is released under the [MIT License](LICENSE).
