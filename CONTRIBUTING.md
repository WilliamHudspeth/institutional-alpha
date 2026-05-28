# Contributing to Institutional Alpha

Thanks for your interest. This project is a multi-factor equity scoring framework with comprehensive testing and quality standards. Contributions of any size are welcome!

## Development Setup

### Prerequisites

- Python 3.10 or later
- Git

### Installation

1. Clone the repository:
```bash
git clone https://github.com/WilliamHudspeth/institutional-alpha.git
cd institutional-alpha
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install in editable mode with all dependencies:
```bash
pip install -e ".[dev,data,live,backtest]"
```

4. Install development tools:
```bash
pip install ruff mypy bandit safety
```

## Code Quality Standards

All contributions must pass automated quality checks. These run automatically on every pull request.

### Before Submitting

Run this checklist locally:

```bash
# Type checking
mypy src/ --ignore-missing-imports

# Code linting and formatting
ruff check src/ tests/
ruff format src/ tests/

# Tests and coverage
pytest -v --cov=src/iam --cov-report=term-missing

# Security checks
bandit -r src/
safety check
```

### What CI/CD Checks

Our GitHub Actions pipeline validates:

1. **Lint & Type Check** — Runs ruff and mypy
2. **Tests** — Full test suite on Python 3.10, 3.11, 3.12
3. **Coverage** — Code coverage reports uploaded to Codecov
4. **Security** — Bandit and safety checks for vulnerabilities
5. **Build** — Verifies package builds successfully

## Design Principles

Follow these core principles (documented in [AI.md](AI.md)):

1. **Factors are orthogonal** — Each factor measures one thing. Never blend valuation with quality, or quality with sentiment.

2. **Everything must be auditable** — Composite scores must decompose back to per-factor contributions and penalty terms. No black-box aggregations.

3. **Pluggable data sources** — The model never assumes a specific data provider. New code should accept fundamentals as inputs, not fetch them.

4. **No magic** — Default factor weights are explicit and documented. No hidden constants. No silent defaults that change behavior.

5. **Dependencies stay minimal** — numpy and pandas are fine. Adding anything else needs a strong reason — propose it before installing.

## Making Changes

### Branch Naming

Use descriptive branch names:
- `feature/name-of-feature` for new features
- `fix/name-of-bug` for bug fixes
- `docs/name-of-update` for documentation
- `refactor/name-of-refactor` for refactoring

### Commit Messages

Write clear, concise commit messages:

```
type: brief description

- More detailed explanation if needed
- Each change on its own line
```

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`

## High-Value Contributions

1. **Implement a factor** — Pick a factor in `src/iam/factors/` and enhance the placeholder calculations. Each file documents what it should do.

2. **Add a data provider adapter** — Wire `Security` to a real data source (FMP, Alpha Vantage, etc.) in a new module under `src/iam/data/providers/`.

3. **Write edge-case tests** — Especially for missing data, extreme values, and boundary conditions.

4. **Calibrate weights** — Use backtest results to validate or improve default factor weights.

## How to Add a New Factor

1. Subclass `Factor` (or `PenaltyFactor`) from `iam.factors.base`.
2. Set `name`.
3. Implement `compute(security) -> FactorContribution`. Return `value` in `[-1, 1]` (or `[0, 1]` for penalties), set `confidence` < 1.0 when data is missing, and populate `components` for auditability.
4. Register it in `src/iam/factors/__init__.py`.
5. Add it to the default factor list in `src/iam/engine/composite.py` if it's a core factor, and add a default weight to `DEFAULT_WEIGHTS`.
6. Document it in `docs/factors.md`.
7. Add a unit test in `tests/` with at least 100% coverage.

## Testing

All public functionality requires tests:

```bash
# Run all tests
pytest -v

# Run with coverage report
pytest -v --cov=src/iam --cov-report=term-missing

# Run specific test file
pytest tests/test_factors.py -v

# Run specific test
pytest tests/test_factors.py::TestValuationFactor::test_value_premium -v
```

Minimum coverage:
- New code: 100% coverage required
- Modified code: Maintain or improve existing coverage

## Pull Requests

1. Create a feature branch from `main`
2. Make your changes and commit with clear messages
3. Push to your fork and open a PR against `main`
4. Fill out the PR template completely
5. Ensure all CI/CD checks pass (they run automatically)
6. Address any review feedback
7. Maintainers will merge when ready

## Architecture

- `src/iam/` — Main package
- `src/iam/factors/` — Individual factor implementations
- `src/iam/pipeline/` — Valuation pipeline stages
- `src/iam/backtest/` — Production backtest harness
- `tests/` — Comprehensive test suite
- `docs/` — Design documentation and architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for full details.

## Questions?

- Check [docs/](docs/) for design documentation
- Review [AI.md](AI.md) for project principles
- Open a GitHub discussion

## Disclaimer

By contributing you agree your contribution is released under the MIT license. This is research software — please don't contribute code that fetches data you don't have rights to, and don't use the framework as a substitute for licensed financial advice.
