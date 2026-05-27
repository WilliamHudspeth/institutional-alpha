# Institutional Alpha Roadmap

**Version**: 0.2.1-alpha  
**Status**: Research Preview  
**Author**: William Hudspeth

---

## Platform Philosophy

Institutional Alpha is a **multi-lens equity research engine** designed for rigorous fundamental analysis. The platform combines:

- **Orthogonal factors** (10 independent quality/value/sentiment dimensions)
- **Multi-perspective valuation** (DCF, Relative, Expectations-based, Triangulation)
- **Macro-aware synthesis** (regime overlays, dynamic assumptions)
- **Probabilistic reasoning** (Bayesian thesis engine, scenario analysis)
- **Financial guardrails** (input validation, sanity checks, assumption bounds)

Unlike black-box ML approaches, every output decomposes to its factor components and assumption inputs. Transparency is non-negotiable.

---

## Current Capabilities (v0.2.1-alpha)

### ✅ Core Engine
- [x] **7-Stage Valuation Pipeline**
  - Stage 1: Reverse DCF (intrinsic value implied by price)
  - Stage 2: Relative Valuation (peer-based multiples)
  - Stage 3: FCFE DCF (explicit forecast valuation)
  - Stage 4: Triangulation (consensus across methods)
  - Stage 5: Macro Overlay (regime-dependent adjustments)
  - Stage 6: Thesis Engine (Bayesian scenario analysis)
  - Stage 7: Verdict (buy/hold/sell with conviction)

### ✅ Factor Framework
- [x] **10 Orthogonal Factors**
  - Quality (ROE, ROIC, quality of earnings)
  - Value (PE, PB, EV/Sales multiples)
  - Growth (earnings & revenue momentum)
  - Sentiment (analyst revisions, news)
  - Momentum (price trends, technical)
  - Macro Regime (rate sensitivity, cyclicality)
  - Reflexivity (crowding, positioning)
  - Runway (cash burn, balance sheet)
  - Expectations (difficulty of consensus growth)
  - Crowding (passive ownership, hedge fund)
  
- [x] **3 Penalty Terms**
  - Leverage penalty (debt reduces confidence)
  - Accrual quality penalty (earnings quality)
  - Sentiment reversal penalty (positioning risk)

### ✅ Data Layer
- [x] Yahoo Finance integration (live market data)
- [x] Fundamentals model (revenues, margins, cash flows)
- [x] Market data model (price, multiples, sentiment)
- [x] Macro context model (rates, credit, liquidity, regimes)
- [x] Thesis/Assumption framework (scenario modeling)

### ✅ Input Validation
- [x] Percentage input normalization (13 → 0.13)
- [x] Growth rate bounds (4-40% forecast, max 5% terminal)
- [x] WACC guardrails (4-25% range)
- [x] Valuation sanity checks (>50x market cap fails)
- [x] Assumption validator framework

### ✅ User Interface
- [x] Interactive welcome screen (main.py)
- [x] Multi-lens valuation CLI (run.py)
- [x] Single-ticker analysis (analyze.py)
- [x] Backtest harness (test historical factor returns)
- [x] Professional headers + versioning

### ✅ Testing & Quality
- [x] 158+ unit tests (passing)
- [x] Factor validation tests
- [x] Pipeline integration tests
- [x] Valuation range tests
- [x] Input validation tests

---

## Roadmap: Next Phases

### Phase 1: Research Maturity (Next 4-6 weeks)
**Focus**: Institutional polish & governance

- [ ] **Develop Branch Protection**
  - Require PRs for all code
  - Mandatory test passage before merge
  - Code review requirements
  - Branch protection rules on main

- [ ] **CI/CD Hardening**
  - GitHub Actions workflow (test, lint, type-check)
  - Coverage reporting (target 85%+)
  - Automated release tags
  - Build artifacts

- [ ] **Architecture Documentation**
  - Module dependency graph
  - Factor design specs per assumption bounds
  - Lens architecture (multi-perspective framework)
  - Macro regime definitions (4 regimes + transitions)

- [ ] **Assumption Registry**
  - Formalized assumption profiles (Conservative/Base/Aggressive)
  - Sector-specific defaults
  - Historical assumption performance
  - Industry median comparisons

### Phase 2: Core Intelligence (Weeks 6-12)
**Focus**: Financial rigor & scenario sophistication

- [ ] **Advanced Macro Overlay**
  - Regime-aware WACC adjustment
  - Yield curve positioning (duration risk)
  - Credit spread contagion modeling
  - Geopolitical event overlays

- [ ] **Probabilistic Valuation**
  - Monte Carlo DCF (distribution of outcomes)
  - Scenario probability weighting
  - Confidence degradation on extreme assumptions
  - Expected value reporting

- [ ] **Factor Weighting System**
  - Regime-dependent factor weights
  - Macro-sensitive factor alphas
  - Dynamic sector rotation framework
  - Correlation breakage detection

- [ ] **Thesis Engine Maturity**
  - Bear/Base/Bull case workflows
  - Assumption dependency mapping
  - Sensitivity analysis (one-way, two-way)
  - Scenario branching logic

