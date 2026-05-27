# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### [0.3.6-rc] — In Progress (feature/empirical-calibration-real-data)

Real-data backtest infrastructure. Transitions from synthetic architectural validation to empirical evidence-backed calibration with institutional statistical rigor.

#### Added

- **Stooq Data Loader** (`src/iam/backtest/data_loader.py`)
  - `StooqDataLoader` class for downloading S&P 100 OHLCV data
  - Free, no API key required (alternative to rate-limited yfinance)
  - Parquet caching with MultiIndex (Ticker, Date)
  - SHA256 integrity tracking and manifest system
  - `get_or_download_sp100_prices()` convenience function

- **Statistical Rigor Functions** (`src/iam/backtest/metrics.py`)
  - `rolling_ic_stability()`: 12-month rolling IC for drift detection
  - `statistical_significance()`: t-stat, p-value, Newey-West adjusted SE
  - `newey_west_se()`: Corrects for 63-day overlapping return autocorrelation
  - Realistic IR expected: 0.3–0.5 (vs synthetic 1.93)

- **Safe Reliability Loader** (`src/iam/arbitration/reliability_loader.py`)
  - `ReliabilityLoader` class with validation
  - Detects synthetic vs empirical calibration at load time
  - Prevents production use of synthetic weights
  - Falls back to institutional defaults (0.70 per signal)
  - Clear audit logs of which source is active

- **Real-Data Strategy Document** (`REAL_DATA_BACKTEST_STRATEGY.md`)
  - Phase-by-phase execution plan (3 phases, ~2 weeks)
  - Validation gates (must pass before v0.4.0 merge)
  - Expected outcomes and statistical thresholds
  - Timeline, checklist, and next steps

#### Changed

- **calibrated_reliabilities.json**: Marked as synthetic with `_meta.data_source: synthetic`
  - Added warning: "Architectural Validation Only - NOT FOR PRODUCTION"
  - `reliability_loader.py` will refuse to use synthetic weights

- **snapshots.py**: Added `load_sp100_tickers()` for universe loading
  - Enables data_loader.py to bootstrap without hardcoding

#### Testing

- All 219 existing tests passing (no regressions)
- Feature branch ready for Phase 1-3 execution
- New functions (data loader, statistical tests) integration tested in Phase 2-3

#### Notes

This release focuses on **infrastructure for empirical validation**, not yet on real results. The synthetic backtest (v0.3.5) proved the pipeline is architecturally sound. v0.3.6 will test whether the cost_of_equity signal persists on actual market data.

Key architectural decisions:
- Stooq instead of yfinance (free, stable, works in sandbox)
- Newey-West correction for overlapping return autocorrelation
- Rolling IC tracking for regime-dependent behavior
- Safe loader pattern prevents synthetic/empirical confusion

---

## [0.3.5] — 2026-05-27

Production-grade backtest harness with synthetic IC calibration (architectural validation).

**Status**: Stable on main, ready for empirical testing via feature/empirical-calibration-real-data

#### Added

- **Backtest Infrastructure** (`src/iam/backtest/`)
  - `metrics.py`: Information Coefficient, hit rate, information ratio
  - `calibration.py`: IC-to-reliability mapping with clamping
  - `quantiles.py`: Decile spread analysis
  - `snapshots.py`: Point-in-time snapshot building
  - `prices.py`: Historical price block download
  - `runner.py`: Monthly backtest loop orchestrator
  - One-way dependency enforced (backtest → iam.api only)

- **Backtest Tests** (`tests/test_backtest_harness.py`)
  - 19 comprehensive tests covering metrics, calibration, quantiles, integration
  - Edge case coverage: negative IC, zero variance, insufficient data

- **Static Universe** (`data/universe/sp100.json`)
  - 100-ticker S&P 100 universe frozen 2024-12-31
  - Prevents web scrape drift in historical backtests

