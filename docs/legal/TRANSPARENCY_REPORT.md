# Transparency Report

**Date**: 2026-07-06
**Version**: v0.4.0-rc1

> **Note**: This project is in early development (v0.4.0-rc1). The first formal transparency reporting cycle has not yet occurred. This document serves as a placeholder explaining the framework and intent for future reports.

---

## Purpose

Transparency reports will be published with each minor/major release (approximately quarterly) to provide stakeholders with:

1. **Model validation metrics** — Information Coefficient (IC), hit rates, factor-level performance
2. **Model change log** — Factor weight adjustments, rationale, and A/B test results
3. **Stress test results** — Performance across macro regimes, known edge cases
4. **Operational metrics** — Issue triage SLA adherence, security posture, dependency health

---

## Current Status (v0.4.0-rc1)

| Area | Status |
|------|--------|
| **Model validation** | Backtesting infrastructure exists (`src/iam/backtest/`); IC calibration runs are manual |
| **Factor weights** | Default weights documented in `src/iam/engine/composite.py:32–43`; no production calibration data yet |
| **Stress tests** | Elasticity module (`src/iam/elasticity/`) implements macro shock scenarios; no automated regime backtests |
| **Issue tracking** | GitHub Issues for bugs/features; no formal SLA published |
| **Security** | Dependency scanning via `pip-audit` in CI; no external audit performed |

---

## Reporting Framework (Planned)

When the first reporting cycle occurs (target: v0.3.0 / Q4 2026), each report will include:

### 1. Model Validation & Performance
- **Overall IC** (Spearman rank correlation between composite score and forward returns)
- **Directional hit rate** (Buy-rated names outperforming benchmark)
- **Top/underperforming factors** by IC contribution
- **Sample size** and time window

### 2. Model Changes & Factor Weights
- **Changes since last report**: factor weight deltas, new/removed factors
- **Rationale**: backtest evidence, regime-specific findings, structural improvements
- **A/B results**: canary vs. production performance

### 3. Stress Tests & Edge Cases
- **Regime-stratified performance** (Expansionary, Inflationary, Recessionary, Risk-Off, etc.)
- **Known limitations**: sectors, market caps, or macro conditions with degraded accuracy
- **Tail behavior**: max drawdown, worst decile performance

### 4. Operational Metrics
- **Bug SLA**: median time-to-resolution for P0/P1 issues
- **Feature SLA**: cycle time from PR open to merge
- **Security**: CVEs addressed, dependency freshness, audit findings
- **Community**: PRs merged, contributors, issue response time

---

## Release Cadence & Report Schedule

| Release | Target | Report Due |
|---------|--------|------------|
| v0.3.0  | Q4 2026 | Upon release |
| v0.4.0  | Q1 2027 | Upon release |
| v0.5.0  | Q2 2027 | Upon release |

Reports will be published to this repository under `docs/legal/transparency/` with the naming convention `TRANSPARENCY_REPORT_YYYY_QN.md`.

---

## Contact

Questions about transparency reporting: open a GitHub Issue with the `transparency` label.