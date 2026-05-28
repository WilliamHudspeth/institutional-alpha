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

### The Democratization Mission

This tool is built for **everyone**, not gatekeepers:

- **For retail investors**: Bring hedge fund reasoning to individual decision-making. Learn *how* institutions think about valuation, not just *what* to buy. Democratize the analytical frameworks that have historically been locked behind $10K/year Bloomberg terminals or $500K+ advisory fees.

- **For asset managers & hedge funds**: A risk-management companion, not a replacement. Use institutional-alpha to stress-test theses, validate assumptions under macro regimes, and catch fragile positions before they blow up.

- **For researchers & academics**: Open methodology. Publish factor alphas. Validate backtests on real data. Contribute factor designs. Learn from each other.

- **Philosophy**: "The best investment insights should not be hoarded. Better markets happen when more people think clearly about value."

**How we achieve this:**
- **Free & open-source** (code published, weights eventually transparent)
- **No SaaS paywall** (download, run locally, no licensing fees)
- **Modular design** (easy to extend, fork, improve)
- **Frequent releases** (security patches in hours, features in weeks)
- **Community-driven** (accept factor PRs, data source contributions, methodologies)
- **Educational materials** (explainers, validation reports, research papers)
- **Institutional adoption** (same tool serves retail and $100B+ funds; no artificial product segmentation)

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

### Phase 0.5: Testing Excellence (Parallel to Phase 1)
**Focus**: Overhaul testing infrastructure beyond pytest (mocking, fixtures, properties, performance)

**Philosophy**: Great software is tested. The better the tests, the faster we can iterate and ship safely.

#### Test Architecture Improvements

- [ ] **Comprehensive Fixture Library**
  - Shared fixtures: temp databases, mock API responses, sample data
  - Fixture factories: generate tickers, dates, fundamentals on demand
  - Context managers for resource cleanup (files, connections)
  - Organized by concern (cache fixtures, source fixtures, integration fixtures)

- [ ] **Mock API Strategy**
  - Decorator library for mocking yfinance, SEC EDGAR, Stooq
  - Realistic response data (match actual API schemas)
  - Controllable failures (rate limits, timeouts, partial data)
  - Request inspection (verify correct parameters sent)

- [ ] **Parametrized Tests**
  - Test multiple inputs per test (pytest.mark.parametrize)
  - Reduce copy-paste test code
  - Example: test all data sources with same assertions
  - Example: test all cache TTLs (0s, 1s, 7d, 30d)

- [ ] **Property-Based Testing (Hypothesis)**
  - Generate random inputs, verify invariants hold
  - Example: cache expiry always happens eventually
  - Example: fallback chain always returns data or empty series
  - Catch edge cases (timezone edge cases, leap years, etc.)

- [ ] **Contract Testing**
  - Verify all data sources implement the same interface
  - Abstract base class with type hints (Protocol)
  - Test that adapters can be swapped interchangeably
  - Catches breaking changes early

- [ ] **Performance Benchmarking**
  - Benchmark critical paths (cache lookups, API fetches)
  - Track performance regressions (pytest-benchmark)
  - Set SLAs (cache lookup < 1ms, API fetch < 5s)
  - Performance test suite runs on every commit

- [ ] **Regression Test Suite**
  - Capture bug reports as failing tests
  - Once fixed, test stays to prevent re-regression
  - Example: off-by-one in date filtering
  - Example: cache TTL miscalculation

- [ ] **Mutation Testing (Mutmut)**
  - Intentionally break code, tests should fail
  - Measures test quality (are you actually testing?)
  - Example: change `>` to `>=`, tests should catch it
  - Example: remove a fallback, tests should fail
  - Target: >90% mutation kill rate

- [ ] **Coverage Tracking & Enforcement**
  - Minimum 85% line coverage (enforced on PR)
  - Minimum 80% branch coverage
  - Coverage report generated on every test run
  - Gaps highlighted (unused code paths)

- [ ] **Test Organization**
  - `tests/fixtures/` — shared fixtures
  - `tests/unit/` — single-unit tests (cache, individual sources)
  - `tests/integration/` — full workflows (backtest, end-to-end)
  - `tests/performance/` — benchmarks
  - `tests/regression/` — bug reports turned tests

