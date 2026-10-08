## Summary

<!-- What changes and why. -->

## Type

- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation

Closes #

## Testing

- [ ] Tests added or updated; a bug fix includes a test that fails without the fix
- [ ] No test was weakened, skipped or loosened
- [ ] Tests do not use the network

## Checklist

- [ ] `ruff check src tests` and `ruff format --check src tests` pass
- [ ] `python -m mypy src/ --ignore-missing-imports` passes
- [ ] `bandit -r src -ll --skip B311` passes
- [ ] `pytest --cov=src/iam --cov-fail-under=85` passes
- [ ] No fabricated defaults: missing data is `None` or an explicit "insufficient data" state
- [ ] Documentation and `CHANGELOG.md` updated if behaviour changed
- [ ] PR title follows [Conventional Commits](../docs/development/commit-conventions.md)
