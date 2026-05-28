# CI/CD Pipeline

This document explains the automated testing and quality assurance infrastructure that runs on every push and pull request.

## Pipeline Overview

The GitHub Actions workflow (`CI/CD Pipeline`) runs on every push to `main` and on every pull request to `main`. It validates code quality, runs tests, checks security, and attempts to build distribution packages.

### Jobs

#### 1. Lint & Type Check

**Runs on:** Every PR and push  
**Python version:** 3.11  
**Tools:**
- `ruff` — Code linting and formatting checks
- `mypy` — Static type checking

**Checks:**
- Linting rules (error/style violations)
- Import sorting (isort plugin)
- Code formatting consistency
- Type annotation coverage

**Failure:** PR blocks if linting or type checking fails

#### 2. Test

**Runs on:** Every PR and push  
**Python versions:** 3.10, 3.11, 3.12 (in parallel)  
**Tools:**
- `pytest` — Test runner with coverage reporting
- `codecov` — Coverage tracking

**Checks:**
- All unit and integration tests pass
- Code coverage meets requirements
- Coverage reports uploaded to Codecov

**Failure:** PR blocks if tests fail or coverage drops

#### 3. Security

**Runs on:** Every PR and push  
**Python version:** 3.11  
**Tools:**
- `bandit` — Security issue detection
- `safety` — Dependency vulnerability checking

**Checks:**
- Code for common security issues
- Dependencies for known CVEs

**Failure:** Non-blocking (warnings only)

#### 4. Build & Verify

**Runs on:** After lint and test pass  
**Python version:** 3.11  
**Tools:**
- `build` — Package building
- `pip` — Installation verification

**Checks:**
- Source distribution builds successfully
- Wheel distribution builds successfully
- Package installs without errors
- Package import works correctly

**Failure:** PR blocks if build fails

## Local Development

### Set Up Pre-Commit Hooks

To catch issues before committing:

```bash
pip install pre-commit
pre-commit install
```

Then pre-commit hooks run automatically on `git commit`. To run manually:

```bash
pre-commit run --all-files
```

### Run Checks Locally

Before pushing, verify all checks pass:

```bash
# Type checking
mypy src/ --ignore-missing-imports

# Code linting
ruff check src/ tests/

# Code formatting
ruff format src/ tests/

# Tests with coverage
pytest -v --cov=src/iam --cov-report=term-missing

# Security checks
bandit -r src/
safety check
```

## Configuration Files

### `pyproject.toml`

Contains configuration for:
- `[tool.pytest.ini_options]` — pytest settings
- `[tool.ruff]` — ruff linting rules
- `[tool.ruff.lint]` — specific linting checks to enable/disable
- `[tool.ruff.lint.isort]` — import sorting rules
- `[tool.mypy]` — mypy type checking settings

### `.github/workflows/python-package.yml`

The main CI/CD workflow definition. Jobs run in sequence:
1. Lint & Type Check (fast)
2. Test (medium)
3. Security (medium)
4. Build (depends on test passing)

### `.pre-commit-config.yaml`

Pre-commit hooks for local development. Includes:
- ruff linting and formatting
- basic file checks (trailing whitespace, large files, etc.)
- mypy type checking

### `.github/pull_request_template.md`

Template that appears when opening PRs. Reminds contributors to:
- Describe the change and type
- Link related issues
- List testing done
- Confirm checklist items

## Status Badges

Add this to your README to show CI/CD status:

```markdown
[![CI/CD Pipeline](https://github.com/WilliamHudspeth/institutional-alpha/actions/workflows/python-package.yml/badge.svg)](https://github.com/WilliamHudspeth/institutional-alpha/actions)
```

## Troubleshooting

### Ruff Linting Fails

Check what's wrong:
```bash
ruff check src/ tests/
```

Auto-fix fixable issues:
```bash
ruff check src/ tests/ --fix
```

### Code Formatting Issues

Auto-format all files:
```bash
ruff format src/ tests/
```

### Type Checking Fails

Run mypy to see issues:
```bash
mypy src/ --ignore-missing-imports
```

Fix by adding type hints to your code.

### Tests Fail

Run locally to debug:
```bash
pytest -v  # Verbose output
pytest -v --tb=short tests/test_file.py  # Single file
pytest -v -k test_name  # Single test
```

### Coverage Below Threshold

Check coverage report:
```bash
pytest --cov=src/iam --cov-report=term-missing
```

Add tests to raise coverage for modified code.

### Build Fails

Check setup.py and pyproject.toml for issues:
```bash
python -m build
pip install dist/*.whl
python -c "import iam; print(iam.__version__)"
```

## Best Practices

1. **Run checks locally before pushing** — Use pre-commit hooks or manual checks
2. **Write tests for new code** — Aim for 100% coverage on new functions
3. **Keep commits focused** — One feature or fix per commit
4. **Write clear commit messages** — Reviewers will thank you
5. **Update documentation** — Add docstrings and update relevant docs/
6. **Review CI output** — Don't ignore warnings; address them proactively

## Accessing CI/CD Results

- **PR checks:** Visible as green/red checkmarks in the PR interface
- **Action details:** Click "Details" next to a check to see full output
- **Action history:** Visit Actions tab in the repository
- **Coverage reports:** Visit codecov.io dashboard (if integrated)

## Questions?

See [CONTRIBUTING.md](../CONTRIBUTING.md) for development guidelines.
