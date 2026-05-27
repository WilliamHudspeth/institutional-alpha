# Claude working notes — institutional-alpha

You are helping develop a multi-factor equity scoring framework.
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
- `analyze.py` — command-line utility for single-ticker analysis
- `src/iam/` — main package
- `src/iam/factors/` — individual factor implementations
- `src/iam/pipeline/` — valuation pipeline stages (Reverse DCF → Relative → Intrinsic → Triangulation, with macro overlay + verdict)
- `docs/` — conceptual writeups (framework.md, factors.md, pipeline.md)
- `examples/` — runnable end-to-end demos
- `tests/` — pytest suite (including backtest harness)

## When unsure

- Ask before adding new dependencies
- Ask before changing public APIs (anything imported from `iam`)
- Ask before modifying factor weights or penalty formulas
- Reference docs/framework.md and docs/factors.md when in doubt

## Status

v0.2.0 is complete and stable:
- ✅ All 7 valuation pipeline stages implemented
- ✅ 10 orthogonal factors + 3 penalty terms
- ✅ Bayesian thesis engine with scenario analysis
- ✅ BacktestHarness for historical factor evaluation
- ✅ Interactive welcome screen and menu-driven UI
- ✅ Damodaran-anchored peer ranking

Future roadmap:
- Advanced data provider adapters (FMP, other sources)
- Machine learning-enhanced factor weightings
- Portfolio-level optimization tools
- Real-time monitoring and alerts

## My (William's) honest context

I'm still learning the codebase even though I own it. When you make
changes, explain *what* you changed and *why* in plain English.
Don't assume I'll catch subtle issues in a diff — flag them.
