# Cadence

[![PyPI version](https://badge.fury.io/py/cadence-flow.svg)](https://badge.fury.io/py/cadence-flow)
[![Python Versions](https://img.shields.io/pypi/pyversions/cadence-flow.svg)](https://pypi.org/project/cadence-flow/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests](https://github.com/mauhpr/cadence/actions/workflows/test.yml/badge.svg)](https://github.com/mauhpr/cadence/actions/workflows/test.yml)
[![codecov](https://codecov.io/gh/mauhpr/cadence/branch/main/graph/badge.svg)](https://codecov.io/gh/mauhpr/cadence)

**A declarative Python framework for building service logic with explicit control flow.**

Cadence lets you build complex service orchestration with a clean, readable API. Define your business logic as composable beats, handle errors gracefully, and scale with confidence.

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
pip install cadence-flow
```

With optional integrations:

```bash
# FastAPI integration
pip install cadence-flow[fastapi]

# Flask integration
pip install cadence-flow[flask]

# OpenTelemetry tracing
pip install cadence-flow[opentelemetry]

# Prometheus metrics
pip install cadence-flow[prometheus]

# All integrations
pip install cadence-flow[all]
```

## Quick Start

```python
from dataclasses import dataclass
from cadence import Cadence, Context, beat

@dataclass
class OrderContext(Context):
    order_id: str
    items: list = None
    total: float = 0.0
    status: str = "pending"

@beat
async def fetch_items(ctx: OrderContext):
    # Fetch order items from database
    ctx.items = await db.get_items(ctx.order_id)

@beat
async def calculate_total(ctx: OrderContext):
    ctx.total = sum(item.price for item in ctx.items)

@beat
async def process_payment(ctx: OrderContext):
    await payment_service.charge(ctx.order_id, ctx.total)
    ctx.status = "paid"

# Build and run the cadence
cadence = (
    Cadence("checkout", OrderContext(order_id="ORD-123"))
    .then("fetch_items", fetch_items)
    .then("calculate_total", calculate_total)
    .then("process_payment", process_payment)
)

result = await cadence.run()
print(f"Order {result.order_id}: {result.status}")
```

## Core Concepts

### Sequential Beats

Execute beats one after another:

```python
cadence = (
    Cadence("process", MyContext())
    .then("beat1", do_first)
    .then("beat2", do_second)
    .then("beat3", do_third)
)
```

### Parallel Execution

Run independent tasks concurrently with automatic context isolation:

```python
cadence = (
    Cadence("enrich", UserContext(user_id="123"))
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
    Cadence("order", OrderContext())
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
payment_cadence = Cadence("payment", PaymentContext())...
shipping_cadence = Cadence("shipping", ShippingContext())...

checkout_cadence = (
    Cadence("checkout", CheckoutContext())
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
@beat
async def call_external_api(ctx):
    response = await http_client.get(ctx.api_url)
    ctx.data = response.json()
```

### Timeout

```python
from cadence import timeout

@timeout(seconds=5.0)
@beat
async def slow_operation(ctx):
    ctx.result = await long_running_task()
```

### Fallback

```python
from cadence import fallback

@fallback(default={"status": "unknown"})
@beat
async def get_status(ctx):
    ctx.status = await status_service.get(ctx.id)
```

### Circuit Breaker

```python
from cadence import circuit_breaker

@circuit_breaker(failure_threshold=5, recovery_timeout=30.0)
@beat
async def call_fragile_service(ctx):
    ctx.data = await fragile_service.fetch()
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
    return OrderContext(order_id=order_id)

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
    return OrderContext(order_id=order_id)

app.register_blueprint(bp)
```

## Observability

### Hooks System

```python
from cadence import Cadence, LoggingHooks, TimingHooks

cadence = (
    Cadence("monitored", MyContext())
    .with_hooks(LoggingHooks())
    .with_hooks(TimingHooks())
    .then("beat1", do_work)
)
```

### Custom Hooks

```python
from cadence import CadenceHooks

class MyHooks(CadenceHooks):
    async def before_beat(self, beat_name, context):
        print(f"Starting: {beat_name}")

    async def after_beat(self, beat_name, context, duration, error=None):
        print(f"Completed: {beat_name} in {duration:.2f}s")

    async def on_error(self, beat_name, context, error):
        alert_team(f"Error in {beat_name}: {error}")
```

### Prometheus Metrics

```python
from cadence.reporters import PrometheusReporter

reporter = PrometheusReporter(prefix="myapp")

cadence = (
    Cadence("tracked", MyContext())
    .with_reporter(reporter.report)
    .then("beat1", do_work)
)
```

### OpenTelemetry Tracing

```python
from cadence.reporters import OpenTelemetryReporter

reporter = OpenTelemetryReporter(service_name="my-service")

cadence = (
    Cadence("traced", MyContext())
    .with_reporter(reporter.report)
    .then("beat1", do_work)
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

# Generate a new beat with resilience decorators
cadence new beat process-payment --retry 3 --timeout 30

# Generate cadence diagram
cadence diagram myapp.cadences:checkout_cadence --format mermaid

# Validate cadence definitions
cadence validate myapp.cadences
```

## Context Management

### Immutable Context

For functional-style cadences:

```python
from cadence import ImmutableContext

@dataclass(frozen=True)
class Config(ImmutableContext):
    api_key: str
    timeout: int = 30

# Create new context with changes
new_config = config.with_field("timeout", 60)
```

### Atomic Operations

Thread-safe context updates for parallel execution:

```python
from cadence import Context, AtomicList, AtomicDict

@dataclass
class AggregatorContext(Context):
    results: AtomicList = None
    cache: AtomicDict = None

    def __post_init__(self):
        super().__post_init__()
        self.results = AtomicList()
        self.cache = AtomicDict()

# Safe concurrent updates
ctx.results.append(new_result)
ctx.cache["key"] = value
```

## Error Handling

```python
from cadence import CadenceError, BeatError

cadence = (
    Cadence("handled", MyContext())
    .then("risky", risky_operation)
    .on_error(handle_error, stop=False)  # Continue on error
    .then("cleanup", cleanup)
)

async def handle_error(context, error):
    if isinstance(error, BeatError):
        logger.error(f"Beat {error.beat_name} failed: {error}")
        context.errors.append(str(error))
```

## Documentation

- [API Reference](https://github.com/mauhpr/cadence/docs)
- [Examples](https://github.com/mauhpr/cadence/tree/main/examples)
- [Design Documents](https://github.com/mauhpr/cadence/tree/main/docs/design)

## Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

## License

Cadence is released under the [MIT License](LICENSE).
