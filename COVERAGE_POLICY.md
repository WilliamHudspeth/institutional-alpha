# Test Coverage Policy

**Phase**: Phase 0.5 (Testing Excellence)  
**Goal**: 85%+ code coverage on all new code  
**Current**: ~70% (progressive enforcement)  
**Status**: Enforced in CI (`--cov-fail-under=70` on every PR)

---

## Philosophy

Code without tests is speculation. We enforce a minimum coverage floor to ensure:

1. **New code is tested** — every feature/fix requires test cases
2. **Critical paths are covered** — edge cases (nil, empty, bounds) are explicit
3. **Regressions are caught** — tests prevent re-breaking past fixes
4. **Confidence in shipping** — institutional-grade code must be institutional-grade tested

---

## Coverage Target by Phase

| Phase | Target | Enforcement |
|-------|--------|-------------|
| Current (0.4.0) | 70% | `--cov-fail-under=70` in CI |
| Phase 0.5 goal | 85% | `--cov-fail-under=85` after fixtures/mocking complete |
| Phase 1+ | 85%+ | Maintain or improve; no decreases allowed |

We use **progressive enforcement**: current floor (70%) can be exceeded by local commits, but cannot decrease. Once Phase 0.5 completes (fixture library + mock API strategy), we'll tighten to 85%.

---

## What Gets Measured

### Covered ✅

```python
def compute(self, security: Security) -> FactorContribution:
    if security.fundamentals.roic_history:  # ← branch tested
        ...
    return FactorContribution(...)  # ← happy path tested
```

- All branches (if/else)
- Happy paths (normal inputs)
- Edge cases (empty lists, None values, zero denominators)
- Error handling (try/except blocks)

### NOT Covered ❌ (and that's OK)

```python
def _never_called_helper():
    ...  # Dead code; should be deleted, not "covered"

# Unreachable except in OS-specific scenarios:
if platform.system() == "Windows":
    ...  # Skip testing on Linux
```

- Dead code (indicates a refactoring opportunity)
- Platform-specific code (test on that platform or mark `# pragma: no cover`)
- Test-only utilities (marked `# pragma: no cover`)

---

## How to Measure Coverage

### Local

```bash
# See line-by-line coverage
python -m pytest --cov=src/iam --cov-report=term-missing

# See by file
python -m pytest --cov=src/iam --cov-report=html
open htmlcov/index.html
```

### In CI

Every PR run includes:
```
pytest -v --cov=src/iam --cov-report=xml --cov-report=term-missing --cov-fail-under=70
```

Coverage report uploads to Codecov (badge in README). Git commit message shows coverage delta.

---

## Coverage Rules

### New Code

Every new file or major function must have:
- At least one "happy path" test
- At least one edge case test (empty list, None, zero, etc.)
- At least one error case test (if applicable)

Example:

```python
# In src/iam/factors/quality.py
def _margin_stability(history: list[float]) -> float | None:
    if len(history) < 3:
        return None  # ← test: empty/short history
    ...
```

```python
# In tests/test_quality.py
def test_margin_stability_short_history():
    assert _margin_stability([]) is None
    assert _margin_stability([0.5]) is None

def test_margin_stability_computes():
    assert _margin_stability([0.40, 0.42, 0.41]) is not None
```

### Exceptions to the Rule

Mark code that shouldn't be covered with `# pragma: no cover`:

```python
if __name__ == "__main__":  # pragma: no cover
    main()

# Platform-specific (test on that platform, or skip)
try:
    import windows_only_lib
except ImportError:  # pragma: no cover
    pass
```

---

## Coverage Gaps — Where to Focus

### Current gaps (as of Phase 0.4.0):

- **Data fetcher** (`src/iam/data/fetchers/`): ~45% — network I/O, fallback chains, cache expiry logic. Phase 0.5 will add mock API strategy.
- **Backtest harness** (`src/iam/backtest/`): ~60% — date edge cases, quantile boundary conditions. Phase 0.5 will add property-based tests.
- **UI rendering** (`src/iam/ui/`): ~50% — ANSI escape sequences hard to test without a terminal. Phase 0.5 will add snapshot tests.

These gaps are *known* and *acceptable* for Phase 0.4. Phase 0.5 **explicitly targets these modules** for fixture + mocking improvements.

---

## How to Improve Coverage

### If coverage drops below the floor:

1. **Add tests** for the uncovered lines:
   ```bash
   python -m pytest --cov=src/iam --cov-report=term-missing | grep "UNCOVERED"
   ```

2. **Delete dead code** if a line isn't reachable:
   ```python
   # If this is never called, delete it (don't add a test).
   ```

3. **Mark unavoidable gaps** with `# pragma: no cover`:
   ```python
   if impossible_condition:  # pragma: no cover
       ...
   ```

### Best practices:

- Write tests *first* (TDD) — test defines what the code should do
- Test behavior, not implementation — don't test that `x = 1` but that the sum is correct
- Use fixtures for shared setup (see tests/ for examples)
- Parametrize repeated tests: `@pytest.mark.parametrize("input,expected", [...])`

---

## Enforcement in CI

Every PR:
1. Runs full test suite
2. Generates coverage report
3. **Fails if coverage drops below floor** (`--cov-fail-under=70`)
4. Uploads coverage to Codecov (badge, PR comment)
5. Allows merge only if:
   - Tests pass
   - Coverage maintained or improved
   - Code review approved

---

## Roadmap Integration

| Phase | Action |
|-------|--------|
| **0.4.0** | Establish 70% floor; identify gaps |
| **0.5** | Build fixture library, mock API strategy, property-based tests → tighten to 85% |
| **1.0+** | Maintain 85%+; mutation testing (>90% kill rate) |

---

## Questions?

- **Why 85%?** — Industry standard for production code. Google, Amazon, Facebook target 85–95%.
- **What if a module is inherently untestable?** — Refactor it so it's testable. If truly not: document with `# pragma: no cover` and add a comment explaining why.
- **Can I commit with lower coverage?** — No; CI enforces the floor. But you can commit to a feature branch and we'll help bring it up to standard before merging.

See CONTRIBUTING.md for testing guidelines.

