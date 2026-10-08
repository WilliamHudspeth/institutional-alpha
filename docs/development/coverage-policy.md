# Coverage Policy

Line coverage of `src/iam` must stay at or above **85%**. CI enforces this with
`--cov-fail-under=85` (`.github/workflows/ci.yml`), and `pyproject.toml` sets
`[tool.coverage.report] fail_under = 85`. The suite currently sits at about 86.7%.

## Rules for new code

Every new module or function needs:

- a test for the normal path,
- a test for missing or empty input (`None`, empty list, zero denominator), and
- a test for each error path it defines.

Bug fixes include a test that fails before the fix.

```python
def test_margin_stability_short_history():
    assert _margin_stability([]) is None
    assert _margin_stability([0.5]) is None
```

Do not weaken a test to make it pass. Do not loosen ranges, skip, xfail or rename tests, and do
not add fixtures or monkeypatches to `tests/conftest.py` that change production behaviour or
inject values. If specified behaviour changes, update the expected value and explain why in the
commit.

## What is excluded

- Code that cannot run on the test platform may carry `# pragma: no cover`, with a comment saying
  why.
- `if __name__ == "__main__":` entry points.
- Dead code should be deleted rather than covered.

## Measuring

```bash
# Line-by-line gaps
python -m pytest --cov=src/iam --cov-report=term-missing

# HTML report
python -m pytest --cov=src/iam --cov-report=html
```

## Weak areas

Coverage is lowest where code depends on the network or a terminal: the data fetchers, the
backtest harness edge cases and ANSI rendering in `src/iam/ui/`. Tests for these use recorded
fixtures or mocks and must not make live calls.

## If CI fails on coverage

1. Run the `term-missing` report and add tests for the lines you changed.
2. Delete code that is unreachable.
3. Mark genuinely untestable lines with `# pragma: no cover` and a reason.
