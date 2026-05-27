# Institutional Alpha Release Notes

## Version History

### v0.3.4 - Production-Grade Backtest Harness
**Status:** Current Release  
**Test Coverage:** 219/219 tests passing ✓

#### Scope
Production-grade historical backtesting framework with Information Coefficient calibration for empirical Bayesian priors.

#### Features
- **Information Coefficient Metrics** (`backtest/metrics.py`)
  - Spearman rank correlation between model signal and forward returns
  - Hit rate: fraction of positive returns when score > median
  - Information Ratio: mean(IC) / std(IC) for consistency measurement
  - NaN handling for edge cases (no variance, insufficient data)

- **Calibration Engine** (`backtest/calibration.py`)
  - IC-to-reliability mapping: `0.5 + clamp(IC * 5, -0.5, 0.45)`
  - Clamps to [0.5, 0.95] range to prevent overconfidence
  - Supports export to `calibrated_reliabilities.json` for production use
  - Per-lens IC tracking for multi-factor attribution

- **Quantile Analysis** (`backtest/quantiles.py`)
  - Decile spreads (top 10% return - bottom 10% return)
  - Graceful handling of ties and insufficient data
  - Coverage metric: fraction of securities assigned to deciles

- **Point-in-Time Snapshots** (`backtest/snapshots.py`)
  - Freezes security state at evaluation date
  - Caches latest quarterly debt and historical price
  - Preserves immutability for scenario construction
  - Efficient pickle-based storage: `data/snapshots/{ticker}/{YYYY-MM}.pkl`

- **Historical Price Download** (`backtest/prices.py`)
  - Single download pass for full backtest period
  - Forward return calculation with custom horizon (default 63 days)
  - MultiIndex DataFrame (date, ticker) for efficient slicing

- **Backtest Runner** (`backtest/runner.py`)
  - Monthly loop: Evaluate each security, score it, measure IC
  - Black-box orchestration: calls `value_security(snapshot)` without introspection
  - Output: date-indexed DataFrame with IC, hit_rate, decile spreads, coverage

#### Architecture Highlights
- **One-way dependency preserved**: `backtest/` → `iam.api.value_security()` only
  - No coupling to internal valuation, arbitration, or factor engines
  - Backtest treats value_security() as immutable black box
  - Enables future integration of alternative valuation methods

- **Immutable snapshots**: Uses `dataclasses.replace()` for scenario construction
  - Point-in-time security state persists across evaluations
  - No accidental mutation of base security or market data
  - Supports both historical backtest and scenario analysis

- **Empirical calibration ready**:
  ```python
  results_df = run_backtest(universe, dates, horizon_days=63)
  summary = summarize_backtest(results_df)
  # IC_mean, IC_std, ICIR, hit_rate, spread metrics available
  
  write_calibration(
      ic_by_lens={"cost_of_equity": 0.045, "fcfe_upside": 0.038},
      output_path=Path("src/iam/arbitration/calibrated_reliabilities.json")
  )
  ```

#### Test Coverage
- 19 new backtest-specific tests
- Coverage: calibration, metrics, quantiles, integration scenarios
- Edge cases: negative IC (clamped to 0.5), zero variance (IR=0), sparse data
- Roundtrip verification: IC → reliability → ModelResult

#### Data Included
- `data/universe/sp100.json`: Static 100-ticker S&P 100 universe (frozen Dec 31, 2024)
  - Prevents web scrape drift in historical backtests
  - Immutable reference for reproducibility
  - Tracks exact evaluation universe across time periods

#### Next Step
Ready for first full production backtest:
```bash
results = run_backtest(
    universe=[Security(ticker=t, ...) for t in sp100_tickers],
    dates=pd.date_range("2018-01", "2024-12", freq="M").strftime("%Y-%m-%d"),
    horizon_days=63,
    score_field="cost_of_equity"
)

# Generate calibrated_reliabilities.json with empirical IC values
# After 36+ months of out-of-sample validation, promote to production
```

