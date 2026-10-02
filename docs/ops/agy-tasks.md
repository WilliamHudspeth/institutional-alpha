# AGY task queue

> Headless runs: `agy -p` cannot prompt for shell permission, so it needs
> `--dangerously-skip-permissions`. Run it only in a throwaway `git worktree`. It wrote files
> even under `--mode plan`.

AGY runs on the owner's machine, not in the Claude cloud session. Paste one
task at a time into AGY from the repo root on branch `claude/adoring-fermat-rvbidx`.

Rules for every task:

- **No made-up numbers.** Missing data shows as "n/a", never as a default or a random value.
- **Review tasks are read-only.** Write findings into the file named in the task; do not edit code.
- **Coding tasks touch only the files listed.** The Sonnet agents own `ui/alpha_terminal.py`,
  `ui/state.py`, `ui/gui.py`, `ui/menu.py`, `pipeline/macro.py`, `valuation/profile_builder.py`,
  `valuation/beta.py` and the SOTP block of `pipeline/orchestrator.py` until their work is merged.
- Every code change ships with a test that fails without it. Run:
  `python -m pytest -q -o addopts="" -p no:cacheprovider --benchmark-disable --ignore=tests/performance`
- Push to `claude/adoring-fermat-rvbidx` only (the owner authorised push and pull).

---

## A1 — Review the landed fixes (read-only) — DONE 2026-10-02 (see output file)

Review commits `25203d6`, `fabec4a`, `f6b420e` and `6b745ce`
(`git log 26de61b..6b745ce`). For each one, check:

1. Is any number shown to the user still invented or defaulted without a label?
2. **Battlefield** (`pipeline/battlefield.py`, Stage 4b in `pipeline/orchestrator.py`):
   - Does `fcfe_value_fn` match the FCFE engine's maths?
   - Is `mismatch_score` (|market-implied value ÷ intrinsic − 1|, capped at 100) a sound thing
     to feed `VerdictGenerator` (it can turn BUY into SPECULATIVE_BUY above 60)?
   - Propose something better if you have it.
3. **Drift** (`thesis/drift.py`): is it right that example thresholds never move the verdict?
4. **TI-89 map** (`valuation/value_grid.py`, `ui/ti89_graph.py`): are the axis ranges sensible?
   The plan uses growth ±6pp and discount rate ±2pp around the base case, widened to include
   the market point.
5. **Risk-free rate** (`data/damodaran.py`): is the ^TNX scale normalisation safe?
6. Are any tests weak or tautological?

Write findings to `docs/ops/agy-review-A1.md` as a table:

| Severity (blocker/major/minor) | File:line | Finding | Suggested fix |

## A2 — Review the Sonnet diffs (read-only, when the owner says they're merged) — DONE 2026-10-02 (see output file)

Same format as A1, written to `docs/ops/agy-review-A2.md`. There are two diffs:

- **TUI de-fabrication:** real price history and quotes, an error state instead of mock data,
  an honest model portfolio, and real factor exposures.
- **WS4 defaults sweep:** check the classification table in `docs/FIX_PLAN.md` against the code.

## A3 — WS5 data-source decision memo (docs only) — DONE 2026-10-02 (see output file)

The owner must choose FMP-first or EDGAR-first for historical financials (Q1 in
`docs/FIX_PLAN.md`). Both clients already exist:

- `backtest/sources/fmp_source.py`
- `backtest/sources/sec_edgar_source.py`
- `data/fetcher.py` (`SecEdgarSource`, `RedundantDataFetcher`)
- `backtest/sources/tiers.py` (the tiered router)

Write `docs/ops/ws5-data-source.md` covering:

- What each source actually returns today.
- Which pipeline fields (`Fundamentals`) each can fill.
- The XBRL-mapping gaps on the EDGAR side.
- Cost and rate limits.
- The smallest change that routes the live pipeline (`data/providers/yfinance_adapter.py`
  `fetch_security`) through `tiers.py` with provenance.
- A recommendation.

No code changes.

## A4 — Remove dead demo terrain code (coding; files listed only) — DONE (deleted; done by Claude, not AGY)

`ui/terrain.py` `TerrainPanel` is not used by the app (only by `tests/test_enhancements_smoke.py`).
Its fallback path reads a Battlefield field that no longer exists, and it draws
`saddle_demo_grid()` / `dcf_terrain_grid(price, 0.10, 0.09)` with invented inputs.

Either:

- **Delete** the class, plus the `engine/simulations.py` helpers it alone uses (check with grep
  first); or
- **Rewire** it to `valuation/value_grid.build_value_grid` and show "n/a" when that returns None.

Prefer deleting if nothing else uses it.

Files: `src/iam/ui/terrain.py`, `src/iam/engine/simulations.py`, `tests/test_enhancements_smoke.py`.

## A5 — Lint and security-scan cleanup — DONE in 5b025f3

CI's `ruff check src/ tests/` reports about 139 errors on `main`, and bandit fails the
"Test & Lint" job.

1. Run `ruff check --fix` and `ruff format` with the CI-pinned `ruff==0.6.3`.
2. Fix the remaining errors by hand. Flag any that are real bugs; undefined names have already
   turned out to be real crashes twice.
3. For bandit: fix real issues. Use `# nosec` only with a one-line justification.

This touches many files, which is why it waits until the other branches are merged.
