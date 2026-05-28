# Real-Data Backtest Strategy (v0.3.5 → v0.4.0)

**Branch:** `feature/empirical-calibration-real-data`  
**Status:** In progress  
**Goal:** Convert synthetic architectural validation into empirical evidence-backed calibration

---

## Why We Need This

The v0.3.5 synthetic backtest proved:
- ✓ Pipeline architecture is clean (one-way dependencies, no lookahead)
- ✓ PIT snapshot discipline works
- ✓ Spearman IC contract is properly implemented
- ✗ **Actual signal persists on real data** (UNKNOWN)

**The synthetic IC of 0.0331 with IR of 1.93 is NOT credible because:**
1. Real equity IC series typically have std dev of 0.10–0.15 (ours was 0.017)
2. Real IR typically compresses to 0.3–0.5 (ours was 1.93)
3. No lookahead bias protection (Yahoo Finance in sandbox is blocked anyway)
4. No survivorship bias protection (static S&P 100)
5. Unknown regime dependence (only tested on synthetic)

---

## Three-Phase Approach

### Phase 1: Data Foundation (3 days)

**Objective:** Get real price data, properly versioned

**Tasks:**
```
[ ] Download Stooq OHLCV for S&P 100
    - Dates: 2018-01-01 to 2024-12-31
    - Use StooqDataLoader (free, no API key)
    - Cache to data/prices/sp100_ohlcv.parquet

[ ] Save data manifest
    - SHA256 hash of parquet file
    - Download timestamp
    - Ticker coverage (which % downloaded successfully)
    - Assumptions: Adjusted close, dividend-adjusted, no revisions

[ ] Document PIT limitations
    - Debt: latest quarterly, may be forward-looking
    - Fundamentals: frozen from universe config
    - Survivorship: current S&P 100 (not historical constituents)
    - Note: These are in MANIFEST.json for audit trail
```

**Key Files:**
- `src/iam/backtest/data_loader.py` — Stooq downloader with caching
- `data/prices/sp100_ohlcv.parquet` — Cached price data
- `data/prices/manifest.json` — Data metadata and integrity info

### Phase 2: Real Backtest Execution (2 days)

**Objective:** Run backtest on real prices, capture statistics

**Tasks:**
```
[ ] Execute scripts/backtest_runner.py against sp100_ohlcv.parquet
    - Uses StooqDataLoader to load cached prices
    - Runs value_security() for each security/date combination
    - Generates monthly IC measurements

[ ] Capture raw results
    - backtest_results_empirical.csv (84 rows, 8 columns)
    - Each row is one month: date, ic, hit_rate, spread, top, bottom, coverage, n_securities

[ ] Add statistical rigor
    - Compute t-stat and p-value for overall IC mean
    - Apply Newey-West SE adjustment (corrects for 63-day overlap)
    - Calculate rolling 12-month IC (drift detection)
    - Compute sector-neutral IC (robustness check)
    - Measure turnover (decile changes per month)

[ ] Generate summary statistics
    - IC mean and std dev
    - Information Ratio (mean/std)
    - Hit rate (directional accuracy)
    - Decile spread (top - bottom return)
    - Statistical significance (t-stat, p-value, Newey-West adjusted)
```

**Key Functions (in metrics.py):**
- `statistical_significance(ic_mean, ic_std, n)` — t-stat, p-value
- `newey_west_se(ic_mean, ic_std, n, nlags=3)` — Corrected SE
- `rolling_ic_stability(ic_series, window=12)` — Monthly drift tracking

### Phase 3: Factor Attribution (3 days)

**Objective:** Identify which factors actually drive alpha

**Tasks:**
```
[ ] Run backtest for each factor independently
    - Extract cost_of_equity signal from valuation stage
    - Extract expectations_difficulty signal from lenses
    - Extract relative_value signal from multiples
    - Extract quality signal from factors
    - Extract arbitration signal from consensus
    
    For each, measure IC separately

[ ] Build correlation matrix
    - Which factors are correlated (> 0.80)?
    - Are we double-counting risk?
    - Example: If "Quality" IC = 0.012 and "Earnings Quality" IC = 0.011
              and they correlate 0.85, one is redundant

[ ] Identify efficient factors
    - Which 3 factors do 80% of total alpha?
    - Remove/downweight redundant factors
    - Document in "Factor Attribution Report"

[ ] Output factor-level reliability calibration
    - If cost_of_equity IC = 0.025, reliability = 0.625
    - If quality IC = 0.015, reliability = 0.575
    - If synthesis IC = 0.032, reliability = 0.66
    - Update calibrated_reliabilities.json with per-factor weights
```

---

## Validation Gates (MUST PASS BEFORE v0.4.0)

### Gate 1: Data Integrity
```
✓ All 80 tickers downloaded successfully from Stooq
✓ Data hash matches manifest (file hasn't been corrupted)
✓ No gaps in price series (every trading day present)
✓ Forward returns calculated correctly (price[t+63] / price[t] - 1)
✓ Debt values are reasonable (no negative, no >500% of equity)
```

