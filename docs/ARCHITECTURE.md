# System Architecture — institutional-alpha

This document describes the actual structure of the codebase as of July 2026, grounded in
`src/iam/`. It is not aspirational — every claim cites a file path.

---

## 1. Module Dependency Map

The root package is `iam` (`src/iam/`). As of this writing, it contains **27 subpackages**
(themselves directories with `__init__.py`) plus a handful of top-level modules.

### Subpackage Inventory

| Subpackage | Role | Cross-package consumers |
|---|---|---|
| `analytics/` | Macro regime detection & factor weight adjustment | (leaf — no one imports it) |
| `api/` | Public API surface | backtest |
| `arbitration/` | Signal reliability & consensus arbitration | ui |
| `assumptions/` | Assumption modelling | (leaf) |
| `audit/` | Immutable audit log | governance |
| `backtest/` | Historical backtesting & calibration | ui, validation |
| `compliance/` | SEC/GDPR compliance audit trails | engine |
| `config/` | Settings & credentials | ui, backtest |
| `data/` | Security model, data fetching, macro conditions | **15 subpackages** (hub) |
| `elasticity/` | Macro stress & durability scoring | pipeline, valuation, laws |
| `engine/` | Composite scoring, market-implied DCF, Damodaran | pipeline, backtest, ui, factors, lenses |
| `factors/` | Factor definitions & scoring | engine, reasoning |
| `governance/` | Governance oversight | (leaf) |
| `integration/` | External system integration | api |
| `laws/` | Damodaran-law consistency checks | pipeline |
| `learning/` | ML-based learning module | backtest, ui |
| `lenses/` | Valuation lenses (DCF variants) | engine, ui, valuation, elasticity |
| `ml/` | IsolationForest anomaly detection lens (diagnostic) | pipeline |
| `monitoring/` | System monitoring | (leaf) |
| `pipeline/` | Valuation pipeline orchestrator | engine, reports, ui |
| `plugins/` | Plugin architecture (ABCs for custom lenses/factors/data adapters) | — |
| `portfolio/` | Portfolio construction | ui |
| `reasoning/` | Business reality engine | pipeline, lenses |
| `reports/` | Report generation | (leaf — imports from pipeline) |
| `thesis/` | Investment thesis & drift detection | pipeline, ui |
| `ui/` | Terminal UI (heaviest consumer) | — |
| `validation/` | Input validation & rate limiting | data, thesis, ui |
| `valuation/` | DCF, relative, SOTP, Monte Carlo, triangulation | data, engine, factors, laws, pipeline, ui |

### Dependency Graph

```
analytics   (no inbound deps)
arbitration (no inbound deps)
assumptions (no inbound deps)
audit       (no inbound deps, but governance imports it)
compliance  (no inbound deps, but engine imports it)
governance  → audit
monitoring  (no inbound deps)

data        → ui, validation, valuation
validation  → backtest
elasticity  → data, lenses
factors     → data, engine, valuation
lenses      → data, engine, reasoning
reasoning   → data, factors
thesis      → data, ui, validation
laws        → data, elasticity, valuation
engine      → compliance, data, factors, lenses, pipeline, valuation
valuation   → data, elasticity, lenses, ui
pipeline    → data, elasticity, engine, laws, reasoning, thesis, valuation
backtest    → api, config, data, engine, learning
integration → data, ui
reports     → pipeline
portfolio   → ui
api         → data, integration
ui          → arbitration, backtest, config, data, engine, learning, lenses,
              pipeline, portfolio, thesis, validation, valuation
```

**Key observations:**

- `data/` is the **foundation dependency** — 15 of 27 subpackages import it.
  It defines `Security` (`src/iam/data/security.py`), `MacroConditions` / `MacroShock`
  (`src/iam/data/macro.py`), data fetchers, and providers.
- `ui/` is the **heaviest consumer** (12 subpackages). The UI is not a thin display layer;
  it directly instantiates engines, lenses, and pipeline components.
- `pipeline/` is the **orchestration hub**, importing 7 subpackages and defining
  `ValuationPipeline` which runs a 7-stage workflow (see §1.1).
