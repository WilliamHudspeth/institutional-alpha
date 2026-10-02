---
description: Non-negotiable rules for institutional-alpha (Python valuation engine, package iam under src/)
globs: "**/*"
---
1. No fabricated numbers. Never add a default, mock or random value that looks computed. Missing data is
   None and shows "n/a" or an explicitly labelled default. Demo data only behind an explicit --demo flag
   with a visible banner.
2. Design principles (docs/ai.md): orthogonal factors, auditable composites, pluggable data, no magic
   constants (name and justify every constant), minimal dependencies. Never pip install or add a
   dependency; never edit pyproject.toml dependencies.
3. Every fix or feature ships with a test that FAILS before the change and passes after. Write the test
   first and run it to see it fail.
4. Tests must not hit the network. To stop the pipeline fetching, patch
   iam.data.markets.fetch_live_quote (return None) and
   iam.data.providers.yfinance_adapter.build_regression_inputs (raise).
5. Before finishing, all of these must pass:
   ruff check src tests ; ruff format --check src tests (ruff is pinned to 0.6.3)
   python -m mypy src/ --ignore-missing-imports
   python -m pytest -q -o addopts="" -p no:cacheprovider --benchmark-disable --ignore=tests/performance
6. Git: commit on the current branch with a conventional commit message. Never push, never merge,
   never touch other branches, never rewrite history.
7. Only edit the files your task lists. If you must touch another file, say so in your final report.
8. Cite file:line for every claim. Verify against the code; do not speculate.
9. Never weaken a test to make it pass. Forbidden: replacing assertions with `pass`, loosening an exact
   check to a range (e.g. `> 0.04`), comparing against a placeholder, renaming a test so it is not
   collected (e.g. `SKIP_test_...`), adding skip/xfail, or adding autouse fixtures or monkeypatches in
   conftest.py that change production behaviour or inject values. If an existing test fails because the
   specified behaviour changed, update its expected value to the new correct value and explain why in
   the report. If it fails for any other reason, fix the code or stop and report. Never leave scratch
   scripts in the worktree.
