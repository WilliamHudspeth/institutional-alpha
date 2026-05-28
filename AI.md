# AI working notes — institutional-alpha

You are an AI coding assistant (such as Antigravity or Claude) helping develop a multi-factor equity scoring framework.
The repo's design principles are non-negotiable. Read them before
making changes.

## Core design rules

1. **Factors are orthogonal.** Each factor measures one thing.
   Never blend valuation with quality, or quality with sentiment.
   If a change would couple two factors, stop and ask.

2. **Everything must be auditable.** Composite scores must decompose
   back to per-factor contributions and penalty terms. No black-box
   aggregations.

3. **Pluggable data sources.** The model never assumes a specific
   data provider. New code should accept fundamentals as inputs,
   not fetch them.

4. **No magic.** Default factor weights are explicit and documented.
   No hidden constants. No silent defaults that change behavior.

5. **Dependencies stay minimal.** numpy and pandas are fine. Adding
   anything else needs a strong reason — propose it before installing.

## Code conventions

- Python 3.10+
- Match the docstring style already in `src/iam/`
- Tests live in `tests/` and use pytest
- Every new factor or pipeline stage needs at least one test
- Type hints on public APIs

## Architecture map

- `main.py` — primary interactive entry point (welcome screen + guided menu)
- `run.py` — alternative interactive CLI for multi-lens valuation
- `src/iam/` — main package
- `src/iam/factors/` — individual factor implementations
- `src/iam/pipeline/` — valuation pipeline stages (Reverse DCF → Relative → Intrinsic → Triangulation, with macro overlay + verdict)
- `src/iam/backtest/` — production backtest harness (sources, metrics, calibration, runner, cli)
- `scripts/` — utility scripts
  - `scripts/analyze.py` — command-line utility for single-ticker analysis
  - `scripts/quick_recommend.py` — fast BUY/HOLD/SELL recommendation
  - `scripts/backtest_runner.py` — empirical backtest orchestrator
  - `scripts/build_price_parquet.py` — one-shot price parquet builder
- `docs/` — conceptual writeups + architecture
  - `docs/framework.md`, `docs/factors.md`, `docs/pipeline.md` — design rationale
  - `docs/ARCHITECTURE.md` — full system audit
  - `docs/REAL_DATA_BACKTEST_STRATEGY.md` — empirical validation plan
  - `docs/v0.3.5_BACKTEST_POST.md` — historical synthetic backtest writeup
- `data/` — runtime artifacts (mostly gitignored)
  - `data/cache/seed_cache.sqlite` — tracked warm-start cache
  - `data/cache/iam_cache.sqlite` — gitignored runtime cache
  - `data/universe/sp100.json` — static S&P 100 universe
  - `data/results/`, `data/prices/`, `data/snapshots/` — gitignored outputs
- `examples/` — runnable end-to-end demos
- `tests/` — pytest suite (including backtest harness)

## When unsure

- Ask before adding new dependencies
- Ask before changing public APIs (anything imported from `iam`)
- Ask before modifying factor weights or penalty formulas
- Reference docs/framework.md and docs/factors.md when in doubt

## Status

v0.4.0-rc1 / Recent Achievements (May 2026):
- ✅ **New Factor Activation**: Fully activated `_working_capital_quality` (inside `EarningsQualityFactor`) and `_roic_difficulty` (inside `ExpectationsDifficultyFactor`).
- ✅ **Data Layer Upgrades**: Built a robust, null-safe, fully formatted `yfinance_adapter.py` live data provider with strict 4-space indentation.
- ✅ **CI-CD & Code Quality**: Upgraded the entire codebase to pass strict Mypy type-checking, Ruff formatting, and Ruff lints cleanly.
- ✅ **Rigorous Testing**: Standardized the test suite to 500+ passing tests (e.g. test assertions formatting corrected in `test_thesis_engine.py`).
- ✅ **Pluggable Data & Backtesting**: Added a diskcache-backed data source layer, parallel scoring, and statsmodels Newey-West HAC calculations.

Future roadmap:
- Real-data S&P 100 empirical IC run and validation checks
- Portfolio-level optimization and allocation tools
- Machine learning-enhanced factor weightings

## My (William's) honest context

I'm still learning the codebase even though I own it. When you make
changes, explain *what* you changed and *why* in plain English.
Don't assume I'll catch subtle issues in a diff — flag them.