- There are **no circular dependencies** at the subpackage level.
- Six subpackages are pure leaves with no cross-package imports: `analytics`,
  `arbitration`, `assumptions`, `audit`, `compliance`, `monitoring`.

### 1.1 Pipeline Stages (`src/iam/pipeline/orchestrator.py:231`)

The `ValuationPipeline.run()` method executes up to 7 stages:

| Stage | Description | Source |
|---|---|---|
| 1 | **Reverse DCF** — what growth does the market price in? | `MarketImpliedEngine` |
| 2 | **Relative Valuation** — peer multiples regression | `RelativeValuation` |
| 3 | **Intrinsic DCF or SOTP** — independent build-up | `FCFEDCF` or `SOTP` (with `DamodaranEngine` for β) |
| 3b | **Monte Carlo** — fair-value distribution | `MonteCarloDCF` |
| 4 | **Triangulation** — cluster the three estimates | `Triangulator` |
| 4b | **Valuation Battlefield** — scenario distributions vs market | `ExpectationsBattlefieldEngine` |
| 4c | **Thesis Drift Detection** — check YAML constraints | `DriftDetector` |
| 5-6 | **Macro Overlay** — WACC adjustment per regime | `MacroOverlay` |
| 7 | **Final Verdict** — rating + confidence band | `VerdictGenerator` |

The output is the `PipelineReport` dataclass (`src/iam/pipeline/orchestrator.py:74`).

### 1.2 Composite Scoring Engine (`src/iam/engine/composite.py`)

The scoring engine (`score()` function) runs **10 additive factors + 3 penalties**
against a `Security`. Default weights are explicit constants on lines 32–43:

| Factor | Weight | Penalty | Weight |
|---|---|---|---|
| expectations_difficulty | 0.22 | fragility_penalty | 0.30 |
| intrinsic_value | 0.20 | leverage_penalty | 0.20 |
| quality | 0.12 | execution_risk_penalty | 0.15 |
| relative_value | 0.10 | | |
| sentiment | 0.08 | | |
| reflexivity | 0.08 | | |
| reinvestment_runway | 0.07 | | |
| macro_regime | 0.05 | | |
| crowding | 0.04 | | |
| earnings_quality | 0.04 | | |

When `security.macro` is present, the engine applies a **regime-aware weight adjustment**
(`src/iam/engine/composite.py:152`) with multipliers for tightening/easing/stagflation/neutral.
Penalties are subtracted: `composite = additive_sum - penalty_sum`.

---

## 2. Factor Design

### 2.1 Contract (`src/iam/factors/base.py`)

Every factor implements `Factor` (ABC) with one method:

```python
def compute(self, security: Security) -> FactorContribution
```

`FactorContribution` is a dataclass with:
- `name: str` — factor identifier
- `value: float` — **normalized to [-1, 1]** where positive = bullish
- `confidence: float` — **[0, 1]** (how much data was available)
- `components: dict` — per-sub-component scores (auditability)
- `notes: list[str]` — human-readable observations
- `effective() -> float` — returns `value * confidence`

`PenaltyFactor` extends `Factor` with `is_penalty = True` and a **[0, 1] convention**
where higher = more penalty (subtracted from composite).

### 2.2 Factor Inventory

All factors live in `src/iam/factors/`.

