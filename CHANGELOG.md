# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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