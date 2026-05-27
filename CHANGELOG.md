# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] — 2026-05-27

### Added
- **Bayesian Updating Engine** (`src/iam/thesis/bayesian/`) — Adaptive inference engine with signal dampening to update thesis probabilities based on new evidence.
- **Verdict Generator** (`src/iam/pipeline/verdict.py`) — Stage 7 of the pipeline producing actionable Buy/Hold/Sell ratings, conviction bands, and penalty downgrades.
- **Peer-Relative Ranking** — Integrated Damodaran sector multiples directly into the final pipeline verdict.
- **Synthetic WACC** — Dynamic cost of capital calculation (`build_wacc`) based on Interest Coverage Ratio mapping to Damodaran synthetic debt ratings.

### Changed
- **Reinvestment Rate Constraint** — DCF engines now enforce `g / ROE` capital constraints to accurately capture the cost of growth.
- **Valuation Pipeline** — Completely integrated Stages 1-7 (Reverse DCF, Relative, Intrinsic, Triangulation, Macro Overlay, Verdict).

## [0.2.0-beta] — 2026-05-27

### Added
- **Macro Overlay** (`src/iam/pipeline/macro.py`) — Threshold-gated gatekeeper that forces an Intrinsic DCF recalculation if interest rate shocks (>50bps) exceed tolerance.
- **Thesis Engine** (`src/iam/thesis/`) — Full scenario-based modeling with:
  - Cross-scenario validation (Bull > Bear).
  - `.simulate()` method for assumption perturbation.
  - `.render_report()` for actionable verdict generation.
- **Relative Valuation Engine** (`src/iam/valuation/relative.py`) — Peer-ranking logic using Damodaran sector median multiples (EV/EBITDA, P/E).
- **Data Adapters** (`src/iam/data/yahoo.py`) — Yahoo Finance integration for live fundamental/market data.

### Fixed
- **State Leakage** — Implemented `try...finally` logic in the pipeline to ensure state (like WACC overrides) is safely restored after each run.
- **Circular Imports** — Resolved import conflicts using `TYPE_CHECKING` blocks.
- **Data Robustness** — Added defensive `None` checks for all financial fields to prevent pipeline crashes on missing ticker data.

### Changed
- **Directory Structure** — Migrated core engine components to `src/iam/` for better package management.
- **Roadmap** — Moved Thesis Engine and Macro Overlay from "Remaining" to "Done."
