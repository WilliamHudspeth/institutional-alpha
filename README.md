# Institutional Alpha Model (IAM)

> A multi-factor equity scoring framework that prices what elite funds actually price.

Most public valuation models stop at DCF or relative multiples. Institutional discretionary and systematic funds implicitly price a much wider surface: **expectations difficulty, quality, reflexivity, crowding, regime fit, fragility, and capital allocation quality.** This repo is an open-source attempt to encode that surface as an orthogonal, weighted, auditable factor model — written in plain Python so it's easy to read, fork, and extend.

## Status

[![CI/CD Pipeline](https://github.com/WilliamHudspeth/institutional-alpha/actions/workflows/python-package.yml/badge.svg)](https://github.com/WilliamHudspeth/institutional-alpha/actions)

**v0.4.0-rc1** — Institutional infrastructure complete. The factor scoring engine, seven-stage valuation pipeline, Bayesian thesis engine, hardened backtest stack, institutional portfolio analytics, and modern modular terminal are all implemented and tested. Next: empirical IC run on real market data (v0.4.0) and probabilistic reasoning engine (v0.5.0).

- 502 tests passing (with enhanced CI/CD coverage)
- 13 orthogonal factors (10 additive + 3 penalty)
- 7-stage valuation pipeline
- **Institutional portfolio layer** (analytics, position sizing, verdict generation)
- **Bayesian thesis framework** (scenario probability tracking, evidence-based updating)
- **Modern modular terminal** (event-driven panels, async data loading, ANSI visualization)
- **Institutional analytics** (factor attribution, 6-regime macro detection)
- Pluggable data sources (yfinance primary, Stooq fallback)
- Bayesian shrinkage calibration with sector-neutral IC
- Comprehensive CI/CD with linting, type checking, and security scanning

**v0.5.0 (in development)** — Probabilistic institutional reasoning engine with 4 independent engines (market expectations, business reality, peer-relative, intrinsic), Damodaran hard-coded rules, thesis drift detection, and competing narratives synthesis.

## How it actually works

The framework is built on an institutional insight: **valuation is competing interpretations of reality under uncertainty**, not a single "correct" number.

### Core Philosophy

Most stock screeners do this: `financials → ratios → score → recommendation`

IAM does this:

```
market expectations          (What does the market believe?)
      ↓
business reality             (What actually drives the business?)
      ↓
peer-relative economics      (Does it deserve its premium?)
      ↓
intrinsic economics          (DCF independent from market bias)
      ↓
macro regime interaction     (How fragile are assumptions?)
      ↓
probabilistic synthesis      (Weight competing realities)
      ↓
decision under uncertainty   (Buy/Hold/Sell with thesis drift detection)
```

### Layer 1 — plain English

When you point IAM at a stock, it runs **four independent reasoning engines**:

1. **Market-Implied Expectations Engine** — What does the stock price *tell us* the market believes about growth, margins, ROIC persistence, and moat duration? This reverses the DCF: given the current price, what assumptions must be true? This is not a valuation. It's decoding the market narrative.

2. **Business Reality Engine** — How does this business *actually* work? What drives revenue (recurring vs transactional, cyclical vs stable)? How durable is cash flow? What is reinvestment efficiency? What risks threaten assumptions? This interrogates the business, not just the numbers.

3. **Peer-Relative Engine** — Does this company *deserve* its premium? Not whether it has one, but whether the economics justify it. What's the justified multiple vs peers? Is quality relative, or absolute?

4. **Intrinsic Valuation Engine** — Full Damodaran DCF: bottom-up beta, geographic ERP blending, segment-level SOTP, through-cycle normalisation, operating leverage, ROIC fade curves, terminal growth constraints. This is independent from market pricing.

Then a **Synthesis Engine** weighs all four perspectives and asks: **"Why does the market disagree with intrinsic value?"** That disagreement is where alpha lives.

Finally, **Thesis Drift Detection** continuously monitors if your core assumptions remain true. If they drift, conviction falls and the model reranks.

### Layer 2 — how the pieces fit

**Factor scoring** (current) — 10 orthogonal factors + 3 penalties. Composite score ∈ [-1, +1]. Quick cross-sectional ranking.

**7-stage valuation pipeline** (current) — Stages 1–3 compute market expectations, peer analysis, and intrinsic DCF in parallel. Stage 4 triangulates. Stages 5–6 stress-test. Stage 7 outputs verdict with conviction band.

**Portfolio analytics** (current) — VaR, correlations, factor exposures, position sizing, rebalancing, portfolio-level verdicts.

**Bayesian thesis engine** (current) — Scenario probability updating on evidence, with reliability weighting to prevent overfitting.

**Probabilistic institutional reasoning** (v0.5.0, in development) — Four-engine architecture with competing narratives, Damodaran hard-coded rules, thesis drift detection, and probabilistic synthesis. See architecture section below.

### Layer 2 — how the pieces fit

**Factor scoring.** Composite = `Σ wᵢ · factorᵢ − Σ penaltyⱼ`. Ten factors with fixed, documented weights (see table below); each factor is implemented independently in `src/iam/factors/` and is orthogonal by design — valuation never blends with quality, sentiment never blends with reflexivity.

**Valuation pipeline.** Seven stages run in sequence, not in parallel. Stage 1 inverts the current price into an implied growth rate (reverse DCF). Stage 2 checks peer multiples. Stage 3 builds an intrinsic DCF bottom-up. Stage 4 triangulates: AGREE / TWO_OF_THREE / DISAGREE. Stages 5–6 detect when a macro shock would move the verdict and re-run only those names. Stage 7 emits Buy/Hold/Sell with a conviction band derived from triangulation spread.

**Thesis engine.** A Bayesian layer for scenario reasoning. You define Bull/Bear/Base scenarios with fair-value ranges. New evidence (earnings beat, guidance cut, macro shock) updates the posterior probability of each scenario — not the fair values themselves. Lets the model say "the Bull case is now 65% likely" instead of "the price target is X."

**Backtest harness.** Every month, build a point-in-time snapshot of each security, score it, then look at the realized 63-day forward return. The Spearman rank correlation between score and return is the **Information Coefficient (IC)**. Over 84 months, you get a distribution; the mean IC tells you if the signal works, the IC standard deviation tells you how consistent it is. The Information Ratio (IR = mean(IC) / std(IC)) is what institutional shops actually care about — 0.3–0.5 is realistic for equity factors.

### Layer 3 — The Institutional Reasoning Engine (v0.5.0)

**Engine 1 — Market-Implied Expectations**
Solves the reverse DCF to extract what the market is pricing:
- Implied 5-year FCFE growth
- Implied operating margins and ROIC persistence
- Implied moat duration (how long does excess return persist?)
- Implied cyclicality and macro sensitivity
- Franchise premium vs commodity value (zero-growth P/E)
- Conviction embedded in the price

Output: "Market is pricing 18% growth, 32% margins, 12-year moat, 6% terminal growth"

**Engine 2 — Business Reality**
Interrogates the actual business economics:
- Revenue durability (recurring, cyclical, regulated, subscription?)
- Cash flow quality and conversion rates
- Reinvestment efficiency: does g = ROIC × Reinvestment Rate hold?
- Operating leverage (fixed cost ratio, elasticity to market shocks)
- Management capital allocation history
- Balance sheet fragility and refinancing risk
- Competitive durability and moat strength
- Technological disruption and TAM saturation

Output: "Revenue is 75% recurring, reinvestment math checks, moat is 8 years, management disciplined"

**Engine 3 — Peer-Relative Reality**
Determines if the premium is justified:
- Regression of P/E (or EV/EBIT) on growth within sector peers
- Relative quality assessment (margins, ROIC, cyclicality)
- Relative certainty: is this company riskier than peers?
- Justified multiple vs actual multiple
- Relative moat durability
- Beta premium justification

Output: "BLK trades 1.1x peer-predicted multiple — fairly valued vs growth, premium justified by quality"

**Engine 4 — Intrinsic Valuation (Damodaran)**
Pure DCF independent from market bias:
- Bottom-up levered beta from Damodaran unlevered industry beta + capital structure
- Geographic-blended ERP (not just US ERP)
- Segment-level SOTP (if multiple businesses)
- Through-cycle normalisation (e.g., 0.8× base FCFE for cyclical industries)
- Operating leverage overlay (if FCF/market-drawdown elasticity >1.2×)
- ROIC decay curves (moat fade over 5–10 years)
- Terminal growth capped at Rf
- Two-stage DCF: high growth 5y, then linear fade 5y, then perpetuity

Output: "Intrinsic range $845–$975; stress floor $340 (severe yen unwind); ROIC reverts to WACC in year 9"

**Engine 5 — Macro Stress**
Recomputes intrinsic under scenario shocks:
- Rate shock (+50bp, +100bp, +150bp)
- ERP expansion (+50bp, +100bp)
- FCFE contraction (based on historical elasticity)
- Credit cycle transmission
- Refinancing risk
- Liquidity shock

Output: "In severe scenario (2.5% rates, 6.5% ERP, -18% FCFE), intrinsic drops to $340"

**Engine 6 — Synthesis (The Secret Sauce)**
Does NOT average. Instead, it:
- Weights each engine's output by confidence/durability
- Maps areas of disagreement
- Identifies the key assumption delta between market and intrinsic
- Produces a **valuation battlefield** showing bull/bear/market/intrinsic theses
- Outputs Buy/Hold/Sell with a **confidence interval** and **fragility score**
- Flags "thesis drift points" — which assumptions must stay true?

### The Damodaran Hard-Coded Laws

These become framework constraints:

| LAW | Rule | Rationale |
|-----|------|-----------|
| **Narrative ↔ Numbers** | If growth high, reinvestment rises; TAM supports; margins compress initially | Catches impossible stories |
| **Growth requires reinvestment** | g = ROIC × Reinv Rate (hard-coded check) | Prevents fake growth narratives |
| **Terminal growth cap** | g_terminal ≤ Rf (always enforced) | Prevents perpetual excess returns |
| **Excess returns fade** | ROIC decay curves; moat duration finite; terminal ROIC → WACC | Realism in competition |
| **Risk single-counted** | Risk in cash flows OR discount rates, never both | Prevents double-penalizing |
| **Peer consistency** | If premium justified vs peers, intrinsic must support it | Aligns relative and intrinsic |

### Thesis Drift Detection (Continuous Monitoring)

The system continuously asks: **"What assumptions must remain true for my thesis?"**

It monitors:
- Operating margins (vs forecast)
- ROIC (vs forecast)
- Reinvestment rates (vs forecast)
- Revenue growth quality (recurring vs transactional mix)
- Balance sheet metrics (leverage, cash conversion)
- Competitive position (share, NPS, retention)
- Macro regime (rates, credit, macro sensitivity)

If drift detected:
1. Conviction score drops
2. Model recomputes fair value
3. Alerts user to "thesis at risk"
4. Suggests rebalancing or position reduction

This turns static valuation into **living probabilistic intelligence**.

### Layer 4 — the math and the audit trail

**IC calibration.** Empirical IC is converted to a reliability weight `r ∈ [0.5, 0.95]` that gates how much the arbitrator listens to each signal. We use **Bayesian shrinkage** to avoid overfitting on short backtests:

```
posterior_ic = (prior_strength · prior_ic + n · empirical_ic) / (prior_strength + n)
reliability  = clamp(0.5 + posterior_ic · 5,  0.5,  0.95)
```

With `prior_ic = 0.02` and `prior_strength = 36` months, 36 months of data give the prior and the empirical IC equal weight. Fewer months than that, and the model trusts the prior more than the noisy empirical estimate. This is the institutional default — a heuristic for "don't believe a backtest until you've seen three years of it."

**Newey-West HAC SE.** Forward-return windows overlap (a 63-day return at month *t* and month *t+1* share 62 days of price action), so naive standard errors understate IC volatility. We use `statsmodels` HAC covariance with maxlags=3 to correct. The corrected t-statistic is what gets quoted in reliability tests.

**Sector-neutral IC.** Global IC can be inflated by a sector tilt the model isn't actually skilled at. We stratify by sector, compute IC within each, and report a size-weighted average. If `IC_sector_neutral ≈ IC_global`, the signal is genuine. If it collapses, the signal was sector timing in disguise.

**Pluggable data sources.** Price and balance-sheet data flow through a `DataSource` contract (`src/iam/backtest/sources/base.py`). The default chain is yfinance → Stooq: yfinance is queried first (institutional-grade, includes quarterly debt); on any failure, Stooq is queried (free CSV export, sandbox-safe, price only). Every new source — FMP, Tiingo, custom CSV — implements three methods and slots in without touching `snapshots.py` or `runner.py`.

**Manifest.** Every backtest run writes a `manifest.json` capturing git SHA, file hashes for all backtest modules, and the full config dump. Two runs with the same manifest are guaranteed reproducible.

## What's in the box

**Factor scoring** (`iam.score`) — cross-sectional ranking across many names. Runs ten orthogonal factors plus three penalty terms to produce a composite score in `[-1, 1]`.

| Factor | Weight | Question |
|---|---|---|
| Expectations Difficulty | 0.22 | What does the price imply, and how hard is that to deliver? |
| Intrinsic Value | 0.20 | What is the asset worth on its cash flows? |
| Quality | 0.12 | How durable and capital-efficient is the business? |
| Relative Value | 0.10 | Cheap or expensive vs. peers and own history? |
| Sentiment | 0.08 | What does the market mood say? |
| Reflexivity | 0.08 | Does the stock price itself improve the fundamentals? |
| Reinvestment Runway | 0.07 | Can capital still be deployed at attractive rates? |
| Macro Regime | 0.05 | Does the current regime reward this style? |
| Crowding | 0.04 | How positioned is the trade? |
| Earnings Quality | 0.04 | Is the reported FCF real? |

Three **penalty factors** are then subtracted: **Fragility** (multiple compression on a small miss), **Leverage** (balance sheet stress and refinancing risk), and **Execution Risk** (operational, regulatory, and geographic complexity).

**Valuation pipeline** (`iam.ValuationPipeline`) — a seven-stage sequential deep-dive on a single name. Disagreement between stages is the most important output, not a problem to smooth away.

```
Stage 1: Reverse DCF       → What does the market expect?
Stage 2: Relative          → Do peers/history support those expectations?
Stage 3: Intrinsic         → What's fair value built bottom-up, independently?
Stage 4: Triangulation     → Do the three answers cluster, or disagree?
Stage 5: Macro Outlier     → Which conclusions move materially under macro stress?
Stage 6: Macro Re-overlay  → Re-run only the names whose verdict actually changes.
Stage 7: Verdict           → Buy/Hold/Sell + conviction band + peer-relative ranking.
```

**Backtest harness** (`iam.backtest`) — production-grade evaluation infrastructure. Pluggable data sources (yfinance → Stooq fallback), Polars-based price block, diskcache PIT snapshots, ProcessPool scoring, statsmodels Newey-West, sector-neutral IC, Bayesian shrinkage calibration. See [`docs/pipeline.md`](docs/pipeline.md) and [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

**Portfolio analytics** (`iam.portfolio`) — institutional risk and allocation framework. `PortfolioAnalyzer` computes VaR via variance-covariance, correlations, factor exposures, and concentration metrics. `PositionSizer` allocates conviction- or risk-based position weights tied to security verdicts. `PortfolioVerdictEngine` synthesizes individual verdicts into OVERWEIGHT/NEUTRAL/UNDERWEIGHT portfolio recommendations. See [`PORTFOLIO_GUIDE.md`](PORTFOLIO_GUIDE.md).

**Institutional analytics** (`iam.analytics`) — macro-aware factor analysis. `AttributionEngine` decomposes returns into factor contributions. `RegimeDetector` classifies macro environment into 6 regimes (INFLATIONARY, DISINFLATIONARY, RECESSIONARY, EXPANSIONARY, RISK_OFF, RISK_ON) and applies dynamic factor weights (0.3x to 2.0x multipliers per regime).

**Modern modular terminal** (`iam.ui`) — event-driven, asynchronous rendering. Immutable state management (`SecurityState`, `TerminalUIState`), pub/sub event bus, composable panel architecture (`BasePanel` with 5 implementations), and ANSI sparklines. `ModernTerminal` accepts async data sources and progressively renders updates. See [`README_SYSTEM.md`](README_SYSTEM.md).

## Install

```bash
git clone https://github.com/WilliamHudspeth/institutional-alpha.git
cd institutional-alpha
pip install -e .
```

For live market data:

```bash
pip install -e ".[live]"
```

For the full backtest stack:

```bash
pip install -e ".[backtest]"
```

Requires Python 3.10+. Core dependencies are `numpy` and `pandas` only. The backtest extras add `polars`, `diskcache`, `statsmodels`, `tenacity`, `typer`, and `pydantic`.

## Quick start

### Interactive welcome screen

```bash
python main.py
```

A guided menu that lets you:
- Value a single security (7-stage pipeline)
- Score a security (10 factors + 3 penalties)
- Analyze scenarios with the thesis engine
- Evaluate historical factor performance

### Factor scoring

```python
from iam import Security, score

aapl = Security(ticker="AAPL")  # populate fundamentals as you wire data sources
result = score(aapl)

print(result.composite)          # e.g. 0.34
print(result.factor_breakdown)   # per-factor contributions
print(result.penalties)          # fragility / leverage / execution
```

### Valuation pipeline

```python
from iam import Security, ValuationPipeline

sec = Security(ticker="HYPCO", ...)  # populate fundamentals + market data
report = ValuationPipeline().run(sec)
print(report.explain())
# Stage 1: market implies 21% FCFE growth — 117% of peak.
# Stage 2: expensive vs peers/history (-44%).
# Stage 3: intrinsic DCF says -34%.
# Stage 4: TWO_OF_THREE — relative + intrinsic cluster; reverse DCF disagrees.
# Stage 7: HOLD | conviction: 0.52
```

### Thesis engine with Bayesian updating

```python
from iam.data.security import Assumption, Security, Thesis
from iam.thesis.engine import ThesisEngine
from iam.thesis.bayesian.priors import ScenarioPrior
from iam.thesis.bayesian.evidence import Evidence, ScenarioLikelihood

sec = Security(
    ticker="HYPCO",
    theses=[
        Thesis(label="Bull", fair_value_low=160.0, fair_value_high=200.0,
               narrative="Margin expansion drives re-rating.",
               assumptions=[Assumption("terminal_margin", 0.30, source="user")]),
        Thesis(label="Bear", fair_value_low=80.0, fair_value_high=110.0,
               narrative="Competition compresses margins.",
               assumptions=[Assumption("terminal_margin", 0.15, source="user")]),
    ],
)

engine = ThesisEngine()

# Bayesian update on an earnings beat
priors = [ScenarioPrior("Bull", 0.40), ScenarioPrior("Bear", 0.60)]
evidence = Evidence(
    description="Q2 earnings beat — margins expanded 200bps",
    signal_strength=0.8,
    likelihoods={
        "Bull": ScenarioLikelihood(0.85),
        "Bear": ScenarioLikelihood(0.25),
    },
)
updated = engine.apply_evidence(sec, priors, evidence)
print(updated.posteriors)    # posterior probabilities after the beat
print(updated.expected_value)
```

### Portfolio analytics

```python
from iam.portfolio.analytics import PortfolioAnalyzer
from iam.portfolio.types import Portfolio, Position

# Build portfolio from list of positions
portfolio = Portfolio(
    positions=[
        Position(ticker="AAPL", shares=100, entry_price=150.0),
        Position(ticker="GOOGL", shares=50, entry_price=2000.0),
        Position(ticker="MSFT", shares=75, entry_price=300.0),
    ],
)

analyzer = PortfolioAnalyzer(portfolio)

# Compute key metrics
var_95 = analyzer.compute_portfolio_var(confidence=0.95)
factor_exposures = analyzer.compute_factor_exposures()
correlation_matrix = analyzer.compute_correlation_matrix()
diversification_ratio = analyzer.compute_diversification_ratio()

print(f"VaR (95%): ${var_95:,.2f}")
print(f"Factor exposures: {factor_exposures}")
print(f"Diversification ratio: {diversification_ratio:.2f}")
```

### Portfolio verdicts and rebalancing

```python
from iam.portfolio.verdicts import PortfolioVerdictEngine

engine = PortfolioVerdictEngine()
verdict = engine.generate_verdict(portfolio_securities=[sec_aapl, sec_googl, sec_msft])

print(f"Portfolio verdict: {verdict.recommendation}")  # e.g., "OVERWEIGHT"
print(f"Confidence: {verdict.confidence}")             # 0.0 to 1.0
print(f"Factor exposures: {verdict.factor_exposures}")
```

### Backtest

Build the price parquet once, then run the backtest. The data source automatically falls back from yfinance to Stooq if yfinance is unavailable.

```bash
# One-time price build (yfinance → Stooq fallback, writes data/prices/sp100.parquet)
python scripts/build_price_parquet.py --start 2018-01-01 --end 2024-12-31 --horizon 63

# Run the backtest with parallel scoring
python -m iam.backtest.cli backtest
```

Or programmatically:

```python
from iam.backtest import (
    BacktestConfig, load_universe_from_json, load_price_block, run_backtest,
)

cfg = BacktestConfig()
cfg.validate_paths()
universe, _ = load_universe_from_json(cfg.universe_file)
prices = load_price_block(cfg)

results = run_backtest(
    universe=universe,
    dates=["2024-01-31", "2024-02-29", "2024-03-29"],
    price_block=prices,
    config=cfg,
    score_field="cost_of_equity",
)
# results has columns: ic, ic_sector_neutral, hit_rate, spread, top, bottom, ...
```

See [`examples/`](examples/) for runnable end-to-end demos.

## Architecture

```
src/iam/
├── api/             # Public facade (value_security)
├── factors/         # 10 orthogonal factors + 3 penalty factors
├── engine/          # Composite scoring (factor weighting + penalties)
├── valuation/       # ReverseDCF, RelativeValuation, FCFEDCF, SOTP, Triangulator
├── pipeline/        # 7-stage orchestrator, macro overlay, verdict generator
├── thesis/          # ThesisEngine + Bayesian updater (priors, evidence, updater)
│   └── bayesian/    # Scenario modeling, Bayes' theorem, evidence reliability
├── lenses/          # Rate-sensitive, platform compounder, Damodaran base, synthesis
├── data/            # Security, Fundamentals, MarketData, MacroContext, Damodaran
│   └── async_loader.py # ThreadPoolExecutor-based async data fetching
├── arbitration/     # Signal blending and reliability calibration
├── analytics/       # Factor attribution, 6-regime macro detection
├── portfolio/       # Risk analytics, position sizing, verdict generation
├── ui/              # Modular terminal, state, events, panels, sparklines
├── config/          # Pydantic settings, structured logging
├── integration/     # Adapters and async orchestration
├── validation/      # Input parser and financial guards
└── backtest/        # Production backtest harness (v0.4 hardened stack)
    ├── sources/     # Pluggable data sources (yfinance, stooq, composite)
    ├── config.py    # Pydantic frozen config
    ├── manifest.py  # Git SHA + file hash audit trail
    ├── metrics.py   # IC, sector-neutral IC, Newey-West, rolling stability
    ├── snapshots.py # Diskcache PIT snapshots
    ├── prices.py    # Polars parquet block loader
    ├── quantiles.py # Decile spreads + cost-adjusted turnover
    ├── runner.py    # ProcessPool scoring loop
    ├── calibration.py  # Bayesian shrinkage IC → reliability
    └── cli.py       # Typer entry point
```

Full conceptual documentation:

**Core model:**
- [`docs/framework.md`](docs/framework.md) — why orthogonality matters, the composite formula, and factor design rationale
- [`docs/factors.md`](docs/factors.md) — every factor's definition, sub-components, and default weights
- [`docs/pipeline.md`](docs/pipeline.md) — the seven pipeline stages in depth
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — 6-layer architecture, phase roadmap, integration patterns (499 lines)

**Institutional features:**
- [`PORTFOLIO_GUIDE.md`](PORTFOLIO_GUIDE.md) — portfolio analytics, position sizing, rebalancing, risk metrics (458 lines)
- [`INTEGRATION_GUIDE.md`](INTEGRATION_GUIDE.md) — end-to-end workflows from securities to portfolio (438 lines)
- [`README_SYSTEM.md`](README_SYSTEM.md) — modern terminal, configuration, async data layer, logging (469 lines)

**Infrastructure & releases:**
- [`docs/REAL_DATA_BACKTEST_STRATEGY.md`](docs/REAL_DATA_BACKTEST_STRATEGY.md) — empirical validation plan and gates
- [`RELEASES.md`](RELEASES.md) — release-by-release notes
- [`CHANGELOG.md`](CHANGELOG.md) — Keep-a-Changelog format

## Design principles

1. **Orthogonal factors.** Each factor measures one thing. Valuation and quality are separate inputs, not one blended score.
2. **Auditable.** Every composite score decomposes back into its factor contributions and penalty terms. No black-box aggregations.
3. **Pluggable data.** The model never assumes a specific data provider. Backtest data flows through the `DataSource` contract; add new sources by implementing three methods.
4. **No magic.** Default factor weights are explicit, documented, and easy to override. No hidden constants, no silent defaults.
5. **Regime-aware.** Macro state is classified into 6 regimes with dynamic factor weights. The overlay can re-weight factors or trigger a pipeline re-run, not just add noise.
6. **Empirically grounded.** Bayesian reliability weights are calibrated from historical IC, not heuristically assigned. Until the empirical run completes, the model uses conservative defaults clearly marked as such.
7. **Portfolio-aware.** Individual security verdicts feed into portfolio-level analytics: VaR, correlations, factor exposures, position sizing, rebalancing.
8. **Asynchronous-first.** Modern terminal and data layer use ThreadPoolExecutor for non-blocking operations. UI remains responsive during data fetches and pipeline runs.

## Roadmap

**v0.1–v0.3:** Foundational layers (factor scoring, DCF, Bayesian updating)
- [x] Factor scoring engine: 10 factors + 3 penalties (v0.1.0)
- [x] Valuation pipeline: Reverse DCF → Relative → Intrinsic → Triangulation (v0.2.0-alpha)
- [x] Core data layer + Yahoo Finance adapter (v0.2.0-alpha)
- [x] Multi-lens valuation engine (v0.2.0-beta)
- [x] Threshold-gated macro overlay (v0.2.0-beta)
- [x] Thesis Engine: scenario modeling, simulation, sensitivity (v0.2.0-beta)
- [x] Verdict generator + Damodaran peer ranking (v0.2.0)
- [x] Bayesian updating engine (v0.2.0)
- [x] Backtest harness v1: IC, quantile spread (v0.2.0)
- [x] Data layer caching + Damodaran ground truth (v0.3.0–v0.3.3)
- [x] Synthetic backtest validation (v0.3.5)
- [x] Real-data infrastructure: Stooq loader, Newey-West, safe reliability loader (v0.3.6)

**v0.4.0:** Production hardening + institutional infrastructure
- [x] Hardened backtest stack v2: pluggable sources, Polars, ProcessPool, sector-neutral IC, Bayesian shrinkage (v0.4.0-rc1)
- [x] **Institutional portfolio layer**: analytics, position sizing, verdicts (v0.4.0-rc1)
- [x] **Bayesian thesis enhancements**: scenario probability tracking, evidence reliability (v0.4.0-rc1)
- [x] **Modern modular terminal**: event-driven panels, async data, ANSI visualization (v0.4.0-rc1)
- [x] **Institutional analytics**: factor attribution, 6-regime macro detection (v0.4.0-rc1)
- [x] **Configuration system**: Pydantic settings, structured logging (v0.4.0-rc1)
- [ ] Empirical IC run on real S&P 100 data (v0.4.0)
- [ ] Multi-horizon IC measurement (21d / 63d / 126d / 252d)

**v0.5.0:** Probabilistic institutional reasoning engine (next major phase)
- [ ] **Market-Implied Expectations Engine**: Reverse DCF to extract market's implicit assumptions (growth, margins, ROIC, moat duration)
- [ ] **Business Reality Engine**: Interrogate actual business mechanics (revenue durability, reinvestment efficiency, moat strength, management quality)
- [ ] **Peer-Relative Reality Engine**: Determine justified premium/discount vs peers with relative quality assessment
- [ ] **Damodaran Hard-Coded Laws**: Framework constraints (narrative↔numbers, growth↔reinvestment, terminal growth cap, ROIC fade, single-counting rule)
- [ ] **Intrinsic Valuation Engine** (enhanced): Bottom-up beta, geographic ERP blending, operating leverage overlay, ROIC decay curves, segment-level SOTP
- [ ] **Macro Stress Engine** (v2): Multi-scenario rate/ERP/FCFE shocks with transmission to intrinsic value
- [ ] **Synthesis Engine**: Weights competing realities (market vs intrinsic vs peer vs business) and produces "valuation battlefield" with disagreement map
- [ ] **Thesis Drift Detection**: Continuous monitoring of core assumptions (margins, ROIC, reinvestment, growth quality, balance sheet, competitive position)
- [ ] **Confidence Intervals & Fragility Scoring**: Not point estimates, but probabilistic ranges with "what must stay true?" alerts
- [ ] **Competing Narratives Output**: Bull/Bear/Market/Intrinsic theses with key assumption deltas

**v0.6.0+:** Advanced features
- [ ] Additional data sources (FMP, Tiingo, Damodaran live datasets) via `DataSource` contract
- [ ] International expansion (country risk premium calculations, multi-currency FCFE)
- [ ] Cognitive research layer: research paper ingestion, insights generation, thesis drift via news flow
- [ ] Machine learning overlay: IC stability prediction, signal reliability estimation
- [ ] Real-time thesis reranking on earnings/macro events
- [ ] Portfolio-level thesis aggregation and sector regime adaptation

## License

MIT — see [LICENSE](LICENSE).

## Disclaimer

This is a research framework, not investment advice. Nothing here is a recommendation to buy or sell any security. Past performance of any factor model does not guarantee future results.
