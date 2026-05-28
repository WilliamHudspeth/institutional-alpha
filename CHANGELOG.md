# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Awaiting: empirical IC run on real S&P 100 data. Once it passes the validation gates in [REAL_DATA_BACKTEST_STRATEGY.md](docs/REAL_DATA_BACKTEST_STRATEGY.md), v0.4.0-rc1 is promoted to v0.4.0.

---

## [0.4.0-rc1] — 2026-05-27

Hardened backtest stack. Pluggable data sources, Polars-backed price block, ProcessPool parallel scoring, statsmodels Newey-West, sector-neutral IC, and Bayesian shrinkage calibration. **Test count: 355.**

### Added

- **Pluggable data source layer** (`src/iam/backtest/sources/`)
  - `DataSource` abstract contract (`base.py`): `fetch_price`, `fetch_debt`, `download_history`
  - `YFinanceSource` (`yfinance_source.py`): primary, with quarterly balance sheet for debt
  - `StooqSource` (`stooq_source.py`): free CSV-export fallback, sandbox-safe
  - `CompositeDataSource` (`composite.py`): first-success fallback chain with `last_used` audit
  - `default_chain()` builder: pre-built yfinance → Stooq chain

- **Backtest configuration & reproducibility**
  - `src/iam/backtest/config.py`: frozen Pydantic `BacktestConfig` with computed path properties
  - `src/iam/backtest/manifest.py`: git SHA + file hash + config dump
  - `src/iam/backtest/universe.py`: static universe loader with content hash
  - `src/iam/backtest/cli.py`: Typer CLI (`python -m iam.backtest.cli backtest`)
  - `scripts/build_price_parquet.py`: one-shot price builder with fallback chain

- **Institutional metrics** (`src/iam/backtest/metrics.py`)
  - `ic_sector_neutral()`: stratify IC by sector with size-weighted average
  - `newey_west_se_rigorous()`: statsmodels OLS with HAC covariance
  - `fisher_mean()`: Fisher z-transform correlation averaging
  - `information_coefficient(sector_col=...)`: optional sector neutralization

- **Cost-aware quantiles** (`src/iam/backtest/quantiles.py`)
  - `quantile_turnover()`: position changes between dates
  - `spread_after_costs()`: decile spread adjusted for round-trip transaction drag

- **Bayesian shrinkage calibration** (`src/iam/backtest/calibration.py`)
  - `ic_to_reliability_bayesian()`: posterior = (prior_strength·prior + n·empirical) / (prior_strength + n)
  - Defaults: `prior_ic = 0.02`, `prior_strength = 36` months
  - Returns full diagnostics: prior, empirical, posterior, shrinkage_factor

- **Test suites** (+136 tests)
  - `tests/test_backtest_sources.py` (38): base contract, yfinance/Stooq mocked, Composite fallback
  - `tests/test_backtest_snapshots_v04.py` (13): source injection, diskcache, fallback integration
  - `tests/test_backtest_config.py` (15): Pydantic validation, path creation
  - `tests/test_backtest_manifest.py` (10): git SHA, file hashes, JSON roundtrip
  - `tests/test_backtest_universe.py` (10): both JSON formats, hash stability
  - `tests/test_backtest_metrics_v04.py` (24): sector-neutral IC, rigorous Newey-West, Fisher mean
  - `tests/test_backtest_quantiles_v04.py` (11): turnover, cost-adjusted spread
  - `tests/test_backtest_calibration_v04.py` (14): Bayesian shrinkage, prior convergence

### Changed

- **`src/iam/backtest/snapshots.py`**: rewrote to delegate fetching to injected `DataSource`. Storage moved from per-ticker pickle files to `diskcache` (thread-safe, SQLite-backed). Added `get_default_source()` / `set_default_source()` / `reset_snapshot_cache()` helpers.
- **`src/iam/backtest/prices.py`**: replaced pandas-based `get_price_block()` with Polars-based `load_price_block()`. Forward returns are now pre-computed at parquet build time.
- **`src/iam/backtest/runner.py`**: parallel scoring via `ProcessPoolExecutor` (n_jobs_cpu workers). Now accepts pre-loaded price block. Output includes `ic_sector_neutral` column.
- **`src/iam/backtest/__init__.py`**: exposed all v0.4 additions in public API.
- **`pyproject.toml`**: added `[backtest]` optional dependency group (polars, diskcache, tenacity, statsmodels, typer, pydantic).
- **`src/iam/version.py`**: bumped to `0.4.0-rc1`.

