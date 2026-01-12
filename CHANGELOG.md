# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **BREAKING**: Complete API rename from ServiceFlow to Cadence
  - Package renamed from `serviceflow` to `cadence`
  - `Flow` class renamed to `Cadence`
  - `State` base class renamed to `Context`
  - `ImmutableState` renamed to `ImmutableContext`
  - `@step` decorator renamed to `@beat`
  - `.next()` method renamed to `.then()`
  - `.parallel()` method renamed to `.sync()`
  - `.branch()` method renamed to `.split()`
  - `FlowError` renamed to `CadenceError`
  - `StepError` renamed to `BeatError`
  - `FlowHooks` renamed to `CadenceHooks`
  - `FlowRouter` renamed to `CadenceRouter` (FastAPI)
  - `FlowBlueprint` renamed to `CadenceBlueprint` (Flask)
  - CLI command renamed from `serviceflow` to `cadence`

## [0.3.0] - 2025-01-10

### Added

- **Flask Integration**: New `CadenceBlueprint` for seamless Flask integration
- **Diagram Generation**: Generate Mermaid and DOT/Graphviz cadence diagrams
  - `cadence.to_mermaid()` and `cadence.to_dot()` methods
  - `cadence.to_svg()` for rendered diagrams (requires graphviz)
  - `cadence.save_diagram()` for file export
- **CLI Tool**: New `cadence` command-line interface
  - `cadence init` - Scaffold a new project
  - `cadence new cadence <name>` - Generate cadence templates
  - `cadence new beat <name>` - Generate beat templates with resilience options
  - `cadence diagram <module:cadence>` - Generate cadence diagrams
  - `cadence validate <module>` - Validate cadence definitions
- **Hooks System**: Extensible middleware for cadence and beat lifecycle
  - `LoggingHooks` - Automatic structured logging
  - `TimingHooks` - Performance tracking
  - `MetricsHooks` - Aggregate metrics collection
  - `TracingHooks` - Distributed tracing support
  - `DebugHooks` - Detailed debugging output
- **Reporters**: Pluggable observability backends
  - Console reporter with human-readable output
  - JSON reporter for structured logging
  - Prometheus reporter for metrics export
  - OpenTelemetry reporter for distributed tracing
- **Child Cadence Composition**: Nest cadences within cadences using `.child()`

### Changed

- Improved context merge strategies with better conflict detection
- Enhanced error messages with more context

### Fixed

- Context isolation in deeply nested parallel branches

## [0.2.0] - 2025-01-05

### Added

- **Resilience Decorators**: Production-ready resilience patterns
  - `@retry` - Configurable retry with exponential/linear backoff
  - `@timeout` - Time limits on beat execution
  - `@fallback` - Default values on failure
  - `@circuit_breaker` - Prevent cascading failures
- **FastAPI Integration**: New `cadence_endpoint()` and `CadenceRoute` helpers
- **Parallel Execution**: Smart context merging with configurable strategies
  - `last_write_wins` - Latest change wins (default)
  - `fail_on_conflict` - Raise error on conflicts
  - `smart_merge` - Intelligent type-aware merging
- **AtomicList and AtomicDict**: Thread-safe collections for concurrent access
- **ImmutableContext**: Functional programming style with `evolve()` method

### Changed

- Context now uses copy-on-write semantics for parallel safety
- Beats can now be both sync and async functions

## [0.1.0] - 2024-12-20

### Added

- Initial release of Cadence
- **Core Cadence API**: Fluent builder pattern for composing beats
  - `.then()` - Sequential execution
  - `.sync()` - Concurrent execution
  - `.sequence()` - Sequential list of beats
  - `.split()` - Conditional branching
- **Context Management**: Dataclass-based context container
- **Beat Decorator**: `@beat` for marking functions as cadence beats
- **Result Type**: `Ok` and `Err` for explicit error handling
- **Custom Exceptions**: `CadenceError`, `BeatError`, `TimeoutError`, `RetryExhaustedError`
- Basic test suite with pytest and pytest-asyncio

[Unreleased]: https://github.com/mauhpr/cadence/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/mauhpr/cadence/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/mauhpr/cadence/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/mauhpr/cadence/releases/tag/v0.1.0
