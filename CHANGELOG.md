# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Awaiting: empirical IC run on real S&P 100 data. Once it passes the validation gates in [REAL_DATA_BACKTEST_STRATEGY.md](docs/REAL_DATA_BACKTEST_STRATEGY.md), v0.4.0-rc1 is promoted to v0.4.0.

---

## [0.4.0-rc1] — 2026-05-27 / 2026-05-28

Hardened backtest stack with documentation, UI, and project-structure refinements. Pluggable data sources, Polars-backed price block, ProcessPool parallel scoring, statsmodels Newey-West, sector-neutral IC, Bayesian shrinkage calibration, typographic terminal UI, and a src-layout root cleanup. **Test count: 355.**

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

### Documentation

- **README.md** rewrite. New "How it actually works" section in three layers (simple → complex):
  - Layer 1 (plain English): the model scores, valuates, and tests itself
  - Layer 2 (how pieces fit): composite formula, pipeline stages, thesis engine, backtest IC
  - Layer 3 (math + audit trail): Bayesian shrinkage formula, Newey-West HAC, sector-neutral IC, the `DataSource` contract, manifest reproducibility
- Updated architecture tree to surface `sources/`, `config.py`, `manifest.py`, `cli.py`. Added `pip install -e ".[backtest]"` and a CLI quick-start (`python -m iam.backtest.cli backtest`).
- **RELEASES.md** rewrite. Release matrix at top showing current → stable history. v0.4.0-rc1 section documents what shipped, why, and the gates that promote it to v0.4.0. v0.3.6-rc marked as rolled into v0.4.0-rc1.
- **CHANGELOG.md** rewrite to strict Keep-a-Changelog format with Added / Changed / Fixed sections. v0.4.0-rc1 Fixed section explicitly names the three bugs caught by testing.
- **CLAUDE.md** architecture map expanded so an agent landing fresh in the repo immediately knows where everything lives: `scripts/`, `docs/`, `data/` subdirectories all enumerated with one-line purposes.
- Cross-references updated everywhere to point at the new `docs/` and `scripts/` paths.

### User interface (terminal)

- **`src/iam/ui/institutional_terminal.py`** rewritten in the clean typographic style:
  - Removed all `┌─┐│└┘` box-drawing characters
  - Single `=` rule at top and bottom of each report; thin `-` separator after the executive summary
  - Bracketed section headers (`[ CORE ASSUMPTIONS ]`, `[ PROBABILISTIC SCENARIO MATRIX ]`, `[ COMPONENT SIGNALS ]`)
  - Executive-summary colons all align at one column
  - Scenario matrix renders as a whitespace-aligned columnar grid (no vertical bars), survives long stock names without warping
  - Header pulls `VERSION` from `iam.version` instead of hardcoding it
  - `print_pipeline_summary()` and `print_bayesian_update_summary()` also rewritten in the new style
  - All three public function signatures preserved — `examples/terminal_ui_example.py` works unchanged
  - Added `_fmt_currency()` and `_fmt_pct_signed()` helpers with TypeError/ValueError fallbacks so malformed inputs render as `$—` / `—` instead of crashing

- **`run.py`** rewritten to run engines silently and dispatch a single unified render:
  - Four-step pipeline: input → silent fetch → silent engines → single `print_institutional_ui()` call
  - New private helpers:
    - `_classify_signal(upside)` maps fractional upside to `BULLISH (+X.X%)` / `NEUTRAL (+X.X%)` / `BEARISH (-X.X%)` using a ±5% threshold so noise doesn't look bullish
    - `_build_scenarios(components)` extracts the probabilistic matrix from `report.intrinsic.components["scenarios"]` (Bear/Base/Bull at 20/60/20 from `FCFEDCF`)
    - `_gather_lens_results(security)` runs all 4 lenses + `synthesize_lenses` inside try/except
    - `_gather_pipeline_report(security, synthesis_upside)` runs `ValuationPipeline.run()` inside try/except
    - `_build_ui_data(...)` pulls PWEV, WACC, terminal growth, verdict, and confidence from real `PipelineReport` attributes (no placeholders)
  - Macro overlay status text-mined from `report.summary`
  - Lens failure non-fatal; pipeline failure fatal with exit 1

- **`src/iam/pipeline/orchestrator.py`** assumption table split:
  - New `format_assumption_table()` returns a string in the typographic style with no side effects
  - `print_assumption_table()` becomes a thin wrapper that prints the formatted string (backward-compatible — `main.py` keeps working)

### Project structure (src-layout root cleanup)

Root used to contain 3 markdown docs, 3 utility scripts, a results CSV, two SQLite caches at depth zero — anyone landing on the GitHub page had to guess what was config, what was code, what was an artifact. Re-applied the src-layout standard:

**Moves** (all via `git mv`, history preserved 98–100%):

| From | To |
|---|---|
| `analyze.py` | `scripts/analyze.py` |
| `quick_recommend.py` | `scripts/quick_recommend.py` |
| `backtest_runner.py` | `scripts/backtest_runner.py` |
| `ARCHITECTURE.md` | `docs/ARCHITECTURE.md` |
| `REAL_DATA_BACKTEST_STRATEGY.md` | `docs/REAL_DATA_BACKTEST_STRATEGY.md` |
| `v0.3.5_BACKTEST_POST.md` | `docs/v0.3.5_BACKTEST_POST.md` |
| `seed_cache.sqlite` | `data/cache/seed_cache.sqlite` (still tracked) |
| `iam_cache.sqlite` | `data/cache/iam_cache.sqlite` (now gitignored) |
| `backtest_results_v0.3.5.csv` | `data/results/backtest_results_v0.3.5.csv` |

**`src/iam/data/yahoo.py`**: centralized cache locations into `SEED_CACHE_PATH` and `RUNTIME_CACHE_PATH` module constants. All four hardcoded `"iam_cache.sqlite"` strings replaced. `_init_cache_db()` now `os.makedirs` the cache directory on first run so a fresh checkout works automatically.

**`.gitignore`** rewritten with a layered approach:

```
/data/**                                # ignore everything by default
!/data/, !/data/cache/, !/data/results/, !/data/universe/  # re-allow dirs
!/data/cache/seed_cache.sqlite          # explicit track
!/data/results/backtest_results_v0.3.5.csv
!/data/universe/*.json
/*.csv, /*.parquet, /*.xlsx, /*.sqlite  # root-level dump guard
.cache/                                  # diskcache working dir
```

This keeps the Seed Database Strategy (v0.3.0) intact — new clones still get a warm cache — while everything else under `data/` is local-only.

**Root after cleanup** contains only project-config and onboarding:
- Entries: `main.py`, `run.py`
- Onboarding: `README.md`, `RELEASES.md`, `CHANGELOG.md`, `ROADMAP.md`, `CONTRIBUTING.md`, `CLAUDE.md`, `LICENSE`
- Config: `pyproject.toml`, `.gitignore`
- Code: `src/`, `tests/`, `scripts/`, `examples/`, `docs/`, `data/`

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
