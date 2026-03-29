# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.5.0] - 2026-03-28

### Added

- **Event System**: New `EventEmitter` hook and `CadenceEvent` dataclass for structured domain events
  - Register listeners for specific event types (`note.started`, `note.completed`, `note.failed`, `cadence.started`, `cadence.completed`, `cadence.failed`) or use `"*"` wildcard
  - Supports both sync and async listeners with error isolation
  - Compose via `.with_hooks(emitter)` — stackable with other hooks
- **Workflow Checkpointing**: New `CheckpointStore` protocol and `.with_checkpoint()` method for crash recovery
  - On re-run with the same `run_id`, completed measures are skipped and score is restored
  - Includes `InMemoryCheckpointStore` for development/testing
  - Provides `serialize_score()` and `restore_score()` utilities
  - Checkpoints auto-clear on successful cadence completion
- **ParallelNoteError**: New exception for `.sync()` failures with task-level identification
  - Properties: `group_name`, `task_index`, `note_name` (the specific task)
  - Backward-compatible: `except NoteError` still catches parallel errors

## [0.4.3] - 2026-02-19

### Added

- **`field=` parameter for `@fallback`**: Sets fallback value directly on the score attribute, matching how notes mutate state by side-effect

## [0.4.2] - 2025-01-14

### Added

- **Documentation**: Added Windows limitation note for `@timeout` decorator in README
- **Future Directions**: Added Windows sync timeout support to roadmap in `docs/design.md`

## [0.4.1] - 2025-01-14

### Changed

- **Documentation**: Updated `docs/design.md` to accurately reflect current capabilities
  - Added "Current Capabilities" section documenting shipped features (visualization, DebugHooks, TimingHooks)
  - Updated "Future Directions" to list only unimplemented features

### Removed

- Removed completed `plans/` folder (test coverage plan is done)

## [0.4.0] - 2025-01-14

### Added

- **Comprehensive Test Suite**: 309 tests with 77% code coverage
  - Unit tests for all hook classes (LoggingHooks, TimingHooks, MetricsHooks, etc.)
  - Node/Measure tests (SingleMeasure, SequenceMeasure, BranchMeasure, ChildCadenceMeasure)
  - Integration tests for FastAPI and Flask
  - Edge case tests (cancellation, concurrent failures, empty workflows)
  - Reporter tests (console, JSON, Prometheus, OpenTelemetry)
- **Reorganized Examples**: Examples now organized by complexity level
  - `examples/basic/` - Getting started examples
  - `examples/intermediate/` - Branching, parallelism, hooks, child composition
  - `examples/advanced/` - Framework integration, resilience, testing patterns
- **New Examples**:
  - `child_composition.py` - Child cadence composition patterns
  - `testing_workflows.py` - Comprehensive testing patterns and best practices
- **CI/CD Improvements**:
  - GitHub Actions workflow with pip caching and coverage threshold
  - Codecov integration with `.codecov.yml` configuration
  - Coverage reporting with 70% minimum threshold

### Changed

- **BREAKING**: Complete API rename from ServiceFlow to Cadence with musical theme
  - Package renamed from `serviceflow` to `cadence`
  - `Flow` class renamed to `Cadence`
  - `State` base class renamed to `Score`
  - `ImmutableState` renamed to `ImmutableScore`
  - `@step` decorator renamed to `@note`
  - `.next()` method renamed to `.then()`
  - `.parallel()` method renamed to `.sync()`
  - `.branch()` method renamed to `.split()`
  - `FlowError` renamed to `CadenceError`
  - `StepError` renamed to `NoteError`
  - `FlowHooks` renamed to `CadenceHooks`
  - Hook methods: `before_step`/`after_step` renamed to `before_note`/`after_note`
  - Internal: `Node` classes renamed to `Measure` (SingleMeasure, ParallelMeasure, etc.)
  - `FlowRouter` renamed to `CadenceRouter` (FastAPI)
  - `FlowBlueprint` renamed to `CadenceBlueprint` (Flask)
  - CLI command renamed from `serviceflow` to `cadence`
  - CLI: `cadence new beat` renamed to `cadence new note`
  - Internal file renames for consistency:
    - `flow.py` → `cadence.py`
    - `state.py` → `score.py`
    - `step.py` → `note.py`

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
  - `cadence new note <name>` - Generate note templates with resilience options
  - `cadence diagram <module:cadence>` - Generate cadence diagrams
  - `cadence validate <module>` - Validate cadence definitions
- **Hooks System**: Extensible middleware for cadence and note lifecycle
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

- Improved score merge strategies with better conflict detection
- Enhanced error messages with more context

### Fixed

- Score isolation in deeply nested parallel branches

## [0.2.0] - 2025-01-05

### Added

- **Resilience Decorators**: Production-ready resilience patterns
  - `@retry` - Configurable retry with exponential/linear backoff
  - `@timeout` - Time limits on note execution
  - `@fallback` - Default values on failure
  - `@circuit_breaker` - Prevent cascading failures
- **FastAPI Integration**: New `cadence_endpoint()` and `CadenceRoute` helpers
- **Parallel Execution**: Smart score merging with configurable strategies
  - `last_write_wins` - Latest change wins (default)
  - `fail_on_conflict` - Raise error on conflicts
  - `smart_merge` - Intelligent type-aware merging
- **AtomicList and AtomicDict**: Thread-safe collections for concurrent access
- **ImmutableScore**: Functional programming style with `evolve()` method

### Changed

- Score now uses copy-on-write semantics for parallel safety
- Notes can now be both sync and async functions

## [0.1.0] - 2024-12-20

### Added

- Initial release of Cadence
- **Core Cadence API**: Fluent builder pattern for composing notes
  - `.then()` - Sequential execution
  - `.sync()` - Concurrent execution
  - `.sequence()` - Sequential list of notes
  - `.split()` - Conditional branching
- **Score Management**: Dataclass-based score container
- **Note Decorator**: `@note` for marking functions as cadence notes
- **Result Type**: `Ok` and `Err` for explicit error handling
- **Custom Exceptions**: `CadenceError`, `NoteError`, `TimeoutError`, `RetryExhaustedError`
- Basic test suite with pytest and pytest-asyncio

[Unreleased]: https://github.com/mauhpr/cadence/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/mauhpr/cadence/compare/v0.4.3...v0.5.0
[0.4.3]: https://github.com/mauhpr/cadence/compare/v0.4.2...v0.4.3
[0.4.2]: https://github.com/mauhpr/cadence/compare/v0.4.1...v0.4.2
[0.4.1]: https://github.com/mauhpr/cadence/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/mauhpr/cadence/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/mauhpr/cadence/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/mauhpr/cadence/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/mauhpr/cadence/releases/tag/v0.1.0
