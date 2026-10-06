# CLAUDE.md: institutional-alpha

Multi-factor equity scoring and valuation engine: reverse DCF, FCFE intrinsic, relative, SOTP, Damodaran laws,
7-stage pipeline, Bayesian thesis engine and IC backtest harness. Python 3.10+, package `iam` under `src/`.
Owner: William Hudspeth.

## Read first
- **`docs/FIX_PLAN.md`** sets the remediation scope and order. `docs/ops/agy-coding-round1.md` records what
  was built, who built it, every review and every disputed finding.
- **`docs/ops/fix-plan-prompt.md`** is the original takeover prompt, kept as history.
- The root `HANDOFF.md` and parts of `ROADMAP.md` overclaim (e.g. "v1.0 ready", "functionally complete").
  The code is **0.4.0-rc1**. Trust the code and tests over the docs.

## State of the code (verified 2026-10-04, `main` after PR #46)
- **Tests:** 1,573 pass and 2 skip (the skips are environment-only: scikit-learn not installed, and POSIX file
  modes on Windows). Coverage is about 86.7%, and CI gates on 85%. ruff, mypy and bandit are clean.
- **Valuation method:** follows the owner's NYU Stern BlackRock paper (v10) and Damodaran.
  - **Reverse DCF (Stage 1)** uses the *consensus* Ke = Rf + regression beta x US ERP (Damodaran April 2026,
    5.03%).
  - **Intrinsic and the reference WACC** use the *bottom-up* Ke = Rf + Damodaran industry beta relevered at
    the current D/E x revenue-weighted ERP. Country ERPs average the rating- and CDS-based figures; regions
    are GDP-weighted; the revenue mix is always renormalised.
  - **Marginal tax** comes from Damodaran's country statutory rates, weighted by revenue mix (the US is 25%).
    It is used to relever beta and for the after-tax cost of debt.
  - **Effective tax** (`Fundamentals.effective_tax_rate`) feeds the multiples regression.
  - **Terminal growth** is capped at Rf in every DCF engine.
  - **Reference check (BLK-like):** consensus Ke 10.84%, ERP 5.44%, relevered beta 0.691, bottom-up Ke 8.06%.
- **Reference data** is in `src/iam/data/reference/`: `country_erp_2026-04.json`, `country_tax_2026-04.json`, and
  `country_erp_2026-01.json` (older dates stay reproducible). The newest dated file is the default; override
  with `IAM_COUNTRY_ERP_FILE` / `IAM_COUNTRY_TAX_FILE`. Refresh them from Damodaran's January and July updates.
- **Still open:**
  - The ML lens is never fitted (`ml/ml_lens.py` never calls `AnomalyDetector.fit`).
  - The IC backtest has no real result: `data/results/ic/ic_summary.txt` shows `n_obs: 0`. It suffers from
    look-ahead and survivorship bias, because `data/universe/sp100.json` is frozen at 2024-12-31.
  - The data-source decision (FIX_PLAN Q1, memo `docs/ops/ws5-data-source.md`) is pending.
  - WS6 (merging the text front-ends) is pending.
  - Live tickers get `Security.revenue_mix` from the latest 10-K's geographic revenue
    (`data/edgar/geography.py`, EDGAR Phase B). The source is in `qualitative["revenue_mix_source"]`.
    Members that `country_risk` cannot resolve (e.g. AAPL "Other countries", MSFT "Non-US") stay in
    the mix and lower its coverage; ERP and tax are weighted over the resolved part. With no 10-K
    mix, live tickers fall back to the US ERP and tax rate. The backtest is not wired yet (Phase C).
- **Resolved, so don't reintroduce:** Damodaran Law 3 and every cost of equity read Rf from the pipeline. No
  4.3%, 21% or `market_cap or 1.0` defaults remain on the valuation path.

## Non-negotiable rules
1. **No fabricated numbers.** Never add a default, mock or random value that looks computed: no `x or 1.0`, no
   silent 21% or 9%. Missing data means None, an explicit "insufficient data" state, or a named, sourced and
   recorded default. Demo data is allowed only behind `--demo` with a visible banner.
2. Follow the design principles in **`docs/ai.md`**: orthogonal factors, auditable composites, pluggable data,
   no magic constants, minimal dependencies.