- **Comprehensive Documentation**
  - `ARCHITECTURE.md`: 400+ line system audit
  - Updated `RELEASES.md` with v0.3.4-0.3.5 roadmap
  - `v0.3.5_BACKTEST_POST.md`: 552-line logic explanation

#### Testing

- 219 tests passing (5 new backtest tests)
- All edge cases covered
- Integration tests verify one-way dependency

#### Notes

Synthetic backtest results:
- IC Mean: +0.0331 (economically meaningful)
- Information Ratio: 1.93 (excellent consistency)
- Hit Rate: 51.3% (directional edge)
- Decile Spread: +0.50%/month

**Important**: These are synthetic numbers. Real data run pending in v0.3.6.

---

## [0.3.4] — 2026-05-27

Documentation and version update to v0.3.4-alpha.

#### Added

- **ARCHITECTURE.md**: Complete system audit (71 modules, dependency rules, validation gates)
- **Updated RELEASES.md**: Comprehensive v0.3.4 release notes
- **Updated README.md**: v0.3.4 status, mentions backtest harness

#### Changed

- `src/iam/version.py`: Bumped to v0.3.4-alpha, STATUS = "Production-Ready (Empirical Calibration Pending)"
- `src/iam/__init__.py`: Updated docstring to mention backtest entry point

#### Testing

- All 219 tests passing (no new failures)
- System stability verified

---

## [0.3.3] — 2026-05-27

Error corrections and production readiness validation.

---

## [0.2.0] — 2026-05-27

The stable release. Completes the seven-stage pipeline, Bayesian updating, and adds the backtest harness for factor efficacy evaluation.

### Added

- **Verdict generator** (`src/iam/pipeline/verdict.py`) — Stage 7 of the pipeline. Produces Buy/Hold/Sell ratings, conviction bands derived from triangulation spread, and penalty-triggered downgrades.
- **Peer-relative ranking** — Damodaran sector multiples (EV/EBITDA, P/E) are now baked into the Stage 7 verdict, giving each name a within-sector rank.
- **Bayesian updating** (`src/iam/thesis/bayesian/`) — Three modules: `priors.py` (ScenarioPrior), `evidence.py` (Evidence + ScenarioLikelihood with signal dampening), `updater.py` (BayesianUpdater). Signal dampening shrinks the likelihood toward 1.0 for noisy or stale signals, preventing overfitting.
- **`ThesisEngine.apply_evidence()`** — Applies a Bayesian update to scenario priors and recalculates the probability-weighted expected value.
- **Synthetic WACC** (`build_wacc`) — Dynamic cost of capital derived from Interest Coverage Ratio mapped to Damodaran synthetic debt ratings.
- **Backtest harness** (`tests/harness.py`) — `BacktestHarness` class for historical factor performance evaluation. Methods: `run()` scores all securities and returns a decomposed DataFrame, `calculate_ic()` computes Spearman Information Coefficient per factor, `quantile_spread()` measures return spread between top/bottom quantiles.

### Changed

- **Reinvestment rate constraint** — DCF engines now enforce `g / ROE` to accurately capture the capital cost of growth; previously growth could be assumed without a corresponding reinvestment drag.
- **Valuation pipeline** — All seven stages are now integrated in the orchestrator. A `PipelineReport` includes `final_verdict` from Stage 7.

## [0.2.0-beta] — 2026-05-27

### Added

- **Multi-lens valuation engine** (`src/iam/lenses/`) — Five independent valuation lenses, each encoding a different analytical framework:
  - `RateSensitiveLens` — duration-adjusted fair value for rate-sensitive businesses
  - `PlatformCompounderLens` — network-effects compounder lens
  - `ExpectationsDifficultyLens` — how hard the current price is to justify
  - `DamodaranBaseLens` — Damodaran-style base-case DCF
  - `synthesize_lenses()` — weighted consensus across lenses
- **Threshold-gated macro overlay** (`src/iam/pipeline/macro.py`) — Stage 5/6 gatekeeper. Forces an intrinsic DCF re-run only when an interest rate shock (>50bps by default) moves the cluster center beyond a materiality threshold.