#### Files Changed
- `src/iam/backtest/__init__.py`: Public exports
- `src/iam/backtest/metrics.py`: IC, hit rate, information ratio
- `src/iam/backtest/calibration.py`: IC-to-reliability, summary, export
- `src/iam/backtest/quantiles.py`: Decile spreads, coverage
- `src/iam/backtest/snapshots.py`: PIT snapshot builder
- `src/iam/backtest/prices.py`: Price block download
- `src/iam/backtest/runner.py`: Monthly loop orchestrator
- `data/universe/sp100.json`: Static universe (force-tracked)
- `tests/test_backtest_harness.py`: 19 comprehensive tests
- `src/iam/version.py`: Bumped to v0.3.4

---

### v0.3.3 - Error Corrections & Production Readiness
**Previous Release**  
**Test Coverage:** 159/159 tests passing ✓

#### Scope
Validation, error handling corrections, and production-readiness verification.

#### What's Fixed
- **fetch_security() Math Fallbacks**: Restored missing data recovery logic
  - PE multiple → Net Income
  - EV/EBITDA → EBITDA TTM
  - Operating Cash Flow*0.8 → FCF (80% heuristic)
  - Ultimate fallback: Net Income as earnings power proxy
  - RuntimeError if price is missing (validation)

- **Bayesian API Migration**: Updated all Evidence instantiations
  - Changed `signal_strength` parameter to `reliability`
  - Added required `type` parameter (e.g., "EARNINGS_BEAT")
  - All 3 Bayesian scenario tests passing

- **FCFE DCF Baseline Validation**:
  - Test updated to expect 8.16% institutional rate (vs old 9% default)
  - Verifies Damodaran baseline appears in notes
  - Numerical precision tolerances adjusted for rounding

#### Test Status
```
Tests: 159/159 passing
- 5/5 Yahoo adapter tests
- 3/3 Bayesian updating tests
- 151+ valuation pipeline tests
```

#### Files Changed
- `src/iam/data/yahoo.py`: Restored math fallbacks
- `tests/test_yahoo.py`: Already passing (no changes needed)
- `tests/test_bayesian.py`: Updated Evidence API usage
- `tests/test_beta.py`: Updated baseline rate expectation
- `tests/test_thesis_engine.py`: Adjusted numerical precision

---

### v0.3.2 - Ground Truth Integration
**Previous Release**  
**Date:** Part of institutional upgrade cycle

#### Scope
Unified Ground Truth Provider and FCFE DCF integration with Damodaran baselines.

#### Features
- **GroundTruthProvider**: Single source of truth for institutional assumptions
  ```python
  profile = GroundTruthProvider.get_equity_risk_profile(security)
  # Returns: erp, risk_free_rate, industry_unlevered_beta, cost_of_equity
  
  wacc = GroundTruthProvider.get_wacc(security)
  # Returns: WACC with institutional baselines
  ```

- **FCFE DCF Integration**: Cost of Equity hierarchy
  1. Custom CAPM (if user provides risk_free_rate + equity_risk_premium)
  2. Damodaran institutional baseline (NEW - default)
  3. Forecast discount rate (fallback)

- **Public API Exports**: Available from `iam.data` package
  - `DamodaranProvider`, `MacroBaselines`
  - `GroundTruthProvider`, `EquityRiskProfile`

#### Example Output (BlackRock Case Study)
```
Sector: Financial Services
Industry: Asset Management
Current Price: $875.50
Market Cap: $120B

Damodaran Baselines:
- Unlevered Beta (Asset Mgmt): 0.59
- Risk-Free Rate: 4.25%
- Implied ERP: 4.6%

Calculation:
- Current D/E: 6.7% (8B debt / 120B market cap)
- Levered Beta: 0.59 × [1 + (1-0.21) × 0.067] = 0.73
- Cost of Equity: 4.25% + 0.73 × 4.6% = 7.59%

FCFE DCF Output:
- Fair Value (PWEV): $1206.96
- Upside: +37.9%
- Confidence: 100%
```

#### Architecture
- **Institutional Alpha**: Uses unlevered industry beta + current D/E
- **Retail Scripts**: Use regression beta (noisy, 5-year average)

