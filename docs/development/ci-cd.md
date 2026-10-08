# CI/CD

GitHub Actions runs on pushes and pull requests to `main`. Workflows are in `.github/workflows/`.

## Workflows

| Workflow | File | Checks |
|---|---|---|
| CI | `ci.yml` | bandit (`-ll --skip B311`), mypy, pytest with `--cov-fail-under=85`, wheel build |
| Lint & Type Check | `lint-type-check.yml` | `ruff check`, `ruff format --check`, mypy (Python 3.11) |
| Tests | `tests.yml` | pytest with coverage on Python 3.10, 3.11, 3.12 across operating systems; coverage uploaded from one job |
| Security & Health Audit | `security-audit.yml` | bandit, pip-audit, safety |
| CodeQL | `codeql.yml` | CodeQL static analysis |
| PR Title Check | `pr-title.yml` | Conventional Commits title format |
| Release Drafter | `release-drafter.yml` | Drafts release notes from merged PRs |
| Release | `release.yml` | On `v*` tags: sdist, wheel, GitHub Release, Windows and macOS executables |
| Build and Release Artifacts | `build-artifacts.yml` | Standalone executable build |

See [releasing](releasing.md) for how tags drive the release workflow and
[branch protection](branch-protection.md) for which checks gate merges.

## Run the checks locally

Use the same versions as CI. Ruff is pinned to 0.6.3.

```bash
pip install -e ".[dev,test,data]"
pip install ruff==0.6.3

ruff check src tests
ruff format --check src tests
python -m mypy src/ --ignore-missing-imports
bandit -r src -ll --skip B311

# Fast loop
python -m pytest -q -o addopts="" -p no:cacheprovider --benchmark-disable --ignore=tests/performance

# CI-equivalent, including tests/performance
pytest --cov=src/iam --cov-fail-under=85 -q
```

`python scripts/verify.py` runs the formatting, lint, type and test checks in one command.

Tests must not use the network.

## Pre-commit

```bash
pip install pre-commit
pre-commit install
pre-commit run --all-files
```

The hooks cover whitespace, YAML validity, private-key detection, ruff and bandit.

## Configuration

| File | Content |
|---|---|
| `pyproject.toml` | pytest, ruff, mypy and coverage settings (`fail_under = 85`) |
| `.pre-commit-config.yaml` | Local hooks |
| `.github/release-drafter.yml` | Release note categories and PR-title autolabeler |
| `.github/pull_request_template.md` | PR checklist |

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ruff check` fails | `ruff check src tests --fix`, then review the diff |
| `ruff format --check` fails | `ruff format src tests` |
| mypy errors | Add or correct type hints; narrow `float | None` values before arithmetic |
| Coverage below 85% | `pytest --cov=src/iam --cov-report=term-missing` and add tests for the listed lines |
| A test hits the network | Patch the data call; see [getting started](../getting-started.md) |
