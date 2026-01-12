# Cadence Open Source Release Checklist

## 1. Documentation

- [ ] **README.md** - Comprehensive project overview
  - [ ] Project description and value proposition
  - [ ] Installation instructions (`pip install cadence-flow`)
  - [ ] Quick start example
  - [ ] Feature highlights with code examples
  - [ ] Link to full documentation
  - [ ] Badges (PyPI version, Python versions, CI status, license)

- [ ] **CONTRIBUTING.md** - Contribution guidelines
  - [ ] How to report bugs
  - [ ] How to suggest features
  - [ ] Development setup instructions
  - [ ] Code style and linting requirements
  - [ ] Pull request process
  - [ ] Code of conduct reference

- [ ] **CODE_OF_CONDUCT.md** - Community standards
  - [ ] Adopt Contributor Covenant or similar

- [ ] **CHANGELOG.md** - Version history
  - [ ] Document all versions (0.1.0, 0.2.0, 0.3.0)
  - [ ] Follow Keep a Changelog format

- [ ] **API Documentation**
  - [ ] Docstrings for all public classes/functions
  - [ ] Generated docs (Sphinx, MkDocs, or pdoc)
  - [ ] Host on GitHub Pages or Read the Docs

- [ ] **Examples directory**
  - [ ] Basic cadence example
  - [ ] Parallel execution example
  - [ ] Error handling and resilience example
  - [ ] FastAPI integration example
  - [ ] Flask integration example
  - [ ] Hooks/middleware example
  - [ ] Real-world use case example

---

## 2. Repository Setup

- [ ] **GitHub repository**
  - [ ] Create public repository
  - [ ] Update URLs in `pyproject.toml` with actual GitHub username
  - [ ] Add repository description and topics/tags
  - [ ] Set default branch to `main`

- [ ] **Branch protection**
  - [ ] Protect `main` branch
  - [ ] Require PR reviews
  - [ ] Require CI to pass

- [ ] **Issue templates**
  - [ ] Bug report template
  - [ ] Feature request template
  - [ ] Question/discussion template

- [ ] **Pull request template**
  - [ ] Description section
  - [ ] Type of change checklist
  - [ ] Testing checklist

- [ ] **Labels**
  - [ ] bug, enhancement, documentation
  - [ ] good first issue, help wanted
  - [ ] priority levels

---

## 3. Legal & Licensing

- [ ] **LICENSE file**
  - [ ] Add MIT license file (already specified in pyproject.toml)
  - [ ] Verify license year and copyright holder

- [ ] **License headers**
  - [ ] Decide if source files need license headers
  - [ ] Add headers if required

- [ ] **Third-party dependencies**
  - [ ] Verify all dependencies have compatible licenses
  - [ ] Document any attribution requirements

---

## 4. CI/CD Pipeline

- [ ] **GitHub Actions workflows**
  - [ ] `.github/workflows/test.yml` - Run tests on push/PR
    - [ ] Test on Python 3.10, 3.11, 3.12, 3.13
    - [ ] Test on Ubuntu, macOS, Windows
  - [ ] `.github/workflows/lint.yml` - Code quality checks
    - [ ] ruff linting
    - [ ] mypy type checking
  - [ ] `.github/workflows/publish.yml` - PyPI publishing
    - [ ] Trigger on release tag
    - [ ] Build and publish to PyPI

- [ ] **Code coverage**
  - [ ] Set up Codecov or Coveralls
  - [ ] Add coverage badge to README

- [ ] **Dependency scanning**
  - [ ] Enable Dependabot for security updates

---

## 5. Package Publishing

- [ ] **PyPI account**
  - [ ] Create account on pypi.org
  - [ ] Create account on test.pypi.org
  - [ ] Set up API tokens

- [ ] **Package metadata** (pyproject.toml)
  - [ ] Verify name is available on PyPI
  - [ ] Update author information
  - [ ] Update repository URLs
  - [ ] Verify classifiers are accurate
  - [ ] Add project logo/icon if desired

- [ ] **Test publish**
  - [ ] Build package: `python -m build`
  - [ ] Upload to TestPyPI first
  - [ ] Verify installation works: `pip install -i https://test.pypi.org/simple/ cadence-flow`

- [ ] **Production publish**
  - [ ] Create GitHub release with tag (v0.3.0)
  - [ ] Publish to PyPI

---

## 6. Code Quality

- [ ] **Test coverage**
  - [ ] Ensure >80% coverage
  - [ ] Add tests for new v0.3.0 features:
    - [ ] Flask integration tests
    - [ ] Diagram generation tests
    - [ ] CLI tests
    - [ ] Hooks system tests

- [ ] **Type hints**
  - [ ] All public APIs have type hints
  - [ ] mypy passes with strict mode

- [ ] **Linting**
  - [ ] All files pass ruff
  - [ ] No TODO/FIXME comments in production code

- [ ] **Security**
  - [ ] Run `pip-audit` or `safety` check
  - [ ] No hardcoded secrets
  - [ ] No known vulnerabilities

---

## 7. Pre-release Cleanup

- [ ] **Remove debug code**
  - [ ] No print statements
  - [ ] No debug flags enabled

- [ ] **Update version numbers**
  - [ ] `pyproject.toml` version
  - [ ] `__init__.py` __version__
  - [ ] CLI --version output

- [ ] **Clean up files**
  - [ ] Remove any private/internal documentation
  - [ ] Remove any placeholder content
  - [ ] Update .gitignore

- [ ] **Verify package contents**
  - [ ] Check `python -m build` creates expected files
  - [ ] Verify MANIFEST.in if needed

---

## 8. Launch Preparation

- [ ] **Announcement preparation**
  - [ ] Write blog post or announcement
  - [ ] Prepare social media posts
  - [ ] Identify relevant communities (Reddit, HN, Python Discord, etc.)

- [ ] **Support infrastructure**
  - [ ] GitHub Discussions enabled
  - [ ] Issue response SLA defined (internal)
  - [ ] Identify initial maintainers

---

## 9. Post-Launch

- [ ] **Monitor**
  - [ ] Watch for issues and questions
  - [ ] Respond to initial feedback

- [ ] **Iterate**
  - [ ] Address any installation issues
  - [ ] Fix any documentation gaps
  - [ ] Plan next release based on feedback

---

## Quick Commands Reference

```bash
# Build package
python -m build

# Upload to TestPyPI
python -m twine upload --repository testpypi dist/*

# Upload to PyPI
python -m twine upload dist/*

# Run tests
pytest tests/ -v --cov=cadence

# Run linting
ruff check src/
mypy src/

# Generate docs (if using pdoc)
pdoc --html cadence -o docs/
```

---

## Files to Create/Update

| File | Status | Priority |
|------|--------|----------|
| README.md | ⬜ Create/Update | High |
| CONTRIBUTING.md | ⬜ Create | High |
| CODE_OF_CONDUCT.md | ⬜ Create | High |
| CHANGELOG.md | ⬜ Create | High |
| LICENSE | ⬜ Create | High |
| .github/workflows/test.yml | ⬜ Create | High |
| .github/workflows/publish.yml | ⬜ Create | High |
| .github/ISSUE_TEMPLATE/*.md | ⬜ Create | Medium |
| .github/PULL_REQUEST_TEMPLATE.md | ⬜ Create | Medium |
| examples/*.py | ⬜ Create | Medium |
| docs/ | ⬜ Create | Medium |