- [ ] **Test Documentation**
  - Each test has a docstring explaining what it tests and why
  - Fixtures documented (what they set up, what they clean up)
  - Test naming convention: `test_<unit>_<scenario>_<expected>`
  - Example: `test_cache_ttl_expiry_returns_none`

#### Success Criteria for Phase 0.5

- 500+ tests passing (up from 502)
- 85%+ coverage on new data layer
- All data sources tested with parametrized tests + mocking
- Property-based tests catch 5+ edge cases
- Performance benchmarks < 1% regression
- Mutation kill rate > 90%
- Zero tests rely on external APIs (all mocked)
- CI/CD runs full suite on every commit

---

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

### Phase 1.1: Release Management & Community Trust (Parallel to Phase 1)
**Focus**: Transparent, frequent releases + community-driven improvements (Rufus-inspired)

**Philosophy**: This tool is for everyone. Fast, trustworthy releases + open development = institutional-grade + accessible to retail.

#### Semantic Versioning & Release Cadence

- [ ] **Release Schedule**
  - Patch releases (v0.4.2): Every Friday if ready; includes bugfixes, security patches, data updates
  - Minor releases (v0.5.0): Every 6 weeks; includes features, factor improvements, UI enhancements
  - Major releases (v1.0.0): Quarterly; breaking changes, architectural shifts, production-grade milestones
  - Security patches: Within 24 hours of identification (no waiting for next scheduled release)

- [ ] **Conventional Commits & Auto-Changelog**
  - All commits tagged: `feat:`, `fix:`, `chore:`, `docs:`, `perf:`, `test:`, `security:`
  - PR descriptions include: what/why/impact + link to issue + changelog entry
  - Auto-generate release notes from merged PRs (tool: `auto` or `release-drafter`)
  - Changelog template: Security → Breaking Changes → Features → Bugfixes → Deprecations → Testing

- [ ] **Version Control & Artifact Management**
  - Every release tagged in git (v0.4.2)
  - Binaries (exe, dmg, wheel) published to GitHub Releases
  - Checksums (SHA256) + GPG signatures for integrity verification
  - Old versions always available (users can downgrade if new version breaks workflow)
  - "End of life" label on versions >12 months old (migrate to newer, but support remains)

#### Transparent Development (GitHub-First)

- [ ] **Public Roadmap**
  - Milestones for v0.5.0, v0.6.0, v1.0.0 (timeline + scope)
  - Issues tagged by type: `bug`, `feature`, `research`, `documentation`, `help-wanted`
  - "Help wanted" issues (contributions invited from researchers, fund managers)
  - Monthly status update (in-app + email): what shipped, what's next, known issues

- [ ] **Community Contributions**
  - Factor improvement PRs (propose new factor, include backtest + IC improvement)
  - Data source adapters (add alternative to yfinance/Stooq; community-maintained)
  - Documentation & educational materials (research papers, explainers, validation reports)
  - Methodology discussions (GitHub Discussions: "How should we handle X?" — open forum)