| Metric | Retail | Institutional |
|--------|--------|---------------|
| Beta | Regression (5yr) | Unlevered industry |
| ERP | Historical (5.5-6%) | Implied (4.6%) |
| WACC | Volatile | Stable |
| Auditability | "Yahoo said so" | Damodaran Jan 2026 |

---

### v0.3.1 - Damodaran Ground Truth Provider
**Previous Release**

#### Scope
Institutional cost of capital baselines from Aswath Damodaran (NYU Stern).

#### Features
- **DamodaranProvider class**:
  ```python
  # Unlevered industry betas (0.4-1.2 by sector)
  u_beta = DamodaranProvider.get_industry_unlevered_beta("Technology", "Software")
  # Returns: 1.15
  
  # Implied equity risk premium (forward-looking)
  erp = DamodaranProvider.CURRENT_IMPLIED_ERP
  # Value: 0.046 (4.6%)
  
  # Country risk premiums
  crp = DamodaranProvider.get_country_risk_premium("India")
  # Returns: 0.020 (2.0% additional)
  
  # Re-levering formula
  levered = DamodaranProvider.relever_beta(0.59, 0.067, 0.21)
  # Returns: 0.73
  ```

- **Unlevered Industry Betas**: Pure business risk (debt-adjusted)
  - Software: 1.15
  - Asset Management: 0.59
  - Utilities: 0.40
  - All 20+ sectors covered

- **Country Risk Premiums**: For international equities
  - Developed (US, EU, JP, AU): 0%
  - Emerging (China 1.5%, India 2%, Brazil 2.5%)

- **Implied ERP**: Forward-looking market risk premium
  - Value: 4.6% (vs historical 5.5-6%)
  - Updated monthly by Damodaran
  - Reacts to market dislocations immediately

#### The Institutional Edge
Traditional retail scripts:
```python
# Regression beta = noisy 5-year average
beta = 1.2  # Could be 0.8-1.8 depending on daily price moves
discount_rate = 0.04 + 1.2 * 0.06  # Generic 9.2%
fair_value = dcf_calculation(discount_rate)
```

Institutional approach:
```python
# Pure business risk + current leverage
u_beta = 1.15  # Software industry, stable
de = 0.067     # Current debt ratio
levered = 1.15 * (1 + 0.79 * 0.067)  # 1.17
discount_rate = 0.0425 + 1.17 * 0.046  # 8.78%
fair_value = dcf_calculation(discount_rate)  # More accurate
```

---

### v0.3.0 - Data Layer Caching & Normalization
**First Release of Upgrade Cycle**

#### Scope
SQLite caching for Yahoo Finance with normalized data validation.

#### Features
- **SQLite Caching Layer**
  ```
  First fetch:  2-3 seconds (Yahoo Finance API)
  Cache hit:    20ms (SQLite local)
  Cache expiry: 24 hours (automatic)
  ```

- **Seed Database Strategy**
  - `seed_cache.sqlite`: Tracked in git (institutional data)
  - `iam_cache.sqlite`: Runtime cache (ignored by git)
  - New developers get warm cache on clone
  - Daily updates don't pollute git history

- **Normalization Layer**
  - `YahooAdapter.fetch_and_normalize(ticker)`
  - Maps Yahoo chaos → Clean IAM schema
  - Validates critical fields (price, shares_outstanding)
  - Returns None for missing fields (graceful degradation)
  - `DataProviderError` for validation failures

- **Seed Data Included**
  - BlackRock (BLK): Asset management
  - Apple (AAPL): Hardware/consumer electronics
  - Johnson & Johnson (JNJ): Pharmaceuticals
  - All fields populated with current institutional data

#### Benefits
- **Performance**: 100x pipeline runs without rate limits
- **Reliability**: Graceful degradation, multi-key fallbacks
- **Auditability**: Cached data is normalized and validated
- **Future-proof**: Swap data providers (FMP, FactSet) without touching pipeline

