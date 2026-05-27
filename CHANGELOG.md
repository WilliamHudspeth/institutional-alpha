# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] — 2026-05-27

The stable release. Completes the seven-stage pipeline and wires Bayesian updating into the thesis engine.

### Added

- **Verdict generator** (`src/iam/pipeline/verdict.py`) — Stage 7 of the pipeline. Produces Buy/Hold/Sell ratings, conviction bands derived from triangulation spread, and penalty-triggered downgrades.
- **Peer-relative ranking** — Damodaran sector multiples (EV/EBITDA, P/E) are now baked into the Stage 7 verdict, giving each name a within-sector rank.
- **Bayesian updating** (`src/iam/thesis/bayesian/`) — Three modules: `priors.py` (ScenarioPrior), `evidence.py` (Evidence + ScenarioLikelihood with signal dampening), `updater.py` (BayesianUpdater). Signal dampening shrinks the likelihood toward 1.0 for noisy or stale signals, preventing overfitting.
- **`ThesisEngine.apply_evidence()`** — Applies a Bayesian update to scenario priors and recalculates the probability-weighted expected value.
- **Synthetic WACC** (`build_wacc`) — Dynamic cost of capital derived from Interest Coverage Ratio mapped to Damodaran synthetic debt ratings.

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
- **Threshold-gated macro overlay** (`src/iam/pipeline/macro.py`) — Stage 5/6 gatekeeper. Forces an intrinsic DCF re-run only when an interest rate shock (>50bps by default) moves the cluster center beyond a materiality threshold. Names below the threshold keep their original verdict untouched.
- **Thesis Engine** (`src/iam/thesis/engine.py`) — Full scenario-based modeling:
  - `ThesisEngine.evaluate()` — computes worst/best case range across all thesis scenarios
  - `ThesisEngine.simulate()` — injects each thesis's assumptions into the Security and re-runs a user-supplied valuation function to derive fair value ranges dynamically
  - `ThesisEngine.calculate_sensitivity()` — perturbs a named assumption and reports the before/after fair value impact per scenario
  - `ThesisEngine.render_report()` — generates a text verdict with dispersion rating, action signal, and probability distribution
- **Relative valuation engine** (`src/iam/valuation/relative.py`) — Peer-ranking using Damodaran sector median multiples. Three signals: EV/EBITDA vs sector median, P/E vs own 10-year percentile, FCF yield vs peers.
- **Yahoo Finance adapter** (`src/iam/data/yahoo.py`) — Pulls live fundamentals and market data from yfinance; installable via `pip install -e ".[live]"`.
- **Damodaran defaults** (`src/iam/valuation/damodaran_defaults.py`) — Lookup tables for sector median multiples and synthetic debt rating spreads.

### Fixed

- **State leakage** — Pipeline WACC overrides are now safely restored via `try…finally` after each run. Previously a pipeline crash could leave a modified WACC on the Security object.
- **Circular imports** — Resolved by moving forward-reference types into `TYPE_CHECKING` blocks.
- **Data robustness** — All financial fields now have explicit `None` guards throughout the pipeline; missing ticker data no longer causes a crash.
- **Thesis low/high validation** — `Thesis.__post_init__` now raises `ValueError` if `fair_value_low > fair_value_high`. `show_spread()` guards against inverted ranges.

### Changed

- **Directory structure** — Migrated `engine.py`, `evidence.py`, `priors.py`, `updater.py` from the repo root into `src/iam/thesis/bayesian/`. Import path is now `from iam.thesis.engine import ThesisEngine`.
- **`Assumption` and `Thesis` dataclasses** — Moved to `src/iam/data/security.py` as first-class data model types.

## [0.2.0-alpha] — 2026-05-26

First implementation of the valuation pipeline. Introduces a sequential alternative to the v0.1.0 parallel factor model.

### Added

- **Valuation pipeline Stages 1–4** (`src/iam/pipeline/`) — Sequential deep-dive on a single name:
  - Stage 1: Reverse DCF — solves for the implied FCFE growth rate that justifies the current price
  - Stage 2: Relative valuation — three independent peer/history signals
  - Stage 3: Intrinsic DCF — bottom-up FCFE model and SOTP for multi-segment businesses
  - Stage 4: Triangulation — clusters the three fair-value estimates; surfaces disagreement rather than averaging it away
- **Core valuation modules** (`src/iam/valuation/`) — `ReverseDCF`, `RelativeValuation`, `FCFEDCF`, `FCFEAssumptions`, `SOTP`, `Triangulator`, `ValuationResult`, `TriangulationResult`.
- **Core data layer** (`src/iam/data/`) — `Security`, `Fundamentals`, `MarketData`, `MacroContext`, `MacroConditions`. All pipeline stages accept these types; no data provider is assumed.
- **`PipelineReport`** — the structured output of a pipeline run, with `.explain()` for a human-readable breakdown.

## [0.1.0] — 2026-05-26

Initial public scaffold. Establishes the package structure, factor definitions, and composite scoring engine.

### Added

- **Ten orthogonal factor implementations** (`src/iam/factors/`) — Intrinsic Value, Expectations Difficulty, Quality, Relative Value, Sentiment, Reflexivity, Reinvestment Runway, Macro Regime, Crowding, Earnings Quality.
- **Three penalty factors** (`src/iam/factors/penalties.py`) — Fragility, Leverage, Execution Risk.
- **Composite scoring engine** (`src/iam/engine/composite.py`) — `score(security)` applies explicit default weights (documented in `docs/framework.md`) and returns a `ScoreResult` with per-factor breakdown and penalty detail.
- **`DEFAULT_WEIGHTS`** — exported from the top-level package; all weights are explicit constants, not hidden defaults.
- **Conceptual documentation** — `docs/framework.md` (why orthogonality matters, the composite formula), `docs/factors.md` (every factor's sub-components and default weights), `docs/pipeline.md` (pipeline design rationale).
- **Package setup** — `pyproject.toml` with optional `[data]` and `[live]` dependency groups, Python 3.10+ support.
- **CI** — GitHub Actions workflow (`python-package.yml`) running pytest across Python 3.10, 3.11, and 3.12.