- [ ] **Issue Triage & Responsiveness**
  - Triage SLA: bug/security → 24h response; feature requests → 1 week
  - Transparency: explain why issues are closed (won't fix, duplicate, out of scope)
  - User feedback → priority (high-volume requests bubble to next sprint)

#### User Communication & Trust

- [ ] **In-App Notifications**
  - New version available (with changelog link, auto-updater prompt)
  - Security alerts (breach? 72-hour user notification)
  - Model updates (factor weights changed; here's why + impact analysis)
  - Educational: tips on how to use features, links to docs

- [ ] **Monthly Community Email**
  - What shipped (with links to PRs + detailed changelog)
  - What's coming (next 4-6 weeks roadmap preview)
  - Validation metrics (IC, hit rate, model performance this month)
  - Research highlight (interesting backtests, factor discoveries)
  - Ask for feedback ("What would help you?" — simple survey)

- [ ] **Validation & Transparency Reports**
  - Monthly IC backtest results (composite score performance by sector, horizon, universe)
  - Model stress tests (how factors behave in different regimes)
  - Factor attribution (which factors contributed most to recent alpha?)
  - Validation errors (cases where model underperformed + lessons learned)
  - These reports are public (GitHub + in-app)

#### Distribution & Accessibility

- [ ] **Single-Artifact Downloads**
  - Windows: `iam-0.4.2.exe` (no installer, just run)
  - macOS: `iam-0.4.2.dmg`
  - Linux: `iam-0.4.2.AppImage` or `.tar.gz`
  - Python package: `pip install institutional-alpha` (for devs)
  - All artifacts on GitHub Releases + checksums + signatures

- [ ] **Zero Dependencies for End Users**
  - Executable bundles Python + all deps (pandas, numpy, polars)
  - User doesn't need to install Python or manage pip
  - Lightweight (goal: <50MB executable)
  - Runs on Windows 7+ (maximum backward compat, not cutting off users)

- [ ] **Free & Open Source Commitment**
  - Code: GitHub public (MIT or similar open license)
  - No closed-source "pro" version (same tool for retail + hedge funds)
  - No license keys or activation (run locally, no SaaS lock-in)
  - No ads, no telemetry (except opt-in usage stats for roadmap prioritization)

#### Success Criteria for Phase 1.1

- New release every Friday (patch) or every 6 weeks (minor)
- Release notes auto-generated from commits (0 manual writing per release)
- 24-hour response to bug reports; security patches within 24h
- 50%+ PRs from community (factors, data adapters, docs)
- GitHub Discussions active (1-2 threads per week from users asking "how do I...")
- Monthly validation report published (IC, stress tests, attribution)
- 90%+ of users on latest version (auto-update working)
- Zero user complaints about "opaque" methodology (all factors, bounds, logic explained)

---

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

#### Auto-Update & Silent Deployment (Never Breaks User Workflow)

The user should never manually update. Security patches, factor improvements, data source changes — all roll out transparently.

- [ ] **Client-Side Update Mechanism**
  - Embedded auto-update checker (similar to Chrome, Electron)
  - Background download of new version during idle time (no performance impact)
  - Automatic restart on next app launch (not forced mid-session)
  - Version manifest (current vs. latest, with changelog)
  - Rollback button (if new version breaks workflow, revert in one click)

- [ ] **Version Tagging & Changelogs**
  - Semantic versioning (MAJOR.MINOR.PATCH)
  - Automated release notes from commit messages
  - Breaking changes highlighted (e.g., "factor weights updated — re-run backtest")
  - Beta releases (users can opt-in to test new features before stable)
  - Security patch priority (critical CVE fixes deployed within 24 hours)

- [ ] **Zero-Downtime Deployment**
  - API versioning (v1, v2) — old clients still work
  - Blue-green deployments (test on green, cut over when stable)
  - Staged rollout (10% → 25% → 50% → 100% of users, watch for errors)
  - Health checks at every stage (abort if error rate spikes)
  - Canary monitoring (catch regressions before they hit all users)

- [ ] **Backward Compatibility**
  - Old API clients keep working (with deprecation warnings, sunset date)
  - Old model versions available (so past backtests remain reproducible)
  - Config file format migrations (auto-convert old format on load)
  - Data artifact versioning (parquet schema versioning, fallback readers)

- [ ] **Transparency Without Noise**
  - Changelog in-app (one-click to see what changed, why)
  - Email digest (monthly, unless security patch → immediate notification)
  - No "update nag" popups during critical work
  - Metrics dashboard (how many users on each version, adoption rate)
  - Feedback loop (users report issues → prioritize fixes in next patch)

#### Success Criteria for Phase 1.5

- All user input validated & sanitized (no injection attacks possible)
- Zero hardcoded secrets (pre-commit hook enforces this)
- 100% of endpoints require authentication (except health check)
- Audit trail logs all scoring operations (immutable, 2-year retention)
- Bandit + pip-audit runs on every PR, must pass before merge
- Security design review completed before any API release
- Incident response plan documented & tested
- Auto-update mechanism deployed & tested (users never manually patch)
- Zero critical vulnerabilities remain unfixed for >24 hours

---

### Phase 1.5b: Legal & Compliance Roadmap (Parallel to Phase 1.5)
**Focus**: Financial/investment regulatory, data protection, liability, institutional trust

**Scope**: Everything a financial advisory platform must do to operate legally. This is not "optional nice-to-have" — it's the framework that lets you commercialize without exposing yourself to SEC enforcement, data breach lawsuits, or user claims.

#### Investment Adviser Regulatory (If Providing Advice/Rankings)

- [ ] **Regulatory Classification & Registration**
  - [ ] Determine if you need SEC Form ADV (investment adviser registration)
    - If: scoring tickers or producing rankings that people use for investing → likely **yes**
    - If: pure research (no recommendations, users do their own research) → gray area
  - [ ] State registration (each state with clients may require separate registration)
  - [ ] FINRA compliance (if you hold client funds, custody rules apply — unlikely here)
  - [ ] Alternative: Claim exemption (e.g., "research only, not advice") — but must be rigorous

- [ ] **Disclosure & Disclaimers**
  - [ ] **Form ADV Part 2A**: Brochure disclosing fees, conflicts, investment strategy, risks
    - Required even if you're exempt from registration
  - [ ] **Disclaimers in all output**:
    - "This is not investment advice. Past performance does not guarantee future results."
    - "Consult a financial advisor before making investment decisions."
    - "Model outputs are subject to model error and data limitations."
  - [ ] **Conflict of interest disclosure**:
    - Do you profit if users follow your recommendations? Disclose it.
    - Do you use alternative data you sell separately? Disclose it.
  - [ ] **Methodology disclosure** (required, but can be summary-level):
    - What factors are you using? High-level description.
    - What data sources? How current?
    - What are the known limitations?
  - [ ] **Performance track record** (if you claim to beat a benchmark):
    - Must be audited by GIPS standards or at least reproducible
    - Cannot cherry-pick periods or securities
    - Must disclose how many strategies, how many were winners (survivorship bias)

- [ ] **Suitability & Appropriateness**
  - [ ] Suitability questionnaire (if giving personalized advice):
    - Investor age, risk tolerance, time horizon, net worth
    - Investment experience, goals
  - [ ] Appropriateness check (model output appropriate for this investor's profile?)
  - [ ] Unsuitability flag (e.g., recommending leveraged bets to a 70-year-old = NOT suitable)
  - [ ] Documentation (save suitability assessment so you can defend if sued)

- [ ] **Fiduciary Duty Compliance** (if registered as advisor)
  - [ ] Duty of care: use reasonable care in analysis
  - [ ] Duty of loyalty: act in client's best interest, not your own
  - [ ] Duty of disclosure: tell clients about risks, conflicts, limitations
  - [ ] Document your process (can defend in court: "we did reasonable due diligence")

#### Data Protection & Privacy (Global)

- [ ] **Privacy Policy**
  - [ ] What data do you collect? (ticker queries, portfolio holdings, user profiles, IP logs)
  - [ ] Why? (service delivery, analytics, abuse prevention)
  - [ ] How long retained? (backtest data: 7 years for audit, user logs: 2 years for compliance)
  - [ ] Who has access? (only staff with legitimate need; contractors?)
  - [ ] User rights: download their data, delete their data, opt-out of analytics
  - [ ] Third-party sharing: do you share data with yfinance, Stooq, analytics vendors?

- [ ] **GDPR Compliance** (if any EU users)
  - [ ] Legal basis for processing (legitimate interest, user consent, contractual necessity)
  - [ ] Data Processing Agreement (if using third-party vendors like AWS, yfinance)
  - [ ] Right to be forgotten (user can demand deletion; implement purge process)
  - [ ] Data breach notification (notify users within 72 hours if personal data compromised)
  - [ ] DPA clause in ToS (users can't sue in EU courts if they agree to jurisdiction clause)
  - [ ] Pseudonymization (can you anonymize user behavior for analytics? Reduces risk)

- [ ] **CCPA/CPRA Compliance** (if California users)
  - [ ] Right to access: user can download all their data
  - [ ] Right to delete: user can ask you to delete (except legal hold)
  - [ ] Right to opt-out: "Do not sell my data" — honor it
  - [ ] Opt-in for minors (under 13 needs parental consent)
  - [ ] Privacy notice at point of collection (not hidden in terms)

- [ ] **Data Minimization**
  - [ ] Collect only what you need (ticker queries, not full portfolio unless necessary)
  - [ ] Don't retain longer than necessary (delete old backtest runs after 7 years)
  - [ ] Pseudo-anonymize (can you score by sector instead of ticker name?)

#### Liability & Risk Management

- [ ] **Terms of Service**
  - [ ] No guarantee of accuracy (model outputs may be wrong)
  - [ ] No liability for user losses (if user loses money, they can't sue you)
    - Exception: gross negligence or fraud (can't waive those)
  - [ ] Limitation of liability cap (e.g., "liability capped at fees paid")
  - [ ] Indemnification: user indemnifies you for third-party claims (rare but possible)
  - [ ] Dispute resolution: binding arbitration or small-claims court (faster than litigation)
  - [ ] Governing law: choose favorable jurisdiction (e.g., Delaware)

- [ ] **Errors & Omissions Insurance**
  - [ ] If commercialized, get E&O insurance (covers negligence, fraud claims)
  - [ ] Coverage limit: typically 1-5M (depends on AUM if advisory)
  - [ ] Carrier: insurers specializing in financial advisors (Chubb, Ironshore, etc.)

- [ ] **Intellectual Property**
  - [ ] Ownership clause: your code, factor definitions, weights are YOUR property
  - [ ] User license: users get limited license to use your output, not copy/resell
  - [ ] Patent considerations: should you file provisional patent on composite score formula?

#### Audit & Institutional Readiness

- [ ] **SOC 2 Type II** (if SaaS)
  - [ ] Security: access controls, encryption, logging
  - [ ] Availability: uptime SLA (e.g., 99.5%), incident response
  - [ ] Processing integrity: data accuracy, completeness
  - [ ] Confidentiality: data segregation, vendor management
  - [ ] 6-month audit with external auditor (costs 10-30K)

- [ ] **Internal Audit Trail**
  - [ ] Who accessed what data, when, why (immutable log, 2-year retention)
  - [ ] Model changes: when were factor weights updated, who approved, impact analysis
  - [ ] User complaints: log all issues, resolution, root cause
  - [ ] Conflicts of interest: flag if you benefit from certain outputs

- [ ] **Model Governance**
  - [ ] Change control: any model update requires documentation, testing, approval
  - [ ] Model validation: independent backtest before deployment
  - [ ] Model monitoring: track factor performance, IC, valuation accuracy
  - [ ] Model review: annual formal review by independent committee
  - [ ] Override log: if human overrides model output, log it + rationale

- [ ] **Regulatory Filings** (if applicable)
  - [ ] Form ADV Part 1 & 2 (SEC registration)
  - [ ] Form 4 (if insider trades — N/A unless you manage clients' portfolios)
  - [ ] Annual compliance certification (sign off that you follow your own policies)

#### Institutional Communications

- [ ] **Educational Materials**
  - [ ] Explainer: what is the composite score? How is it computed?
  - [ ] Limitations: where does the model break? (high-debt cyclicals, pre-revenue tech, etc.)
  - [ ] Validation: show backtested IC, Sharpe ratio, hit rate
  - [ ] Comparison: how does this compare to Bloomberg, Refinitiv, other providers?

- [ ] **Client Onboarding**
  - [ ] Suitability questionnaire (if personalizing advice)
  - [ ] Acknowledgment of disclaimers (they've read and understood)
  - [ ] Model risk briefing (what can go wrong? How do you monitor for failures?)
  - [ ] Data privacy briefing (what data you collect, how it's protected)

- [ ] **Ongoing Reporting**
  - [ ] Monthly model performance report (IC, hit rate, worst predictions)
  - [ ] Quarterly model update newsletter (factor weights changed? Why?)
  - [ ] Annual governance report (model reviews, complaints, regulatory filings)
  - [ ] Incident notifications (data breach? Immediately notify, full transparency)

#### Legal Documentation Checklist

- [ ] **Contracts**
  - [ ] Terms of Service (for end users)
  - [ ] Data Processing Agreement (for EU/GDPR)
  - [ ] Third-party vendor agreements (yfinance, AWS, if using)
  - [ ] Employee/contractor NDAs (protect factor weights, models, client data)

- [ ] **Disclaimers (Embed in Every Output)**
  - [ ] "Not investment advice"
  - [ ] "Past performance ≠ future results"
  - [ ] "Model subject to error"
  - [ ] "Consult a fiduciary advisor"
  - [ ] "No warranty of accuracy or timeliness"

- [ ] **Regulatory Filings** (varies by jurisdiction)
  - [ ] SEC Form ADV (if advisory)
  - [ ] State registrations (if operating in regulated states)
  - [ ] Industry certifications (CFA, CFP if personal advice)

#### Success Criteria for Phase 1.5b

- Privacy policy drafted & reviewed by counsel
- Terms of Service drafted (limitation of liability, disclaimers)
- All disclaimers embedded in every score/report
- Form ADV Part 2 (or exemption memo) prepared
- Data Processing Agreement ready (if EU users)
- E&O insurance quote obtained
- Model governance policy documented
- Audit trail logs all model changes & access
- Annual model review process defined
- Incident response plan includes user notification (72 hours)

---

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

- [ ] **Zero-Configuration Data Layer** (Key for democratization)
  - **Philosophy**: Users download repo, run `python data_fetcher.py --prefetch`, then backtest — no API keys, no config.
  - Redundant fetching: yfinance (primary) → Stooq (fallback) for prices
  - SEC EDGAR for point-in-time fundamentals (official, no key required)
  - Bundled macro data (CSV; user can replace with FRED if desired)
  - Persistent SQLite cache (TTL-based, reduces network calls)
  - Pre-fetch script: one-time download of 20+ years of data for universe
  - Automatic rate limiting & exponential backoff (graceful degradation under load)
  - Offline-first: after prefetch, backtest runs entirely offline
  - Integration: `RedundantDataFetcher` API used by backtest runner

  **Benefits**:
  - Retail investors can backtest without API keys or vendor lock-in
  - Researchers can validate methodologies on real historical data
  - Hedge funds get redundant, resilient data pipeline for production
  - Community can contribute data source adapters (Bloomberg, Refinitiv connectors)

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
Each factor measures one independent dimension. No mixing of valuation with quality, sentiment with growth. Users can understand and challenge each piece.

### 2. **Everything Is Auditable**
Composite scores decompose to factor contributions. No black-box aggregations. Every output traceable to inputs. Retail investors deserve the same transparency as hedge funds.

### 3. **Pluggable Data Sources**
The model accepts fundamentals as inputs. Never assumes a specific data provider. Easy to adapt to major market data providers. Open community (contribute data adapters, improve fallback chains).

### 4. **No Magic Numbers**
All default weights, bounds, and assumptions are explicit and documented. Silent defaults are forbidden. Users and researchers can propose improvements via PRs.

### 5. **Dependencies Stay Minimal**
Core engine uses only: pandas, numpy. Financial theory, not ML dependencies. Easy to audit, reproduce, and extend. No vendor lock-in.

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
- Regulatory-ready disclaimers (Phase 1.5b complete)
- Professional reporting formats
- Legal review by securities counsel (if advisory)
- SOC 2 Type II certification (if SaaS)
- E&O insurance in place (if commercialized)

---

## Future Considerations

### If Commercialized (Open-Core Model, Not Gatekeeping)

**Philosophy**: Free, open-source core + optional premium services for enterprises/professionals who want convenience.

- **Core (Always Free & Open)**
  - Single-user local deployment (download, run, score tickers)
  - All factors, all valuation methods
  - Backtest harness
  - Community-contributed data sources (yfinance, Stooq, etc.)
  - No paywalls, no feature lockouts

- **Optional Premium (Enterprise/Professional)**
  - Managed SaaS API (don't run locally, just call HTTP endpoint)
  - Real-time enterprise data feeds (Bloomberg, Refinitiv, proprietary sources)
  - Multi-user collaboration (shared portfolios, assumption libraries, team research)
  - Advanced risk reporting (portfolio-level VaR, stress scenarios, Greeks)
  - Audit trail & governance (SOC 2 Type II, regulatory-ready)
  - Dedicated support SLA
  
  **Model**: $99-999/month per user or $10K-50K/year per firm (scale by AUM)

- **Values**:
  - **Security-first**: Phase 1.5 is non-negotiable for any deployment
  - **Transparent pricing**: no hidden tiers, no artificial feature segmentation
  - **No lock-in**: export your data anytime, run open-source core locally
  - **Community first**: premium customers fund open-source development
  - **Regulatory-grade**: SOC 2 Type II, GDPR, CCPA, investment adviser filings (for both free + premium)

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
