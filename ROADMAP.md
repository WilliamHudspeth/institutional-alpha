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

The current pipeline already runs four valuation perspectives and triangulates them. The next evolution deepens the **thought process** that drives those perspectives — moving from static formulas to **theory-first reasoning that works for any stock**. The platform's edge is not better numbers, but **better decision structure**: each valuation method reasons independently, their disagreement reveals hidden assumptions, and we re-weight those assumptions under stress based on how *durable* the underlying business is.

The theory: Apply **Mauboussin's expectations-investing framework** (what does the market expect?) in sequence with **Damodaran's intrinsic DCF rigor** (what is it worth?), using the disagreement between them to spot which assumptions are fragile.

### Seven-Engine Architecture (Target for v0.5)

| # | Engine | Question | Status | Theory |
|---|--------|----------|--------|--------|
| 1 | **Data Integrity** | Normalized inputs, segment accounting, cycle detection | ✅ Partial | Clean accounting is foundational |
| 2 | **Market Expectations** | What growth, margins, ROIC, moat duration is the price implying? | ✅ | Reverse DCF (Mauboussin) |
| 3 | **Business Reality** | Revenue durability, cash-flow quality, capital efficiency, management discipline | ⬜ New | Business logic layer (Damodaran) |
| 4 | **Relative Reality** | Justified premium/discount based on competitive durability, not just multiples | Partial → enhance | "Does it *deserve* this premium?" |
| 5 | **Intrinsic Valuation** | Fair value from bottom-up DCF, independent of market | ✅ | Damodaran DCF with bottom-up risk |
| 6 | **Macro Stress** | Fair value swing when rates move / growth contracts, calibrated by business durability | Partial → enhance | Elasticity-aware, not flat shocks |
| 7 | **Synthesis** | Weight competing theses by durability and disagreement; output verdict + confidence drift | Partial → refine | Valuation Battlefield + Drift Detection |

### Damodaran Laws — Theory-First Consistency Checks

These become consistency checks that **flag fragile analyses** rather than inventing numbers:

- **LAW 1 — Narrative must match numbers.** High growth + shrinking margins = reinvestment story (probably valid). High growth + expanding margins = competitive moat (needs explanation). Flag if narrative doesn't match the math.
- **LAW 2 — Growth requires reinvestment.** `g = ROIC × retention_rate` is a law. If the model predicts 15% growth but ROIC/retention can't support it, flag.
- **LAW 3 — Terminal growth ≤ risk-free rate.** ✅ Enforced.
- **LAW 4 — Excess returns fade.** High ROIC today attracts competition → margin pressure → ROIC mean-reversion. Model should assume explicit fade (5-10 year glide path).
- **LAW 5 — Risk is not double-counted.** Risk lives in cash flows OR discount rate, never both.

### The Core Enhancement: Theory-First Stress Testing

**Current state:** Macro overlay applies uniform rate/growth shocks. Gates on large moves ("this name is rate-sensitive") but doesn't reason about *why*.

**Target (v0.5):** Build a **Durability + Elasticity Scoring Layer** that decodes how a *specific* business responds to macro stress, then applies those response functions to re-price the three valuations.

**Theory:**
- **Durability score** (0–1): What % of cash flows persist if growth stalls? Asset managers: low (unless fees are sticky). Software with subscriptions: high. Cyclicals: very low. Comes from analyzing revenue mix, customer stickiness, recurring vs transactional.
- **Elasticity to growth shocks** (0–2): How much does FCFE contract if growth drops 5pp? Fixed-cost-heavy business (OpEx = 60% of revenue) → FCFE → 0 if growth → 0. Pure-variable-cost → FCFE falls proportionally. (Damodaran's "operating leverage"; Mauboussin's "reflexivity.")
- **Rate elasticity** (0–3): How much does terminal value change per 50bps rate move? Long-duration cash flows → 20–30% swings. Short-lived flows → <10%.

The insight: **Build the reasoning, not the numbers.** "How would an analyst think about this business under stress?" then apply that to re-weight and re-run the three valuations.

### Headline Outputs (Target for v0.5)

- **Valuation Battlefield** — surface Bull / Bear / Market-Implied / Intrinsic theses side-by-side. Call out the **key disagreement**. Example: "Market prices 35% FCFE growth (peak). Intrinsic assumes 8%. Relative says 12% (peer-justified). **Key disagreement: moat durability & excess-return fade** — is 5-year moat durable?"
- **Thesis Drift Detection** — register assumptions that **must** remain true. Monitor weekly. When assumptions drift (margins fall, ROIC drops), conviction falls and verdict re-ranks. Example: "Bull thesis requires 25% ROIC. Q1 ROIC = 22% → conviction 80% → 60%. Re-run valuation."
- **Elasticity-Aware Stress Report** — not "price drops 5% if rates rise 50bps" but "**this business is duration-bound**; rate moves have 3× impact of baseline DCF. Conviction collapses on >75bp move."

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
**Dependency**: Phase 1.5 (Security Hardening) runs in parallel and gates API exposure

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