3. Every fix ships with a test that fails before the fix. Keep the full suite green.
4. **Never weaken a test to make it pass.** No `pass` in place of assertions, no loosened ranges, no
   renamed, skipped or xfailed tests, and no autouse fixtures or monkeypatches in `tests/conftest.py` that
   change production behaviour or inject values. When specified behaviour changes, update the expected value
   and say why.
5. One branch per workstream, conventional commits. Ask the owner before pushing to `main`, merging PRs or
   deleting branches.
6. Don't `pip install` from app code at runtime. Declare dependencies in `pyproject.toml`; data files must be
   declared as package data (guarded by `tests/test_package_data.py`).
7. Verify claims (yours, AGY's, a bot reviewer's or the docs') against the code with file:line evidence before
   acting on them.

## Commands
```bash
pip install -e ".[dev,test,data]"
pip install ruff==0.6.3                       # CI pins this version
ruff check src tests && ruff format --check src tests
python -m mypy src/ --ignore-missing-imports
bandit -r src -ll --skip B311
python -m pytest -q -o addopts="" -p no:cacheprovider --benchmark-disable --ignore=tests/performance   # fast loop
pytest --cov=src/iam --cov-fail-under=85 -q    # CI-equivalent (includes tests/performance)
python launch_gui.py                          # Streamlit GUI (src/iam/ui/gui.py)
python launch_tui.py [--demo]                 # ANSI terminal UI (src/iam/ui/alpha_terminal.py)
```
Tests must not hit the network. To run the pipeline offline, patch `iam.data.markets.fetch_live_quote`
(return None) and `iam.data.providers.yfinance_adapter.build_regression_inputs` (raise). This is a Windows
machine: use PowerShell or Git Bash, and quote paths.

## Map
- `src/iam/pipeline/`: the orchestrator (7 stages; stage-specific Ke), verdict, arbitration, and
  `battlefield.py` (real FCFE attribution).
- `src/iam/valuation/`: reverse DCF, FCFE DCF, relative, SOTP, triangulator, `value_grid.py` (TI-89 map and
  fair-value frontier), `country_risk.py` (`company_erp`), `country_tax.py` (`company_marginal_tax`).
- `src/iam/data/`:
  - `damodaran.py`: Rf with its source, loaders.
  - `ground_truth.py`: the bottom-up Ke profile.
  - `providers/yfinance_adapter.py`: live data; missing fields stay None.
  - `reference/`: Damodaran data.
- `src/iam/factors/`, `lenses/`, `laws/`, `reasoning/`, `thesis/`: scoring and reasoning layers.
- `src/iam/backtest/`: snapshots, ic_runner, sources (yfinance, stooq, SEC EDGAR, FMP, tiered router).
- `src/iam/ui/`: `gui.py`, `alpha_terminal.py`, `ti89_graph.py`, `visualization_lab.py`, plus legacy terminals
  slated for consolidation (WS6).

## Working with models and AGY
- **Main session (strongest model):** planning, financial-modeling correctness, and final line-by-line
  review of every branch before merge.
- **Valuation-critical code** goes to Claude Sonnet subagents in their own git worktrees.
- **Narrow and mechanical tasks** may go to AGY (Gemini) as coder, in a throwaway worktree on an `agy/<task>`
  branch. Use the launcher pattern: inline `.agents/rules/iam-rules.md` and the `iam-coder` body into the
  prompt, because custom agents without a `tools:` list are read-only in agy 1.2.14. Pass the model id without
  `--effort`, since the id already encodes the tier.
- **AGY as reviewer** runs read-only with `--agent iam-reviewer`, on a model family different from the
  coder's.
- **After an AGY coder (or any coder):** scan the test diff mechanically before merging, checking for an
  unchanged conftest and for no `pass`, skip or loosened asserts. An AGY Gemini coder was rejected once for
  gaming tests (`agy/coe-split-gemini-rejected`).
- **Quotas:** AGY quotas run out (HTTP 429). Probe each model with a one-line prompt before dispatching.

## Done means
Tests green, ruff, mypy and bandit clean, no fabricated output paths, a review recorded in
`docs/ops/agy-coding-round1.md` (or a successor), and the docs updated to match the code. Report back to the
owner with what changed and the evidence.