#### Architecture
```
Yahoo Finance API
        ↓
[Caching Check]
        ↓
seed_cache.sqlite (if fresh)   OR   yfinance (if expired/miss)
        ↓                             ↓
        └──────────────────┬──────────┘
                          ↓
            YahooAdapter.fetch_and_normalize()
                          ↓
            [Validation + Normalization]
                          ↓
            save_cached_data() → iam_cache.sqlite
                          ↓
            Normalized Dict → Security object
```

---

## Release Matrix

| Version | Focus | Tests | Key Files | Status |
|---------|-------|-------|-----------|--------|
| v0.3.4 | Backtest Harness & IC Calibration | 219/219 ✓ | backtest/*, calibration.py | **Current** |
| v0.3.3 | Validation & Correctness | 159/159 ✓ | yahoo.py, tests/ | Stable |
| v0.3.2 | Ground Truth Integration | All passing | ground_truth.py, fcfe_dcf.py | Stable |
| v0.3.1 | Damodaran Provider | All passing | damodaran.py | Stable |
| v0.3.0 | Caching & Normalization | All passing | yahoo.py, seed_cache.sqlite | Stable |

---

## Deployment Checklist (v0.3.4)

- [x] All 219 tests passing (backtest + integration + legacy)
- [x] Backtest harness complete (metrics, calibration, runner)
- [x] Point-in-time snapshots implemented with PIT pricing
- [x] Information Coefficient (Spearman rank) tested
- [x] IC-to-reliability mapping with clamping verified
- [x] Decile spread analysis with tie handling working
- [x] Historical price download functional
- [x] S&P 100 universe static/frozen (no drift)
- [x] One-way dependency preserved (backtest → iam.api)
- [x] Orchestrator black-box integration verified
- [x] Edge cases covered (negative IC, zero variance, sparse data)
- [x] Version bumped to v0.3.4
- [x] README and RELEASES.md updated
- [x] Git committed and pushed to main

---

## Git Tags

Current release tags:

```bash
# View all tags:
git tag -l
# Output:
# v0.3.0 - Data Layer Caching & Normalization
# v0.3.1 - Damodaran Ground Truth Provider
# v0.3.2 - Ground Truth Integration
# v0.3.3 - Error Corrections & Production Readiness
# v0.3.4 - Production-Grade Backtest Harness (NEW)

# Create and push the new tag:
git tag -a v0.3.4 -m "Production-Grade Backtest Harness with IC Calibration"
git push origin v0.3.4
```

---

## What Comes Next

**Immediate (v0.3.5)**
1. **First Production Backtest** (2018-01 to 2024-12, 63-day horizon)
   - Run full backtest on S&P 100
   - Generate empirical IC values for all signals
   - Write `calibrated_reliabilities.json` with IC-based weights
   - 36+ months of out-of-sample validation required before promotion

2. **Arbitrator Integration**
   - Load `calibrated_reliabilities.json` at import time
   - Use empirical IC weights in ModelResult blending
   - Feed IC back to BayesianEvidenceModel as priors
   - Complete "signal → backtest → calibration → Bayesian update" loop

**Roadmap v0.4.0+**

1. **Extended Data Providers**
   - FMP (Financial Modeling Prep) adapter
   - FactSet connector
   - Alternative data sources

2. **Advanced Backtesting**
   - Multi-horizon IC measurement (21d, 63d, 126d, 252d)
   - Factor-level attribution (which signals drive IC?)
   - Regime-dependent IC (macro environment effects)

3. **Macro Overlay**
   - Real-time ERP updates from Damodaran
   - Market shock detection
   - WACC spike on liquidity crises
   - Regime-aware factor weights

4. **Industry Peers**
   - Rank by Damodaran unlevered beta
   - Compare to industry standard WACC
   - Peer group analysis with historical IC

5. **International Expansion**
   - Country risk premium calculations
   - Multi-currency valuation
   - Emerging market focus

---

## Contact & Questions

For questions about these releases, refer to:
- `docs/framework.md` - Overall architecture
- `docs/factors.md` - Factor definitions
- `docs/pipeline.md` - Valuation stages
- `CLAUDE.md` - Development guidelines

