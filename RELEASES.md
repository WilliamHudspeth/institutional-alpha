# Institutional Alpha — Release Notes

Release-by-release summary of what shipped, why it shipped, and what's pending. For commit-level history see [CHANGELOG.md](CHANGELOG.md). For architectural detail see [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Release Matrix

| Version | Focus | Tests | Status |
|---|---|---|---|
| **v0.4.0-rc1** | Hardened backtest stack: pluggable sources, Polars, ProcessPool, Bayesian shrinkage | 355 | **Current** (feature/empirical-calibration-real-data) |
| v0.3.6-rc | Real-data infrastructure: Stooq loader, Newey-West, safe reliability loader | 219 | Rolled into v0.4.0-rc1 |
| v0.3.5 | Synthetic backtest harness, IC calibration framework | 219 | Tagged `v0.3.5-synthetic-harness` |
| v0.3.4 | Architecture audit, version metadata, RELEASES.md baseline | 219 | Tagged |
| v0.3.3 | Error corrections, production readiness | 159 | Tagged |
| v0.3.2 | Ground Truth Provider, FCFE DCF integration | All passing | Tagged |
| v0.3.1 | Damodaran Provider (unlevered betas, implied ERP, country risk) | All passing | Tagged |
| v0.3.0 | SQLite caching, normalization layer | All passing | Tagged |
| v0.2.0 | 7-stage pipeline complete, Bayesian engine, BacktestHarness v1 | All passing | Tagged |

---

## v0.4.0-rc1 — Hardened Backtest Stack

**Release candidate.** Promotes to v0.4.0 after one successful empirical IC run passes the validation gates documented in [REAL_DATA_BACKTEST_STRATEGY.md](REAL_DATA_BACKTEST_STRATEGY.md).

### Why this release

v0.3.5 proved the backtest pipeline was architecturally clean but ran on synthetic data, producing an Information Ratio of 1.93 that is not credible in real markets (typical equity IRs are 0.3–0.5). v0.3.6-rc added a Stooq fallback and statistical helpers but kept the snapshot layer tightly coupled to yfinance.

v0.4.0-rc1 replaces all of that with an institutional-grade harness. The data layer is now pluggable, the price block is Polars-backed, scoring runs on a ProcessPool, statsmodels HAC covariance replaces the simplified Newey-West, and calibration uses Bayesian shrinkage so short backtests don't produce overconfident reliability weights.

### What's new

**Pluggable data source layer** (`src/iam/backtest/sources/`)
- `DataSource` abstract contract: `fetch_price`, `fetch_debt`, `download_history`
- `YFinanceSource` — primary, includes quarterly balance sheet for debt
- `StooqSource` — free CSV-export fallback, sandbox-compatible
- `CompositeDataSource` — chains sources with first-success fallback, tracks `last_used` for audit
- `default_chain()` — pre-built yfinance → Stooq chain
- Adding a new source (FMP, Tiingo, custom CSV) requires implementing three methods; no changes to snapshots or runner

**Institutional metrics** (`src/iam/backtest/metrics.py`)
- `ic_sector_neutral()` — stratify IC by sector, weighted average; detects sector-timing in disguise
- `newey_west_se_rigorous()` — statsmodels OLS + HAC covariance, replaces the simplified approximation
- `fisher_mean()` — Fisher z-transform for proper correlation averaging
- `information_coefficient(sector_col=...)` — optional sector neutralization

**Cost-aware quantiles** (`src/iam/backtest/quantiles.py`)
- `quantile_turnover()` — fraction of positions that changed decile between dates
- `spread_after_costs()` — adjusts decile spread for round-trip transaction drag

**Bayesian shrinkage calibration** (`src/iam/backtest/calibration.py`)
- `ic_to_reliability_bayesian()` — `posterior = (prior_strength · prior + n · empirical) / (prior_strength + n)`
- Default prior: `prior_ic = 0.02`, `prior_strength = 36` months
- Prevents overfitting on short-history backtests
- Linear `ic_to_reliability()` preserved for backward compatibility

**Production infrastructure**
- `src/iam/backtest/config.py` — frozen Pydantic `BacktestConfig` with computed path properties
- `src/iam/backtest/manifest.py` — git SHA + file hashes + config dump for reproducibility audit
- `src/iam/backtest/universe.py` — static universe loader with content hash
- `src/iam/backtest/cli.py` — Typer CLI: `python -m iam.backtest.cli backtest`
- `src/iam/backtest/snapshots.py` — diskcache-backed PIT snapshots (was pickle); accepts injected DataSource
- `src/iam/backtest/prices.py` — Polars parquet loader with pre-computed forward returns
- `src/iam/backtest/runner.py` — ProcessPoolExecutor parallel scoring (~4–6× speedup)
- `scripts/build_price_parquet.py` — one-shot price-data build (yfinance → Stooq fallback)

### Bugs caught by testing

The new test suites caught three real bugs that would have produced silent or confusing failures:

1. **yfinance debt column ordering.** `quarterly_balance_sheet` returns columns in descending date order. The original `cols[-1]` was picking the oldest quarterly debt instead of the latest. Fixed with explicit `sorted()`.
2. **Manifest JSON serialization.** Pydantic `model_dump()` returns `PosixPath` objects that `json.dump` cannot serialize. Fixed with stringification + `default=str`.
3. **Universe loader Security construction.** `Security` doesn't accept `shares_outstanding` directly — it lives on `Security.fundamentals`. Fixed by routing the field through the dataclass.

### Test coverage

- **355 tests passing** (was 219)
- New suites: `test_backtest_sources.py` (38), `test_backtest_snapshots_v04.py` (13), `test_backtest_config.py` (15), `test_backtest_manifest.py` (10), `test_backtest_universe.py` (10), `test_backtest_metrics_v04.py` (24), `test_backtest_quantiles_v04.py` (11), `test_backtest_calibration_v04.py` (14)
- One-way dependency rule preserved: `iam.backtest` imports only `iam.api.value_security()`

### Dependencies added

The `[backtest]` extra installs: `polars`, `diskcache`, `tenacity`, `statsmodels`, `typer`, `pydantic`, `tqdm`.

### What gates the v0.4.0 promotion

1. Build the price parquet (`python scripts/build_price_parquet.py`)
2. Run the empirical backtest (`python -m iam.backtest.cli backtest`)
3. Pass the validation gates in [REAL_DATA_BACKTEST_STRATEGY.md](REAL_DATA_BACKTEST_STRATEGY.md):
   - Data integrity: ≥75 of 100 tickers downloaded, no gaps, debt values reasonable
   - Statistical validity: IC mean > 0.01, IR > 0.3, t-stat > 1.5, rolling IC stable
   - Architectural soundness: sector-neutral IC ≈ global IC, turnover < 40%/month
4. Write `calibrated_reliabilities_empirical.json` with the Bayesian posterior
5. Tag `v0.4.0` and merge to `main`

---

## v0.3.6-rc — Real-Data Infrastructure (rolled into v0.4.0-rc1)

**Status:** Superseded by v0.4.0-rc1. The data_loader and reliability_loader added here are still in tree; the snapshots/metrics changes were re-implemented in the v0.4 hardened stack.

### Scope

Transitioned the harness from synthetic to real-data capable.

### What was added

- `src/iam/backtest/data_loader.py` — Stooq downloader, parquet caching, SHA256 integrity tracking, manifest system
- `src/iam/arbitration/reliability_loader.py` — safe loader that detects `data_source: synthetic` and refuses production use, falls back to institutional defaults (0.70 per signal)
- `src/iam/backtest/metrics.py` — added `rolling_ic_stability()`, `statistical_significance()`, simplified `newey_west_se()`
- `src/iam/backtest/snapshots.py` — `load_sp100_tickers()` helper
- `src/iam/arbitration/calibrated_reliabilities.json` — explicitly marked `_meta.data_source: synthetic` with warning
- `REAL_DATA_BACKTEST_STRATEGY.md` — three-phase execution plan with validation gates

### Why it mattered

The synthetic IC of 0.0331 with IR 1.93 was architecturally correct but empirically unrealistic. v0.3.6-rc separated "architecture proof" from "empirical proof" so the model couldn't quietly use synthetic weights in production.

---

## v0.3.5 — Synthetic Backtest Harness

**Tag:** `v0.3.5-synthetic-harness`. **Tests:** 219 passing.

### Scope

Production-grade historical backtest framework. Architectural validation only — synthetic data.

### What shipped

- `src/iam/backtest/metrics.py` — Spearman IC, hit rate, information ratio with NaN handling
- `src/iam/backtest/calibration.py` — `ic_to_reliability()` = `0.5 + clamp(IC · 5, −0.5, 0.45)`, clamped to [0.5, 0.95]
- `src/iam/backtest/quantiles.py` — decile spreads with tie/sparse-data handling and coverage metric
- `src/iam/backtest/snapshots.py` — PIT snapshots cached as pickle files
- `src/iam/backtest/prices.py` — historical price block download with forward returns
- `src/iam/backtest/runner.py` — monthly loop orchestrator, treats `value_security()` as a black box
- `data/universe/sp100.json` — 100-ticker S&P 100 universe frozen 2024-12-31
- `tests/test_backtest_harness.py` — 19 comprehensive tests

### Results (synthetic)

- IC mean: +0.0331
- IC std: 0.017
- Information Ratio: 1.93
- Hit rate: 51.3%
- Decile spread: +0.50%/month

These numbers proved the pipeline was sound, not that the signal works on real markets. The v0.3.6-rc work explicitly flagged them as synthetic to prevent accidental production use.

---

## v0.3.4 — Architecture Audit

**Tests:** 219 passing.

### Scope