| Class | File | Range | What it measures |
|---|---|---|---|
| `SentimentFactor` | `sentiment.py` | [-1, 1] | Analyst revisions, momentum, earnings surprise persistence, news sentiment delta |
| `QualityFactor` | `quality.py` | [-1, 1] | Persistent quality premium: ROIC persistence, margin stability, FCF conversion, balance sheet strength, dilution, reinvestment efficiency |
| `EarningsQualityFactor` | `earnings_quality.py` | [-1, 1] | Real vs accounting FCF: accruals ratio, SBC % revenue, cash conversion, capex authenticity, one-time adjustments, working capital quality |
| `RunwayFactor` | `runway.py` | [-1, 1] | Reinvestment runway: incremental ROIC, TAM remaining, geographic/adjacency expansion, recurring revenue mix |
| `CrowdingFactor` | `crowding.py` | [-1, 1] | Ownership crowding: hedge fund, retail, passive concentration, short interest, options skew (less crowded = higher score) |
| `ReflexivityFactor` | `reflexivity.py` | [-1, 1] | Feedback loops: equity currency strength, network effects, talent attraction, acquisition optionality, narrative reinforcement |
| `MacroRegimeFactor` | `macro_regime.py` | [-1, 1] | Macro tailwind: real rates, liquidity, credit spreads, yield curve, PMI direction, dollar strength |
| `IntrinsicValueFactor` | `intrinsic_value.py` | [-1, 1] | DCF residual (fair/price - 1), market-implied thesis gap, owner earnings yield |
| `ExpectationsDifficultyFactor` | `expectations.py` | [-1, 1] | How demanding is the priced-in expectation vs historical peak (higher = easier = attractive) |
| `RelativeValueFactor` | `relative_value.py` | [-1, 1] | EV/EBITDA vs sector, P/E percentile, FCF yield vs peers, EV/Sales vs peers |

**Penalty factors** (range [0, 1], higher = worse):

| Class | File | What it measures |
|---|---|---|
| `FragilityPenalty` | `penalties.py` | PEG-style fragility — multiple vulnerability to growth disappointment |
| `LeveragePenalty` | `penalties.py` | Balance sheet stress: net debt/EBITDA, interest coverage, refinancing risk, current ratio |
| `ExecutionRiskPenalty` | `penalties.py` | Operational, supply chain, regulatory, geographic, integration risk (qualitative) |

**Normalization conventions:**
- Factor `value` is always clamped to [-1, 1] via `Factor.clamp()`; penalty `value` to [0, 1].
- Sub-component formulas use domain-specific neutral points (e.g., 10% ROIC = neutral for quality, 3.5% FCF yield = neutral for intrinsic value).
- Qualitative inputs expected in [0, 1] are mapped to [-1, 1] via `raw * 2 - 1`.
- Confidence is reduced multiplicatively when required data fields are missing.

---

## 3. Lens Architecture

### 3.1 Contract (`src/iam/lenses/base.py`)

Every lens extends `BaseLens` (ABC) with:

```python
def compute(self, security: Security) -> LensResult
```

`LensResult` is a dataclass with:
- `lens_name: str`
- `fair_value_low / fair_value_high: float | None` — WACC ± 1% sensitivity band
- `implied_move_pct: float | None` — `(midpoint / price) - 1`
- `confidence: float` — **[0, 1]**
- `narrative: str` — plain-English conclusion
- `assumptions: dict[str, float]` — key model inputs exposed for transparency
- `notes: list[str]`

**Diagnostic convention:** Lenses that return `None` for all three price fields are
"diagnostic only" — the synthesis engine (`synthesis.py`) skips them in the numerical
blend but preserves their narratives.

All valuation lenses use a shared `two_stage_pv()` helper for the DCF math:
10-year high-growth stage + perpetuity terminal value.

### 3.2 Lens Inventory

All lenses live in `src/iam/lenses/`.

| Class | File | Values? | Discount Rate | Differentiator |
|---|---|---|---|---|
| `RateSensitiveLens` | `rate_sensitive.py` | Yes | `real_rate_10y + 5.5%` | Macro-aware WACC for banks, insurers, REITs |
| `PlatformCompounderLens` | `platform_compounder.py` | Yes | `qualitative["forecast_discount_rate"]` (default 9%) | Terminal growth boost from margin expansion (capped 4%) |
| `ExpectationsDifficultyLens` | `expectations_difficulty.py` | No (diagnostic) | — | Back-solves required growth from price; compares to historical peak |
| `BusinessRealityLens` | `business_reality_lens.py` | No (diagnostic) | — | Qualitative durability/fragility via `BusinessRealityEngine` |

**Synthesis (`synthesis.py`):**
- `synthesize_lenses(lenses, reliabilities=None)` blends non-diagnostic lens outputs
  weighted by `confidence` × optional per-signal reliability (from historical IC
  calibration). Diagnostic lenses contribute to narratives only.

---

## 4. Macro Regime Definitions

The codebase contains **three distinct regime systems** at different layers.