### Phase 3: Operational Excellence (Weeks 12-24)
**Focus**: Reproducibility, governance, institutional adoption

- [ ] **Reproducibility Framework**
  - Build date stamping
  - Seed control (deterministic models)
  - Version-locked dependencies
  - Backtest data versioning

- [ ] **Research Governance**
  - Research hypothesis registry
  - Factor inclusion/exclusion audit trail
  - Model change logs
  - Assumption override tracking

- [ ] **Institutional Exports**
  - HTML research reports
  - Excel-compatible outputs
  - PDF summary generation
  - Institutional risk metrics

- [ ] **Performance Monitoring**
  - Factor alpha tracking
  - Valuation accuracy vs. realized price
  - Model performance by sector
  - Assumption forecast accuracy

### Phase 4: Advanced Research (Quarter 2+)
**Focus**: ML integration, portfolio-level optimization, institutional-grade tooling

- [ ] **Machine Learning Layer** (Optional)
  - Factor importance via tree-based models
  - Assumption prediction (growth, margin evolution)
  - Anomaly detection (impossible valuations)
  - Regime prediction (macro regime classifier)

- [ ] **Portfolio Optimization**
  - Position sizing (Kelly criterion)
  - Sector rotation framework
  - Macro hedge recommendations
  - Risk parity weighting

- [ ] **Dashboard & Terminal UI**
  - Real-time factor scorecards
  - Valuation range visualization
  - Macro regime display
  - Performance analytics

- [ ] **Plugin Architecture**
  - Custom lens registration
  - Custom factor framework
  - Alternative data source adapters
  - Valuation model extensions

---

## Architectural Principles

### 1. **Factors Are Orthogonal**
Each factor measures one independent dimension. No mixing of valuation with quality, sentiment with growth.

### 2. **Everything Is Auditable**
Composite scores decompose to factor contributions. No black-box aggregations. Every output traceable to inputs.

### 3. **Pluggable Data Sources**
The model accepts fundamentals as inputs. Never assumes a specific data provider. Easy to adapt to Bloomberg, Refinitiv, etc.

### 4. **No Magic Numbers**
All default weights, bounds, and assumptions are explicit and documented. Silent defaults are forbidden.

### 5. **Dependencies Stay Minimal**
Core engine uses only: pandas, numpy. Financial theory, not ML dependencies. Easy to audit and reproduce.

---

## Known Limitations

### Data Limitations
- Yahoo Finance as primary source (may have delays, errors)
- Limited historical data (5-10 years typical)
- No insider transaction data, regulatory filings parsing, alternative data

### Model Limitations
- DCF sensitivity to terminal growth rate assumptions
- Relative valuation dependent on peer set selection
- Macro overlay requires manual regime definition
- Thesis engine doesn't predict regime changes

### Operational Limitations
- Single-user tool (not multi-tenant)
- No real-time data (daily updates)
- Limited to North American equities (easily extensible)
- Backtesting requires manual data curation

---

## Success Metrics

### Research Quality
- Factor alphas > 5% annualized (out-of-sample)
- Valuation accuracy ±30% vs. realized price (1-year forward)
- Macro regime classification >75% accuracy
- Assumption forecast accuracy tracked

### Engineering Quality
- Test coverage > 85%
- Build reproducibility: date stamping + versioning
- Zero silent failures (all errors visible)
- Documentation coverage 100%

### Institutional Readiness
- Peer-reviewed assumptions (sector experts)
- Governance audit trail (who changed what, when)
- Regulatory-ready disclaimers
- Professional reporting formats

---

## Future Considerations

### If Commercialized
- Multi-user platform (authentication, permissions)
- Real-time data feeds (Bloomberg, FactSet)
- Institutional API (REST endpoints)
- Portfolio management layer
- Risk reporting (VaR, stress testing)
- Regulatory compliance (if applicable)

### If Academic
- Published factor papers (define alpha clearly)
- Reproducible backtest infrastructure
- Open data, closed methodology
- Peer review process
- Publication in academic journals

### If Enterprise Internal Tool
- Integration with internal risk systems
- Compliance framework
- Audit logging
- Institutional assumption frameworks
- Committee review workflows

---

## Dependencies & Requirements

**Core**:
- Python 3.10+
- pandas >= 2.0
- numpy >= 1.24

**Data**:
- yfinance >= 0.2 (for live data)

**Testing**:
- pytest >= 7.0
- pytest-cov

**Optional**:
- scipy (for advanced statistics)
- matplotlib (for visualization)
- jupyter (for interactive analysis)

---

## Contact & Support

**Author**: William Hudspeth  
**Email**: williamhudspethblackburn@gmail.com  
**GitHub**: [institutional-alpha](https://github.com/WilliamHudspeth/institutional-alpha)

**For questions about**:
- Factor methodology → See `docs/factors.md`
- Pipeline architecture → See `docs/framework.md`
- Valuation philosophy → See `docs/pipeline.md`
- Code structure → See `CLAUDE.md`

---

## License

Proprietary Research Platform. See LICENSE for details.

---

**Last Updated**: 2026-05-27  
**Status**: Research Preview (v0.2.1-alpha)  
**Next Review**: 2026-06-27
