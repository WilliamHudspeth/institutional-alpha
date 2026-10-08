# Contributing

## Setup

```bash
git clone https://github.com/WilliamHudspeth/institutional-alpha
cd institutional-alpha
pip install -e ".[dev,test,data]"
pip install ruff==0.6.3        # CI pins this version
```

Python 3.10 or newer.

## Workflow

1. Create a branch off `main`, one branch per topic: `git checkout -b feat/your-feature`.
2. Make the change and add tests.
3. Run the checks below.
4. Open a pull request to `main` with a [Conventional Commit](docs/development/commit-conventions.md)
   title. Merges need one approval, passing checks and resolved conversations
   ([branch protection](docs/development/branch-protection.md)).

## Checks

```bash
ruff check src tests
ruff format --check src tests
python -m mypy src/ --ignore-missing-imports
bandit -r src -ll --skip B311
pytest --cov=src/iam --cov-fail-under=85 -q
```

For a faster loop while developing:

```bash
python -m pytest -q -o addopts="" -p no:cacheprovider --benchmark-disable --ignore=tests/performance
```

`python scripts/verify.py` runs the main checks in one command. Details are in
[CI/CD](docs/development/ci-cd.md) and the [coverage policy](docs/development/coverage-policy.md).

## Rules

1. **No fabricated numbers.** Do not add a default, mock or random value that looks computed
   (`x or 1.0`, a silent 21% tax rate or 9% discount rate). Missing data is `None`, an explicit
   "insufficient data" state, or a named, sourced and recorded default. Demo data is allowed only
   behind `--demo` with a visible banner.
2. **Every fix has a test that fails before the fix.**
3. **Do not weaken tests to make them pass.** No loosened ranges, skips, xfails or renames, and no
   fixtures in `tests/conftest.py` that change production behaviour. If specified behaviour
   changes, update the expected value and say why.
4. **Tests must not use the network.** Use recorded fixtures or patch the call.
5. **Follow the design principles** in [architecture](docs/architecture.md): orthogonal factors,
   auditable composites, pluggable data, no magic constants, minimal dependencies.
6. **Declare dependencies in `pyproject.toml`** and data files as package data. Do not install
   packages at run time.
7. Ask before adding a dependency, changing a public API or changing factor weights.

## Domain contributions

### Factor proposals

A new factor is a claim that a signal predicts return or risk, so it needs evidence.

1. Implement the `Factor` interface in `src/iam/factors/base.py`: `compute(security)` returns a
   `FactorContribution` with `value` in `[-1, 1]` (or `[0, 1]` for a penalty), `confidence` in
   `[0, 1]` and `components` filled in.
2. Add tests for the normal case, missing-data degradation and clamping.
3. Run the backtest and report IC with and without the factor, and its correlation with existing
   factors. A correlation above 0.80 needs a justification. Until the backtest has a valid result
   ([status](docs/research/backtest.md)), state that the evidence is limited.
4. Document it in [factors](docs/methodology/factors.md).
5. Title: `feat(factors): add <name> factor`.

### Data source adapters

Implement the `DataSource` contract in `src/iam/backtest/sources/base.py` (`fetch_price`,
`fetch_debt`, `download_history`, `is_available`). A failure raises `DataSourceError`; it never
returns a plausible default. Mock the network in tests, and record key requirements and rate
limits in the module docstring. Title: `feat(backtest): add <name> data source adapter`.

### Documentation and methodology

Documentation changes use the `docs:` type. Open questions about how the model should work belong
in GitHub Discussions rather than Issues.

## Issues and review

| Label | Meaning |
|---|---|
| `bug` | Something is broken |
| `feature` | New capability |
| `research` | Methodology, factor or backtest question |
| `documentation` | Docs gap or correction |
| `help-wanted` | Open for anyone to pick up |

Reviewers check correctness, consistency with existing patterns, clarity, input bounds, and scope.
Red flags are hard-coded constants, missing `None` handling, breaking changes without a version
bump, and new dependencies without justification. A closed issue gets a reason.

## Releases

Releases follow [semantic versioning](docs/development/releasing.md). Security fixes are released
out of band; see [SECURITY.md](SECURITY.md).