### Fixed

- **yfinance debt column ordering** (`src/iam/backtest/sources/yfinance_source.py`): `quarterly_balance_sheet` returns columns in descending date order. The original `cols[-1]` silently picked the *oldest* debt value instead of the latest. Fixed by sorting columns ascending.
- **Manifest JSON serialization** (`src/iam/backtest/manifest.py`): Pydantic `model_dump()` returned `PosixPath` objects that `json.dump` refused to serialize. Fixed with explicit stringification + `default=str`.
- **Universe loader Security construction** (`src/iam/backtest/universe.py`): `Security` doesn't accept `shares_outstanding` directly — the field lives on `Security.fundamentals`. Fixed by routing through the dataclass.

### Testing

- 355 tests passing (was 219; +136 net new)
- One-way dependency rule preserved: `iam.backtest` imports only `iam.api.value_security()`
- Three real bugs caught and fixed during test development (above)

---

## [0.3.6-rc] — 2026-05-27

Real-data backtest infrastructure. Rolled into v0.4.0-rc1.

### Added

- **Stooq Data Loader** (`src/iam/backtest/data_loader.py`): `StooqDataLoader` class with parquet caching, SHA256 integrity tracking, manifest system; `get_or_download_sp100_prices()` convenience function.
- **Statistical helpers** (`src/iam/backtest/metrics.py`): `rolling_ic_stability()` (12-month rolling drift), `statistical_significance()` (t-stat + p-value), `newey_west_se()` (simplified autocorrelation correction). Note: the rigorous statsmodels version arrived in v0.4.0-rc1.
- **Safe reliability loader** (`src/iam/arbitration/reliability_loader.py`): `ReliabilityLoader` with `data_source` detection. Refuses to use synthetic calibration in production; falls back to institutional defaults (0.70 per signal).
- **Strategy document** (`docs/REAL_DATA_BACKTEST_STRATEGY.md`): three-phase plan with validation gates.

### Changed

- **`src/iam/arbitration/calibrated_reliabilities.json`**: marked `_meta.data_source: "synthetic"` with explicit "Architectural Validation Only — NOT FOR PRODUCTION" warning.
- **`src/iam/backtest/snapshots.py`**: added `load_sp100_tickers()` to bootstrap the universe.

### Testing

- 219 tests passing (no regressions)

---

## [0.3.5] — 2026-05-27

Synthetic backtest harness with IC calibration framework. **Tag:** `v0.3.5-synthetic-harness`.

Architectural validation only; synthetic data produced an Information Ratio of 1.93 which is not credible in real markets. Real calibration deferred to v0.4.0.

### Added

- **Backtest infrastructure** (`src/iam/backtest/`)
  - `metrics.py`: Spearman IC, hit rate, information ratio
  - `calibration.py`: IC-to-reliability mapping (`0.5 + clamp(IC·5, −0.5, 0.45)`)
  - `quantiles.py`: decile spreads with coverage tracking
  - `snapshots.py`: PIT snapshot builder, pickle cache
  - `prices.py`: historical price block download
  - `runner.py`: monthly orchestrator, `value_security()` as black box
- **Backtest tests** (`tests/test_backtest_harness.py`): 19 tests covering metrics, calibration, quantiles, and integration scenarios
- **Static universe** (`data/universe/sp100.json`): 100-ticker S&P 100 frozen 2024-12-31

### Notes

Synthetic results: IC mean +0.0331, IR 1.93, hit rate 51.3%, decile spread +0.50%/month. Architectural soundness proven; empirical validity not.

---

## [0.3.4] — 2026-05-27

Architecture audit and version metadata.

### Added

- `docs/ARCHITECTURE.md`: 400+ line system audit (71 modules, dependency rules, validation gates)
- `RELEASES.md`: comprehensive release history baseline
- Updated `README.md`: v0.3.4 status, mentions backtest harness