### Phase 1.5: Security Hardening & Data Protection (Parallel to Phase 1)
**Focus**: CIA (Confidentiality, Integrity, Availability) + secure-by-default architecture

**Motivation**: Before any API exposure, multi-user access, or commercialization, the platform must be hardened against data exfiltration, injection attacks, and supply-chain compromise. This phase runs *in parallel* with Phase 1 and becomes a prerequisite for Phases 2+.

#### Core Security Disciplines

- [ ] **Input Validation & Sanitization**
  - [x] Numeric bounds checking (% normalization, WACC guardrails) — exists
  - [ ] Ticker symbol validation (regex: `^[A-Z]{1,5}$`, block SQL/path injection)
  - [ ] Date/time validation (ISO 8601 only, no format inference)
  - [ ] User-supplied assumption bounds (no formula injection via assumption strings)
  - [ ] API request schema validation (Pydantic models for all endpoints)
  - [ ] Rate limiting per user/IP (sliding window, exponential backoff on exceeded)
  - [ ] Request size limits (prevent billion-row CSV uploads)

- [ ] **Data Confidentiality**
  - [ ] Encrypt sensitive data at rest (model weights, user portfolios, API keys)
  - [ ] Encryption in transit (HTTPS/TLS 1.3 required for all endpoints)
  - [ ] Secrets management (environment variables, AWS Secrets Manager, HashiCorp Vault)
  - [ ] API key rotation policy (60-day expiry, automated generation)
  - [ ] PII masking in logs (no ticker names in error messages visible to untrusted users)
  - [ ] Secure session handling (JWT with short TTL, refresh tokens)

- [ ] **Data Integrity**
  - [ ] Checksum verification on all data artifacts (parquet files, CSV snapshots)
  - [ ] Audit logging for all model changes (factor weight updates, assumption overrides)
  - [ ] Git commit signing (GPG for all merges to main)
  - [ ] Immutable historical snapshots (backtest results, model versions)
  - [ ] Data provenance tracking (which yfinance/Stooq response produced this value?)
  - [ ] Idempotency keys (prevent double-scoring on network retry)

- [ ] **Data Availability**
  - [ ] Graceful degradation on data source failure (Stooq fallback already exists)
  - [ ] Rate limiting without DOS-ing upstream (exponential backoff on yfinance 429)
  - [ ] Circuit breaker pattern (fail open if data source is down for >N minutes)
  - [ ] Caching strategy (diskcache + TTL to avoid hammering APIs)
  - [ ] Backup & recovery procedures (versioned parquet snapshots)

#### Security Testing & Validation

- [ ] **Static Code Analysis**
  - [ ] Bandit (Python security linter) — scan for hardcoded secrets, SQL injection, eval()
  - [ ] Semgrep rules (financial domain: ticker validation, disclosure rules)
  - [ ] Type checking (mypy, strict mode) — null-safety prevents many injection attacks
  - [ ] Pre-commit hooks (block commits with secrets, enforce linting)

- [ ] **Dependency Scanning**
  - [ ] pip-audit (check installed packages for known CVEs)
  - [ ] safety (runtime Python vulnerability checks)
  - [ ] SBOM (Software Bill of Materials) — version lock all transitive deps
  - [ ] Automated dependency updates (Dependabot) + security alerts

