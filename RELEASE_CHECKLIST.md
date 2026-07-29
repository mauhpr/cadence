# Cadence release process

Cadence publishes the `cadence-orchestration` Python package to PyPI from
GitHub Actions. Do not publish from a local machine.

## One-time repository setup

- Configure `pypi` and `testpypi` GitHub environments with deployment
  protection appropriate for the repository.
- Register both environments as PyPI Trusted Publishers. Do not store PyPI API
  tokens in GitHub or on maintainer machines.
- Protect `main` and require the test and lint workflows.
- Enable Dependabot, secret scanning, push protection, and private
  vulnerability reporting.

## Release owner checklist

1. Prepare a release PR from a branch such as `release/vX.Y.Z-description`.
   Update these files together:
   - `pyproject.toml`
   - `src/cadence/__init__.py`
   - `uv.lock`
   - `CHANGELOG.md`

2. Confirm the package version is identical in all release surfaces.

   ```bash
   uv lock --check
   uv run --python 3.13 python -c \
     'import cadence, tomllib; from pathlib import Path; p=tomllib.loads(Path("pyproject.toml").read_text()); assert cadence.__version__ == p["project"]["version"]'
   uv run --python 3.13 cadence --version
   ```

3. Run the complete local gate.

   ```bash
   uv sync --extra dev --extra all --frozen --python 3.13
   uv run --python 3.13 ruff format --check src/
   uv run --python 3.13 ruff check src/
   uv run --python 3.13 mypy src/
   uv run --python 3.13 pytest --cov=cadence --cov-report=term-missing
   uv build
   ```

4. Smoke-test the built wheel in an isolated environment.

   ```bash
   uv venv --seed .release-wheel-venv
   uv pip install --python .release-wheel-venv/bin/python dist/*.whl
   .release-wheel-venv/bin/cadence --version
   ```

5. Open the release PR and wait for every required GitHub check. Merge only
   after the Python/platform matrix and quality jobs pass.

6. Before the first production release of a version, run
   `.github/workflows/test-publish.yml` manually. It builds once, tests the
   wheel, and publishes that exact artifact to TestPyPI through trusted
   publishing. TestPyPI rejects a filename that has already been uploaded, so
   use a new version for every retry that reaches publication.

7. Merge the release PR into `main`, then create a GitHub Release from the
   final `main` commit.

   ```bash
   git fetch origin main --tags
   TARGET_SHA="$(git rev-parse origin/main)"
   gh release create vX.Y.Z \
     --target "$TARGET_SHA" \
     --title "Cadence vX.Y.Z" \
     --notes-file /path/to/release-notes.md
   ```

8. Let `.github/workflows/publish.yml` publish to PyPI using OIDC. Verify the
   workflow and a fresh install after it succeeds.

   ```bash
   gh run list --workflow publish.yml --limit 5
   uv tool install --upgrade --reinstall cadence-orchestration
   cadence --version
   ```

## Important rules

- Never run `twine upload`, `uv publish`, or another local upload command.
- Build once in the workflow and publish the transferred artifact; never
  rebuild in the trusted publishing job.
- Never move or reuse a published release tag. Publish a patch release for a
  correction.
- Keep release notes focused on user-visible behavior, fixes, compatibility,
  and migration requirements.
- Treat failed version consistency, installed-wheel, or metadata checks as a
  release blocker.