### Changed

- `src/iam/version.py`: bumped to `0.3.4-alpha`, `STATUS = "Production-Ready (Empirical Calibration Pending)"`
- `src/iam/__init__.py`: docstring updated with backtest entry point

### Testing

- 219 tests passing (no regressions)

---

## [0.3.3] — 2026-05-27

Error corrections and production readiness validation.

### Fixed

- `fetch_security()` math fallbacks restored: PE → Net Income, EV/EBITDA → EBITDA TTM, Operating Cash Flow × 0.8 → FCF
- Bayesian API: `Evidence.signal_strength` renamed to `reliability`; added required `type` parameter
- FCFE DCF baseline test updated to expect 8.16% institutional rate (was 9% default)
- Numerical precision tolerances adjusted

### Testing

- 159 tests passing

---

## [0.3.2] — 2026-05-27

Ground Truth Provider and FCFE DCF integration.

### Added

- `GroundTruthProvider` (`src/iam/data/ground_truth.py`): `get_equity_risk_profile()`, `get_wacc()`
- FCFE DCF cost-of-equity hierarchy: custom CAPM → Damodaran baseline → forecast rate
- `iam.data` public exports: `DamodaranProvider`, `MacroBaselines`, `GroundTruthProvider`, `EquityRiskProfile`

---

## [0.3.1] — 2026-05-27

Damodaran institutional baselines.

### Added

- `DamodaranProvider` (`src/iam/data/damodaran.py`)
- Unlevered industry betas (20+ sectors)
- Country risk premiums (developed and emerging)
- Implied ERP (forward-looking, vs. historical 5.5–6%)
- Re-levering formula: `levered = unlevered × (1 + (1 − tax) × D/E)`

---

## [0.3.0] — 2026-05-27

Data layer caching and normalization.

### Added

- SQLite caching for Yahoo Finance (first fetch 2–3 s, cache hit 20 ms)
- Seed cache strategy: `seed_cache.sqlite` tracked in git, `iam_cache.sqlite` ignored
- `YahooAdapter.fetch_and_normalize()`: chaotic Yahoo schema → clean IAM schema with validation
- Seed data: BlackRock (BLK), Apple (AAPL), Johnson & Johnson (JNJ)

---

## [0.2.0] — 2026-05-27

The stable release. Completes the seven-stage pipeline, Bayesian updating, and adds the backtest harness for factor efficacy evaluation.

### Added

- **Verdict generator** (`src/iam/pipeline/verdict.py`) — Stage 7: Buy/Hold/Sell ratings, conviction bands from triangulation spread, penalty-triggered downgrades
- **Peer-relative ranking** — Damodaran sector multiples (EV/EBITDA, P/E) baked into Stage 7
- **Bayesian updating** (`src/iam/thesis/bayesian/`) — `priors.py`, `evidence.py` (with signal dampening), `updater.py`
- **`ThesisEngine.apply_evidence()`** — Bayesian update to scenario priors with recalculated expected value
- **Synthetic WACC** (`build_wacc`) — dynamic cost of capital from Interest Coverage Ratio mapped to Damodaran synthetic debt ratings
- **Backtest harness v1** (`tests/harness.py`) — `BacktestHarness.run()`, `calculate_ic()`, `quantile_spread()`

### Changed

- **Reinvestment rate constraint** — DCF engines enforce `g / ROE` to capture the capital cost of growth
- **Valuation pipeline** — All seven stages integrated; `PipelineReport.final_verdict` from Stage 7

---

## [0.2.0-beta] — 2026-05-27

### Added

- **Multi-lens valuation engine** (`src/iam/lenses/`):
  - `RateSensitiveLens` — duration-adjusted fair value
  - `PlatformCompounderLens` — network-effects compounder
  - `ExpectationsDifficultyLens` — how hard the current price is to justify
  - `DamodaranBaseLens` — Damodaran-style base-case DCF
  - `synthesize_lenses()` — weighted consensus across lenses
- **Threshold-gated macro overlay** (`src/iam/pipeline/macro.py`) — forces an intrinsic DCF re-run only when an interest rate shock (> 50 bps default) moves the cluster center beyond a materiality threshold