- [ ] **Dynamic Testing**
  - [ ] Fuzzing: random ticker symbols, malformed dates, huge numbers
  - [ ] SQL injection tests (if any database integration added)
  - [ ] XSS payload tests (if any web UI added)
  - [ ] CSRF token validation
  - [ ] CORS misconfiguration tests
  - [ ] API authentication/authorization boundary tests (can user A see user B's portfolio?)

- [ ] **Penetration Testing Prep**
  - [ ] API endpoint inventory (document all routes, auth requirements)
  - [ ] Threat model (who attacks and why? Data theft, service disruption, IP theft)
  - [ ] Attack surface diagram (trust boundaries: user input, external APIs, storage)
  - [ ] Incident response plan (how do we handle a breach?)

#### API Security Framework (If/When Exposed)

- [ ] **Authentication**
  - [ ] OAuth 2.0 / OpenID Connect (industry standard, not custom auth)
  - [ ] API key management (generation, rotation, revocation)
  - [ ] Multi-factor auth for admin operations
  - [ ] Audit trail for all authentication events

- [ ] **Authorization**
  - [ ] Role-based access control (RBAC): Admin, Analyst, Viewer
  - [ ] Resource-level permissions (user can only score tickers they own)
  - [ ] Least-privilege principle (default deny, explicitly grant)
  - [ ] Capability-based tokens (JWT with scopes: `read:scores`, `write:assumptions`)

- [ ] **API Hardening**
  - [ ] OpenAPI/Swagger spec (machine-readable contract, security schema)
  - [ ] CORS policy (specify allowed origins, methods, headers)
  - [ ] HSTS (force HTTPS, prevent downgrade attacks)
  - [ ] CSP (Content Security Policy) if any web UI
  - [ ] API versioning (v1, v2 for backward-compatible changes)
  - [ ] Deprecation policy (sunset old API versions with notice)

#### Compliance & Governance

- [ ] **Audit Logging**
  - [ ] Immutable log stream (append-only, can't be deleted post-hoc)
  - [ ] What: endpoint, user, ticker, assumptions, output score
  - [ ] Who: authenticated user identity, IP address
  - [ ] When: precise timestamp, timezone
  - [ ] Why: operation type, parent request ID (for tracing)
  - [ ] Retention: 2-year minimum (regulatory requirement for financial advice)

- [ ] **Compliance Documentation**
  - [ ] Privacy policy (what data do we collect, how long retained, GDPR/CCPA compliance)
  - [ ] Terms of service (disclaimers: not investment advice, past performance doesn't predict)
  - [ ] Security incident disclosure policy (how quickly do we notify users?)
  - [ ] Data processing agreement (if GDPR-regulated)

- [ ] **Code Security Documentation**
  - [ ] Security design review checklist (before any API exposure)
  - [ ] Threat model living document
  - [ ] Secure coding guidelines (for contributors)
  - [ ] Known vulnerabilities & mitigations log

#### Operational Security

- [ ] **Development & CI/CD**
  - [ ] GitHub secrets vault (never commit API keys, DB passwords)
  - [ ] Signed commits (GPG signing of all code)
  - [ ] Branch protection + code review requirement (minimum 2 approvals for security changes)
  - [ ] Automated security scanning on every PR (Bandit, pip-audit)
  - [ ] Secrets scanning (GitGuardian, TruffleHog) — block pushes with hardcoded secrets

- [ ] **Deployment**
  - [ ] Container image scanning (if using Docker)
  - [ ] Immutable deployments (no in-place edits of running code)
  - [ ] Blue-green deployments (test before cut-over)
  - [ ] Rollback plan (can revert to previous version quickly)

- [ ] **Secrets & Key Management**
  - [ ] Never store secrets in code or config files
  - [ ] Use environment variables or secret manager (AWS Secrets, Vault)
  - [ ] Rotate API keys & passwords regularly (60-day cycle)
  - [ ] Separate keys for dev/test/prod (use different data sources)
  - [ ] Key escrow procedure (if employee leaves, revoke all their keys)

#### Success Criteria for Phase 1.5

- All user input validated & sanitized (no injection attacks possible)
- Zero hardcoded secrets (pre-commit hook enforces this)
- 100% of endpoints require authentication (except health check)
- Audit trail logs all scoring operations (immutable, 2-year retention)
- Bandit + pip-audit runs on every PR, must pass before merge
- Security design review completed before any API release
- Incident response plan documented & tested

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

### 6. **Security Is Built-In, Not Bolted-On**
Input validation, immutable audit logs, encrypted secrets, and rate limiting are foundational — not afterthoughts. Every endpoint requires authentication. Every data access is logged. Every assumption override is traceable.

### 7. **CIA (Confidentiality, Integrity, Availability) by Design**
- **Confidentiality**: Encrypt sensitive data at rest and in transit. Mask PII in logs. Rotate secrets regularly.
- **Integrity**: Immutable audit trail. Checksums on all artifacts. Git signing for all commits.
- **Availability**: Graceful degradation on data source failure. Circuit breakers. Rate limiting without DOS-ing.

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
- **Security-first**: Phase 1.5 is non-negotiable prerequisite
- Multi-user platform (OAuth 2.0, RBAC, audit logging)
- Real-time enterprise data feeds (rate limiting, circuit breakers)
- Institutional API (REST, OpenAPI spec, API key management)
- Portfolio management layer (user data isolation, encryption at rest)
- Risk reporting (VaR, stress testing)
- Regulatory compliance: SOC 2 Type II, GDPR, CCPA, investment adviser filings
- Incident response SLA (notification within 24 hours of breach)

### If Academic
- Published factor papers (define alpha clearly)
- Reproducible backtest infrastructure
- Open data, closed methodology
- Peer review process
- Publication in academic journals

### If Enterprise Internal Tool
- Integration with internal risk systems (SSO, LDAP/AD sync)
- Compliance framework (SOX, internal audit requirements)
- Immutable audit logging (all model changes, assumption overrides, score requests)
- Data governance (lineage tracking, PII protection, retention policies)
- Institutional assumption frameworks (approval workflows for assumption changes)
- Committee review workflows (sign-offs on major model updates)
- Data residency (on-premises or VPC, no cloud transit of sensitive data)

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
