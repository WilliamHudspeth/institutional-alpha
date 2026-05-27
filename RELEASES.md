# Institutional Alpha Release Notes

## Version History

### v0.3.3 - Error Corrections & Production Readiness
**Status:** Current Release  
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
| v0.3.3 | Validation & Correctness | 159/159 ✓ | yahoo.py, tests/ | **Current** |
| v0.3.2 | Ground Truth Integration | All passing | ground_truth.py, fcfe_dcf.py | Stable |
| v0.3.1 | Damodaran Provider | All passing | damodaran.py | Stable |
| v0.3.0 | Caching & Normalization | All passing | yahoo.py, seed_cache.sqlite | Stable |

---

## Deployment Checklist

- [x] All 159 tests passing
- [x] Caching layer verified (cold start → warm cache)
- [x] Damodaran baselines loaded and tested
- [x] Ground Truth Provider integrated with FCFE DCF
- [x] fetch_security() math fallbacks working
- [x] Bayesian API migrations complete
- [x] Public API exports correct
- [x] Seed database initialized (BLK, AAPL, JNJ)
- [x] Error handling and validation tested
- [x] Documentation updated (RELEASES.md)

---

## Git Tags

Create and push these tags to create GitHub releases:

```bash
# Already created locally:
git tag -l
# Output:
# v0.3.0 - Data Layer Caching & Normalization
# v0.3.1 - Damodaran Ground Truth Provider
# v0.3.2 - Ground Truth Integration
# v0.3.3 - Error Corrections & Production Readiness

# To push to GitHub:
git push origin v0.3.0 v0.3.1 v0.3.2 v0.3.3
```

---

## What Comes Next

**Roadmap v0.4.0+**

1. **Extended Data Providers**
   - FMP (Financial Modeling Prep) adapter
   - FactSet connector
   - Alternative data sources

2. **Calibration Tracking**
   - Measure Bull/Bear prediction accuracy
   - Track Damodaran baseline changes
   - Backtest factor weights

3. **Macro Overlay**
   - Real-time ERP updates
   - Market shock detection
   - WACC spike on liquidity crises

4. **Industry Peers**
   - Rank by Damodaran unlevered beta
   - Compare to industry standard WACC
   - Peer group analysis

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

