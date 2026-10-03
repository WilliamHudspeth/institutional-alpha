# Handoff: cloud session → local Claude Code session

Written 2026-10-02 at the end of the cloud session that ran `docs/FIX_PLAN.md`.
Start a local Claude Code session in your clone and paste the prompt at the bottom.

## Where things stand

- **Branch:** `claude/adoring-fermat-rvbidx`, head `3917e78` (plus this handoff commit).
- **PR:** [WilliamHudspeth/institutional-alpha#46](https://github.com/WilliamHudspeth/institutional-alpha/pull/46), draft.
- **CI:** every GitHub Actions check is green: lint and type check, Test & Lint, the 3-OS × 3-Python matrix,
  and the 85% coverage gate (86.4%).
- **Only red check:** "Workers Builds: institutional-alpha" (Cloudflare). The repo has no wrangler or
  package.json config, so no code change fixes it. Disconnect the repo in the Cloudflare dashboard
  (Workers → institutional-alpha → Settings → Builds), or ignore it.

## What was done (FIX_PLAN workstreams)

| Commit | Change |
|---|---|
| `25203d6` | **WS1:** Battlefield attribution uses a real FCFE value function, not hardcoded weights. Adds `mismatch_score`, which feeds the verdict. |
| `fabec4a` | **WS3:** Thesis drift says whether thresholds come from the user or an example. Example thresholds never move the verdict. `IAM_CONSTRAINTS_DIR` is supported. |
| `f6b420e` | **WS2:** The TI-89 map is drawn from a real value grid (`valuation/value_grid.py`) and shows n/a when inputs are missing. |
| `6b745ce` | Risk-free rate comes from one cached ^TNX quote, never a mock. The scale is normalised. Pipeline run time dropped from 54s to 12s. |
| `deba15a`, `333c1b3` | TUI de-fabrication: real price history, an error state instead of mock data, honest scenario/backtest/SOTP panels. |
| `bd1370e` | **WS4:** Invented defaults removed or labelled (profile builder, macro, beta, SOTP). |
| `413984d` | Backtest quintile spread is NaN when not measured; it used to be invented as avg IC × 5. |
| `5b025f3` | Repo-wide ruff and bandit cleanup. https-only `data/http.py:safe_urlopen`. Fixed a durability-adjustment bug that always raised. |
| `e1df99d` | mypy clean. Real bugs fixed in `menu.py` `Assumption(...)` and `snapshots.py` `model_copy`. |
| `3917e78` | 143 behavioural tests; coverage 80.4% → 86.4%. |

## Open work, in priority order

1. **AGY tasks** in `docs/ops/agy-tasks.md`. AGY couldn't run in the cloud because `antigravity.google` is blocked.
   - **A1:** read-only review of `25203d6`, `fabec4a`, `f6b420e` and `6b745ce`, written to `docs/ops/agy-review-A1.md`.
   - **A2:** read-only review of the Sonnet diffs (TUI de-fabrication, WS4), written to `docs/ops/agy-review-A2.md`.
     The diffs are merged, so this can run now.
   - **A3:** WS5 data-source memo (FMP vs EDGAR), written to `docs/ops/ws5-data-source.md`. Docs only.
   - **A4:** delete or rewire the dead `ui/terrain.py` `TerrainPanel`.
   - **A5** is already done; mark it done in the queue.

   Workflow: AGY writes the review file, then Claude triages each finding. Real issues become a fix plus a
   failing-first test. Disputed findings get a one-line reason in the same file.
2. **Possible bug, owner to decide:** `valuation/damodaran_defaults.py` `get_synthetic_spread` uses strict `>`,
   so an interest coverage of exactly 3.00 rates BBB, not A-. Damodaran's table is usually `>=`.
   `tests/test_cov_guards_damodaran.py::test_synthetic_spread_edges` currently locks in `>`.
3. **Remaining invented defaults** (found by agents, not yet fixed):
   - `pipeline/orchestrator.py` `_calculate_dynamic_wacc` fallbacks: ke 0.09, rf 0.043, tax 0.21.
   - `data/providers/yfinance_adapter.py` defaults: 0.15, 0.12, 0.10 and 0.21.
   - The GUI shows `pwev_target` as $0.00 when it is missing.
   - `CompanyProfile.roe` and `roic` should be `Optional`.
4. **Test hygiene:** the Stooq mock in `tests/conftest.py` passes non-Stooq URLs through to the real `urlopen`.
5. **Dead code:** `valuation/expectations_battlefield.py` (the old engine). It is now tested, but only
   `scripts/quick_recommend.py` uses it. Decide whether to keep it.
6. **Open questions in `docs/FIX_PLAN.md`:**
   - **Q1:** FMP-first or EDGAR-first. A3 informs this.
   - **Q2:** merge the four text front-ends (WS6). Not started.
   - Q3–Q5 run on the plan's defaults.

## Guardrails (from the owner)

- **No made-up numbers** anywhere a user sees them. Missing data shows "n/a" or a labelled default.
- **Every fix ships with a test** that fails without it.
- **AGY reviews; it doesn't build** (except A4, which lists its files).
  Use the cheapest capable model for each job: delegate coding to Sonnet subagents and have Opus review and merge.
- Push to `claude/adoring-fermat-rvbidx` and keep PR #46 green.

## How to verify locally (mirrors CI)

```bash
pip install -e ".[dev,test,data]"
pip install ruff==0.6.3            # CI pins this; newer ruff misses UP038
ruff check src tests && ruff format --check src tests
python -m mypy src/ --ignore-missing-imports
bandit -r src -ll --skip B311
pytest --cov=src/iam --cov-fail-under=85 -x -q    # ~3 min, includes tests/performance
# fast loop:
python -m pytest -q -o addopts="" -p no:cacheprovider --benchmark-disable --ignore=tests/performance
```

Tests must not hit the network. To stop the pipeline from fetching, patch
`iam.data.markets.fetch_live_quote` (return None) and
`iam.data.providers.yfinance_adapter.build_regression_inputs` (raise).

## Prompt to paste into the local session

```text
Read docs/ops/HANDOFF.md and docs/ops/agy-tasks.md, then:
1. git pull origin claude/adoring-fermat-rvbidx
2. Run AGY task A1 with `agy -p "..."`: a read-only review of commits 25203d6, fabec4a, f6b420e,
   6b745ce against the six checks in agy-tasks.md, written to docs/ops/agy-review-A1.md as a
   table (Severity | File:line | Finding | Suggested fix).
3. Triage each finding. Fix real issues with a failing-first test; record disputed findings
   with a one-line reason in the same file.
4. Run the CI-equivalent checks from HANDOFF.md, commit, push to claude/adoring-fermat-rvbidx,
   and confirm PR #46 stays green.
5. Then continue with A2, A3 and A4 the same way.
```
