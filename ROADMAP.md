# Institutional Alpha Roadmap

**Version**: 0.4.0-rc1  
**Status**: Release Candidate  
**Author**: William Hudspeth

---

## Platform Philosophy

Institutional Alpha is a **probabilistic institutional equity reasoning engine** — not a stock screener. A screener runs `financials → ratios → score → recommendation`. This platform instead treats valuation as **competing interpretations of reality under uncertainty**, and asks the question institutional investors actually ask:

> *Why does the market disagree with intrinsic value, and whose belief system is right?*

To answer that, the platform combines:

- **Orthogonal factors** (10 independent quality/value/sentiment dimensions)
- **Multi-perspective valuation** (DCF, Relative, Expectations-based, Triangulation)
- **Macro-aware synthesis** (regime overlays, dynamic assumptions)
- **Probabilistic reasoning** (Bayesian thesis engine, scenario analysis)
- **Financial guardrails** (input validation, sanity checks, assumption bounds)

Unlike black-box ML approaches, every output decomposes to its factor components and assumption inputs. Transparency is non-negotiable.

---

## The Reasoning-Engine Direction (v0.5+)

The current pipeline already runs four valuation perspectives and triangulates them. The next evolution reframes those perspectives as **independent reasoning engines** whose *disagreement* is the primary product, governed by a set of hard-coded valuation laws. The edge is not better math — it is **structuring uncertainty, disagreement, and narrative consistency correctly.**

### Seven-Engine Architecture (target)

| # | Engine | Question | Status |
|---|--------|----------|--------|
| 1 | **Data Integrity** | Are the inputs normalized, segment-aware, cycle-aware? | Partial (`validation/`, `data/`) |
| 2 | **Market Expectations** | What does the price *imply* — growth, margins, ROIC, moat duration? | ✅ Reverse DCF |
| 3 | **Business Reality** | What actually drives this business (revenue quality, cash-flow durability, capital allocation)? | ⬜ New |
| 4 | **Relative Reality** | Does this company *deserve* its premium, and by how much? | Partial → add **justified premium** |
| 5 | **Intrinsic Valuation** | What is it worth on cash flows alone, market ignored? | ✅ FCFE DCF, SOTP, bottom-up β, geo-ERP |
| 6 | **Macro Stress** | How does fair value move under regime shocks? | ✅ Macro overlay |
| 7 | **Synthesis** | Weight competing realities (not average them) into a verdict + disagreement map | Partial → add **Valuation Battlefield** |

### Damodaran Laws — narrative-consistency constraint layer (target)

These become enforced framework laws that can *reject* an internally inconsistent valuation rather than silently computing one:

- **LAW 1 — Narrative must match numbers.** High growth must be backed by reinvestment, TAM, and (usually) early margin compression.
- **LAW 2 — Growth requires reinvestment.** Enforce `g = ROIC × reinvestment_rate`; flag narratives where growth is "free."
- **LAW 3 — Terminal growth ≤ risk-free rate.** ✅ Already enforced.
- **LAW 4 — Excess returns fade.** Model explicit ROIC decay / margin mean-reversion curves; high ROIC attracts competition.
- **LAW 5 — Risk is not double-counted.** Risk lives in the cash flows *or* the discount rate, never both.

### Headline outputs (target)

- **Valuation Battlefield** — instead of a single fair value, surface the Bull / Bear / Market-implied / Intrinsic theses side-by-side with the **key disagreement** (e.g. "duration of excess returns") called out explicitly.
- **Thesis Drift Detection** — register the assumptions that *must remain true*, then monitor margins, ROIC, reinvestment, balance sheet, and macro regime. When assumptions drift, conviction falls and the verdict is re-ranked — turning static valuation into a living, fragility-aware signal.

---

## Current Capabilities (v0.4.0-rc1)

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
- [x] Single-ticker analysis (scripts/analyze.py)
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

### Phase 2.5: Reasoning-Engine Evolution (Weeks 10-18)
**Focus**: Turn the valuation pipeline into a disagreement-first reasoning engine (see "The Reasoning-Engine Direction" above)

- [ ] **Damodaran Laws constraint layer**
  - Enforce `g = ROIC × reinvestment_rate` (growth requires reinvestment)
  - Narrative-vs-numbers consistency check (reject impossible narratives)
  - ROIC decay / excess-return fade curves
  - Risk double-counting guard (cash flows OR discount rate, not both)
  - Terminal-growth ≤ Rf (already enforced — fold into the law registry)

- [ ] **Business Reality Engine** (`iam.reasoning` / new lens)
  - Revenue-quality classification (recurring / transactional / cyclical / regulated)
  - Cash-flow durability scoring (stable / mean-reverting / capital-markets-dependent)
  - Growth-quality decomposition (organic vs acquisition, marginal ROIC, TAM realism)
  - Capital-allocation / management-behavior signals (dilution, buyback discipline)

- [ ] **Relative Reality: justified premium**
  - Estimate the premium/discount a name *deserves* vs sector (not just observed)
  - Drivers: relative margins, ROIC, durability, cyclicality, optionality
  - Output justified-vs-actual premium gap

- [ ] **Valuation Battlefield output**
  - Surface Bull / Bear / Market-implied / Intrinsic theses side-by-side
  - Identify and label the single key disagreement per name
  - Replace "one fair value" framing with a structured disagreement map

- [ ] **Thesis Drift Detection**
  - Register assumptions that must remain true for each active thesis
  - Monitor margins, ROIC, reinvestment, balance sheet, macro regime
  - Degrade conviction and re-rank verdict when assumptions drift
  - Emit a per-name fragility score

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

- [x] **Interactive ANSI Terminal UI**
  - [x] Pure ANSI escape-sequence renderer (no heavy library dependency)
  - [x] Interactive side-panel layout with custom grid alignments
  - [x] Live fluctuating portfolio watchlist with dynamic sparklines
  - [x] Solid block factor scorecard meters & custom animation engines

- [ ] **Desktop Integration: C# ASP.NET Micro-Widget**
  - [ ] Standalone C# .NET 8 desktop webview/window container
  - [ ] Compact side-panel view (occupies 1/4 of screen)
  - [ ] Real-time local API sync to the Python valuation engine
  - [ ] Glowing glassmorphic widgets & real-time visual alerts

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
The model accepts fundamentals as inputs. Never assumes a specific data provider. Easy to adapt to major market data providers.

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
- Real-time enterprise data feeds
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
- Code structure → See `AI.md`

---

## License

Proprietary Research Platform. See LICENSE for details.

---

**Last Updated**: 2026-05-28  
**Status**: Release Candidate (v0.4.0-rc1)  
**Next Review**: 2026-06-28
