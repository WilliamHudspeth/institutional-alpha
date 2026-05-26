# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0a0] — v0.2.0-alpha

### Added

- **Valuation pipeline** (`iam.ValuationPipeline`) — a sequential Stage 1–4 flow that produces a structured argument rather than a single composite score.
  - **Stage 1: Reverse DCF** (`iam.valuation.ReverseDCF`). Two-stage Gordon-growth FCFE model. Bisects to find the implied growth rate the market is demanding, then compares to historical peak.
  - **Stage 2: Relative valuation** (`iam.valuation.RelativeValuation`). Three signals: EV/EBITDA vs sector median, P/E vs own 10y history percentile, FCF yield vs peer set.
  - **Stage 3: Intrinsic DCF** (`iam.valuation.FCFEDCF`) and **SOTP scaffold** (`iam.valuation.SOTP`). Independent fair-value build-up using user-supplied or default forecasts.
  - **Stage 4: Triangulation** (`iam.valuation.Triangulator`). Closest-cluster-wins logic. Verdicts: `agree` / `two_of_three` / `disagree` / `single_method` / `no_data`.
- `docs/pipeline.md` — design doc for the pipeline.
- `examples/pipeline_one.py` — runnable end-to-end demo of the pipeline.
- 17 new tests covering the math, each method, and the triangulation logic.

### Changed

- `iam.__version__` is now `"0.2.0a0"`.
- README updated with two-entry-point quickstart and revised roadmap.

### Notes

- v0.1.0's factor-scoring engine (`iam.score`) is unchanged and fully backwards-compatible. All 9 original tests still pass.
- Stages 5–7 (macro overlay, verdict, peer-relative ranking) ship in v0.2.0-beta and v0.2.0.

## [0.1.0] — Initial scaffold

### Added

- 10 additive factors and 3 penalty factors.
- Composite engine with confidence-weighted, decomposable scoring.
- Conceptual framework (`docs/framework.md`) and per-factor definitions (`docs/factors.md`).
- 9-test test suite.
- `examples/score_one.py` runnable demo.
- MIT license, CONTRIBUTING.md, pyproject.toml.
