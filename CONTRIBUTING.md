# Contributing to Cadence

Thank you for your interest in contributing to Cadence! This document provides guidelines and instructions for contributing.

## Code of Conduct

By participating in this project, you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md). Please read it before contributing.

## How to Contribute

### Reporting Bugs

Before submitting a bug report:

1. Check the [existing issues](https://github.com/mauhpr/cadence/issues) to avoid duplicates
2. Use the latest version of Cadence
3. Collect information about the bug:
   - Python version (`python --version`)
   - Cadence version (`cadence --version`)
   - Operating system
   - Stack trace (if applicable)
   - Steps to reproduce

To report a bug, [open a new issue](https://github.com/mauhpr/cadence/issues/new?template=bug_report.md) using the bug report template.

### Suggesting Features

We welcome feature suggestions! Before submitting:

1. Check if the feature has already been requested
2. Consider if the feature aligns with Cadence's goals
3. Think about the implementation approach

To suggest a feature, [open a new issue](https://github.com/mauhpr/cadence/issues/new?template=feature_request.md) using the feature request template.

### Pull Requests

1. Fork the repository
2. Create a feature branch from `main`
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass
6. Submit a pull request

## Development Setup

### Prerequisites

- Python 3.10 or higher
- pip or uv package manager

### Setting Up Your Environment

```bash
# Clone your fork
git clone https://github.com/mauhpr/cadence.git
cd cadence

# Create a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in development mode with all dependencies
pip install -e ".[dev,all]"
```

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=cadence --cov-report=html

# Run a specific test file
pytest tests/test_cadence.py -v

# Run a specific test
pytest tests/test_cadence.py::TestCadenceBasics::test_single_beat -v
```

### Code Quality

We use several tools to maintain code quality:

```bash
# Run linter
ruff check src/

# Fix auto-fixable issues
ruff check src/ --fix

# Run type checker
mypy src/

# Format code (if using ruff format)
ruff format src/
```

### Pre-commit Hooks (Optional)

You can set up pre-commit hooks to run checks automatically:

```bash
pip install pre-commit
pre-commit install
```

## Code Style

### General Guidelines

- Follow [PEP 8](https://pep8.org/) style guidelines
- Use type hints for all public functions and methods
- Write docstrings for all public APIs
- Keep functions focused and concise
- Prefer explicit over implicit

### Naming Conventions

- Classes: `PascalCase`
- Functions/methods: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Private members: `_leading_underscore`

### Docstrings

Use Google-style docstrings:

```python
def process_order(order_id: str, options: dict = None) -> Order:
    """Process an order and return the result.

    Args:
        order_id: The unique identifier for the order.
        options: Optional processing options.

    Returns:
        The processed Order object.

    Raises:
        OrderNotFoundError: If the order doesn't exist.
        ProcessingError: If processing fails.

    Example:
        >>> order = process_order("ORD-123")
        >>> print(order.status)
        'completed'
    """
```

### Type Hints

All public APIs should have type hints:

```python
from typing import Optional, List, Callable, TypeVar

ContextT = TypeVar("ContextT")

def create_cadence(
    name: str,
    context: ContextT,
    *,
    reporter: Optional[Callable[[str, float, ContextT], None]] = None,
) -> Cadence[ContextT]:
    ...
```

## Testing Guidelines

### Test Structure

- Place tests in the `tests/` directory
- Mirror the source structure (e.g., `src/cadence/cadence.py` → `tests/test_cadence.py`)
- Use descriptive test names

### Writing Tests

```python
import pytest
from cadence import Cadence, Context, beat
from dataclasses import dataclass

@dataclass
class TestContext(Context):
    value: int = 0

class TestCadenceBasics:
    """Tests for basic Cadence functionality."""

    @pytest.mark.asyncio
    async def test_single_beat_modifies_context(self):
        """Verify that a single beat can modify the context."""
        @beat
        async def increment(ctx: TestContext):
            ctx.value += 1

        cadence = Cadence("test", TestContext(value=0)).then("inc", increment)
        result = await cadence.run()

        assert result.value == 1

    @pytest.mark.asyncio
    async def test_cadence_with_error_handler(self):
        """Verify that error handlers are called on failure."""
        errors = []

        @beat
        async def failing_beat(ctx: TestContext):
            raise ValueError("Test error")

        cadence = (
            Cadence("test", TestContext())
            .then("fail", failing_beat)
            .on_error(lambda ctx, err: errors.append(err))
        )

        await cadence.run()
        assert len(errors) == 1
```

### Test Categories

- **Unit tests**: Test individual components in isolation
- **Integration tests**: Test component interactions
- **End-to-end tests**: Test complete workflows

## Pull Request Process

### Before Submitting

1. **Update documentation**: If you're adding features, update the relevant documentation
2. **Add tests**: All new code should have corresponding tests
3. **Run the full test suite**: Ensure all tests pass
4. **Run linting and type checks**: Fix any issues

### PR Title Format

Use conventional commit format:

- `feat: Add new feature`
- `fix: Fix bug in X`
- `docs: Update documentation`
- `test: Add tests for X`
- `refactor: Refactor X`
- `chore: Update dependencies`

### PR Description

Include:
- What changes were made
- Why the changes were made
- How to test the changes
- Any breaking changes

### Review Process

1. A maintainer will review your PR
2. Address any feedback
3. Once approved, a maintainer will merge the PR

## Project Structure

```
cadence/
├── src/
│   └── cadence/
│       ├── __init__.py          # Package exports
│       ├── cadence.py           # Core Cadence class
│       ├── context.py           # Context management
│       ├── beat.py              # Beat decorator
│       ├── result.py            # Result types (Ok, Err)
│       ├── exceptions.py        # Exception classes
│       ├── resilience.py        # Retry, timeout, fallback, circuit breaker
│       ├── hooks.py             # Hooks system
│       ├── diagram.py           # Cadence diagram generation
│       ├── cli.py               # CLI commands
│       ├── reporters.py         # Time reporters
│       ├── nodes/               # Node implementations
│       │   ├── base.py
│       │   ├── single.py
│       │   ├── sequence.py
│       │   ├── parallel.py
│       │   ├── branch.py
│       │   └── child.py
│       └── integrations/        # Framework integrations
│           ├── fastapi.py
│           └── flask.py
├── tests/                       # Test files
├── examples/                    # Example code
├── docs/                        # Documentation
└── pyproject.toml              # Project configuration
```

## Release Process

Releases are managed by maintainers:

1. Update version in `pyproject.toml` and `__init__.py`
2. Update `CHANGELOG.md`
3. Create a git tag (`v0.x.x`)
4. Push tag to trigger release workflow
5. GitHub Actions publishes to PyPI

## Getting Help

- **Questions**: Open a [discussion](https://github.com/mauhpr/cadence/discussions)
- **Bugs**: Open an [issue](https://github.com/mauhpr/cadence/issues)
- **Chat**: Join our community (if applicable)

## Recognition

Contributors will be recognized in:
- The CHANGELOG for their contributions
- The GitHub contributors page

Thank you for contributing to Cadence!