### 4.1 Analytics Regime (`src/iam/analytics/regime.py`)

The richest system — 6 regimes with full factor-weight multipliers.

**Enum:**

```python
class MacroRegime(Enum):
    EXPANSIONARY    = "expansionary"
    DISINFLATIONARY = "disinflationary"
    INFLATIONARY    = "inflationary"
    RECESSIONARY    = "recessionary"
    RISK_OFF        = "risk_off"
    RISK_ON         = "risk_on"
```

**Input:** `RegimeIndicators` dataclass — inflation (rate + trend), real rates (rate + trend),
unemployment, GDP growth, credit spreads, VIX, earnings revisions + trend.

**Detection logic** (priority order):

| Condition | Regime |
|---|---|
| `credit_spreads > 400` OR `vix > 25` | RISK_OFF |
| `inflation_trend == "rising"` AND `rate_trend == "rising"` AND `inflation_rate > 3.0` | INFLATIONARY |
| `inflation_trend == "falling"` AND `rate_trend in ("falling","stable")` | DISINFLATIONARY |
| `gdp_growth < 0` OR `unemployment > 5.5` OR `earnings_trend == "deteriorating"` | RECESSIONARY |
| `gdp_growth > 3.0` AND `unemployment < 4.5` AND `earnings_trend == "improving"` | EXPANSIONARY |
| (default) | RISK_ON |

**Output:** `RegimeWeights` — 9 per-factor multipliers (quality, growth, value, momentum,
sentiment, capital_alloc, earnings_quality, relative_value, macro_regime) + a
`apply_to_weights()` method that multiplies and renormalizes. Example: in RISK_OFF,
quality_mult=1.8, macro_regime_mult=2.0, growth_mult=0.3, momentum_mult=0.1.

### 4.2 Pipeline Macro Regimes (`src/iam/pipeline/macro_regimes.py`)

A simpler 4-regime system used for WACC adjustment in the pipeline.

**Enum:**

```python
class MacroRegime(str, Enum):
    EASING      = "easing"
    TIGHTENING  = "tightening"
    STAGFLATION = "stagflation"
    NEUTRAL     = "neutral"
```

**Input:** `MacroConditions` (`src/iam/data/macro.py`) — `rate_change`, `pmi`,
`inflation_rate`, `credit_spread`, `gdp_growth`.

**Detection logic:**

| Condition | Regime |
|---|---|
| `rate_change > 0` AND `pmi < 50` | STAGFLATION |
| `rate_change > 0` | TIGHTENING |
| `rate_change < 0` | EASING |
| (default) | NEUTRAL |

**Output:** `MacroRegimeAssessment` — includes a `wacc_premium` (e.g., stagflation +150 bps,
easing -50 bps), a `shock_multiplier` for elasticity scaling, and a mapped `MacroShock`
(STAGFLATION_SHOCK / RATE_HIKE_SHOCK / RECESSION_SHOCK) defined in
`src/iam/data/macro.py`.

The `engine/composite.py` also references pipeline regimes via `_REGIME_WEIGHT_MAP`
(lighter 4-factor adjustment: quality, intrinsic_value, momentum, sentiment, macro_regime).

### 4.3 Confidence Regimes (`src/iam/pipeline/arbitration.py`)

Not macroeconomic, but a consensus-confidence tier:

| `primary_confidence` | `confidence_regime` | `pipeline_weight` |
|---|---|---|
| < 0.60 | LOW | 0.30 |
| 0.60–0.80 | MODERATE | 0.40 |
| >= 0.80 | HIGH | 0.60 |

### 4.4 Macro Regime Factor (`src/iam/factors/macro_regime.py`)

A continuous factor (not categorical) reading from `MacroContext` on the `Security`.
Computes a weighted average of 6 sub-scores (real rate regime, liquidity, credit spreads,
yield curve slope, PMI direction, dollar strength), each mapped to [-1, 1] via rules
(e.g., falling rates → +0.7, rising → -0.7). Final value clamped to [-1, 1].

---

*This document was generated from code survey, not from ROADMAP.md or design documents.*
*For design principles, see `docs/ai.md`. For framework rationale, see `docs/framework.md`.*