- `ARCHITECTURE.md` — 400+ line system audit: 71 modules, dependency rules, validation gates
- `RELEASES.md` — comprehensive baseline release notes
- `src/iam/version.py` — bumped to v0.3.4-alpha
- `src/iam/__init__.py` — updated docstring with backtest entry point

---

## v0.3.3 — Error Corrections

**Tests:** 159 passing.

### What was fixed

- `fetch_security()` math fallbacks restored: PE → Net Income, EV/EBITDA → EBITDA TTM, Operating Cash Flow × 0.8 → FCF heuristic
- Bayesian API migration: `signal_strength` → `reliability` on `Evidence`, plus required `type` parameter
- FCFE DCF baseline updated: expects 8.16% institutional rate (was 9% default)
- Numerical precision tolerances tightened

---

## v0.3.2 — Ground Truth Integration

### Scope

- `GroundTruthProvider` — single source of truth for institutional assumptions (`get_equity_risk_profile`, `get_wacc`)
- FCFE DCF cost-of-equity hierarchy: custom CAPM → Damodaran baseline → forecast rate
- `DamodaranProvider` and `MacroBaselines` exported from `iam.data`

The institutional edge: unlevered industry betas + current D/E, instead of a noisy 5-year regression beta.

---

## v0.3.1 — Damodaran Provider

### Scope

- Unlevered industry betas (0.4–1.2 by sector, 20+ sectors)
- Country risk premiums (US/EU/JP 0%, China 1.5%, India 2%, Brazil 2.5%)
- Implied ERP (4.6%, updated monthly by Damodaran)
- Re-levering formula: `levered = unlevered × (1 + (1 − tax) × D/E)`

---

## v0.3.0 — Caching Layer

### Scope

- SQLite caching for Yahoo Finance (first fetch 2–3 s, cache hit 20 ms)
- Seed cache strategy: `seed_cache.sqlite` tracked in git, `iam_cache.sqlite` ignored at runtime
- `YahooAdapter.fetch_and_normalize()` — maps Yahoo's chaotic schema to clean IAM schema with validation and graceful degradation
- Seed data for BlackRock, Apple, Johnson & Johnson

---

## v0.2.0 — Pipeline & Bayesian Engine

### Scope

The stable foundation. Completes the 7-stage pipeline, the Bayesian thesis engine, and the first backtest harness.

- **Verdict generator** (`src/iam/pipeline/verdict.py`) — Stage 7. Buy/Hold/Sell, conviction bands from triangulation spread, penalty-triggered downgrades.
- **Peer-relative ranking** — Damodaran sector multiples baked into Stage 7
- **Bayesian updating** (`src/iam/thesis/bayesian/`) — `priors.py`, `evidence.py` with signal dampening, `updater.py`
- **`ThesisEngine.apply_evidence()`** — Bayesian update to scenario priors with recalculated expected value
- **Synthetic WACC** (`build_wacc`) — dynamic cost of capital from Interest Coverage Ratio mapped to Damodaran synthetic debt ratings
- **Backtest harness v1** (`tests/harness.py`) — `BacktestHarness.run()`, `calculate_ic()`, `quantile_spread()`
- **Reinvestment rate constraint** — DCF engines enforce `g / ROE` to capture capital cost of growth
- All seven pipeline stages integrated; `PipelineReport.final_verdict` exposed

---

## What comes next (post-v0.4.0)

1. **Multi-horizon IC** — Measure at 21d, 63d, 126d, 252d to identify the natural decay horizon of each signal
2. **Factor attribution** — Run the backtest one factor at a time, identify redundant signals (correlation > 0.80), build a factor correlation matrix
3. **Additional data sources** — FMP and Tiingo adapters via the `DataSource` contract
4. **Regime-dependent calibration** — Separate IC for bull/bear/sideways regimes
5. **Out-of-sample tracking** — Reserve 2025 data as a true test set, set up monthly IC drift alerts
6. **International expansion** — Country risk premium adjustments, multi-currency valuation

---

## Git tags

```bash
git tag -l
# v0.3.0  — Data layer caching
# v0.3.1  — Damodaran provider
# v0.3.2  — Ground Truth integration
# v0.3.3  — Error corrections
# v0.3.4  — Architecture audit
# v0.3.5-synthetic-harness  — Synthetic backtest validation
# v0.4.0-rc1  — Hardened backtest stack (current)
```

---

## References

- [`README.md`](README.md) — overview, quick start, method explanation
- [`CHANGELOG.md`](CHANGELOG.md) — commit-level history in Keep-a-Changelog format
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — module map, dependency rules
- [`REAL_DATA_BACKTEST_STRATEGY.md`](REAL_DATA_BACKTEST_STRATEGY.md) — empirical validation plan
- [`docs/framework.md`](docs/framework.md) — orthogonality, composite formula
- [`docs/factors.md`](docs/factors.md) — every factor's definition and weights
- [`docs/pipeline.md`](docs/pipeline.md) — the seven pipeline stages in depth