### Gate 2: Statistical Validity
```
✓ IC mean > 0.01 (has measurable signal)
✓ IC mean / IC std > 0.3 (information ratio reasonable)
✓ IC t-stat > 1.5 (trending toward significance despite noise)
✓ Rolling IC doesn't collapse to zero (signal stable)
✓ Hit rate > 50% (slight directional edge, not random)
```

### Gate 3: Architectural Soundness
```
✓ No lookahead bias (prices frozen on evaluation date)
✓ No survivorship bias (note: S&P 100 is static, so *some* bias exists)
✓ Sector-neutral IC > 0.5 * long-only IC (signal isn't just sector timing)
✓ Turnover < 40% per month (portfolio is stable, not just churning)
```

### Gate 4: Out-of-Sample Readiness
```
✓ 2018-2024 data committed to git (TRAINING SET)
✓ 2025 data reserved but NOT TRAINED ON (TEST SET)
✓ Manifest clearly labels training vs test
✓ OOS testing code written (to run after 2025 completes)
```

---

## If Real IC Comes Back Low (0.00–0.01)

**What it means:**
- The cost_of_equity signal has no measurable predictive power
- The system's valuation pipeline is academically sound but empirically weak
- This is STILL VALUABLE (knowing what doesn't work is worth knowing)

**What we do:**
1. Document thoroughly in "Empirical Results" post
2. Tag as `v0.4.0-empirical-null` to preserve the finding
3. Pivot to factor decomposition: Which *other* signals have IC?
4. Consider longer horizons (252-day instead of 63-day returns)
5. Consider regime-dependent calibration (bull/bear IC different?)

---

## If Real IC Comes Back Moderate (0.02–0.04)

**What it means:**
- Signal is real, economically meaningful
- Consistent with institutional alpha standards
- Worth integrating into Bayesian layer

**What we do:**
1. Tag as `v0.4.0-empirical-alpha`
2. Write calibrated_reliabilities.json with `data_source: empirical`
3. Merge into main branch
4. Begin v0.4.1 out-of-sample validation (2025 onwards)
5. Set up monthly IC tracking to detect drift

---

## Timeline

| Phase | Dates | Deliverable | Gate |
|-------|-------|-------------|------|
| Phase 1 | This week | sp100_ohlcv.parquet + manifest | Data Integrity ✓ |
| Phase 2 | Next week | backtest_results_empirical.csv + stats | Statistical Validity ✓ |
| Phase 3 | Following week | Factor Attribution Report | Architectural Soundness ✓ |
| Gate 4 | Before merge | OOS setup, 2025 test bucket ready | OOS Readiness ✓ |

---

## Key Differences: Synthetic vs Empirical

| Aspect | Synthetic (v0.3.5) | Empirical (this branch) |
|--------|-------------------|------------------------|
| **Data source** | Generated | Real (Stooq) |
| **IC std dev** | 0.017 (unrealistic) | ~0.10–0.15 (realistic) |
| **Information Ratio** | 1.93 (false) | ~0.3–0.5 (expected) |
| **Survivorship bias** | None (synthetic) | Some (S&P 100 is static) |
| **Lookahead bias** | None (sandboxed) | Protected (PIT discipline) |
| **Regime validation** | Single path | 84 months, multiple regimes |
| **Purpose** | Architecture proof | Empirical calibration |
| **Suitable for production** | ✗ No | ✓ Yes (if passes gates) |

---

## Code Changes Required

### New files:
- `src/iam/backtest/data_loader.py` — Stooq price loader ✓
- `src/iam/arbitration/reliability_loader.py` — Safe calibration loader ✓

### Modified files:
- `src/iam/backtest/metrics.py` — Add statistical functions ✓
- `src/iam/backtest/snapshots.py` — Add SP100 ticker loader ✓
- `src/iam/arbitration/calibrated_reliabilities.json` — Mark as synthetic ✓

### New outputs:
- `data/prices/sp100_ohlcv.parquet` — Cached price data
- `data/prices/manifest.json` — Data metadata
- `backtest_results_empirical.csv` — 84 monthly IC measurements
- `factor_attribution_report.md` — Which factors drive alpha?

---

## Execution Checklist

- [ ] Download and cache Stooq data
- [ ] Verify all 80 tickers downloaded
- [ ] Run scripts/backtest_runner.py on real prices
- [ ] Compute statistical significance tests
- [ ] Generate rolling IC plot (drift detection)
- [ ] Run factor attribution analysis
- [ ] Document findings in empirical post
- [ ] Pass all validation gates
- [ ] Commit to feature branch
- [ ] Create PR for code review
- [ ] Merge to main as v0.4.0-empirical

---

## References

- Grinold, Kahn. *Active Portfolio Management* (1995) — IC theory
- Newey, West. "Automatic lag selection in covariance matrix estimation" (1994)
- Damodaran. *Damodaran on Valuation* (2006) — Valuation principles

---

**Next step:** Execute Phase 1 (download real price data, cache with manifest)

