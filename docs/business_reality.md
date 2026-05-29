# Business Reality Engine

**Engine #3 of the Seven-Engine architecture** (see `ROADMAP.md`).

The Business Reality Engine is a *theory-first reasoning layer*, not an alpha
factor. Where the valuation lenses ask *"what is it worth?"*, this engine asks
the Damodaran **Business Reality** question:

> *Revenue durability, cash-flow quality, capital efficiency, management
> discipline — does the business deserve the story the price is telling?*

It consumes a `Security` and produces a structured `BusinessReality`
assessment. It is **stateless, side-effect-free, and never raises** on missing
data (each dimension degrades its confidence and falls back to a neutral prior).

```python
from iam.reasoning import BusinessRealityEngine

assessment = BusinessRealityEngine().assess(security)
print(assessment.narrative)
```

## Why it is not a composite factor

Adding a new alpha factor would require re-normalising the ten existing factor
weights (which sum to 1.0) and re-baselining the backtests. Instead, Business
Reality is surfaced two ways that are **non-breaking**:

1. **As a diagnostic lens** — `iam.lenses.BusinessRealityLens` wraps the engine
   in the standard `LensResult` shape with `fair_value_*`/`implied_move_pct` set
   to `None`, so `synthesize_lenses` skips it for the weighted price target. It
   exists to surface reasoning, not to vote on fair value.
2. **As structured output** — the `fragility` score is the hook a future
   *Thesis-Drift Detector* / *Valuation Battlefield* (separate roadmap items)
   consumes to degrade conviction on fragile names.

## The six reasoning dimensions

| # | Dimension | Output | Range | Theory |
|---|-----------|--------|-------|--------|
| 1 | Revenue quality | `revenue_quality` | enum | Character of the top line |
| 2 | Cash-flow durability | `cashflow_durability` + label | [0, 1] | Operating leverage / reflexivity |
| 3 | Growth quality | `growth_quality` + decomposition | [-1, 1] | Damodaran Law 2 (growth needs reinvestment) |
| 4 | Capital allocation | `capital_allocation` + label | [-1, 1] | Management discipline |
| 5 | ROIC durability | `roic_durability` | [0, 1] | Damodaran Law 4 (excess returns fade) |
| 6 | Fragility / robustness | `fragility`, `robustness` | [0, 1] | Synthesis (`fragility = 1 − robustness`) |

### 1. Revenue-quality classification

`RevenueQuality` ∈ {`RECURRING`, `TRANSACTIONAL`, `CYCLICAL`, `REGULATED`,
`UNKNOWN`}. Decision order (first match wins):

1. Explicit `qualitative["recurring_revenue_mix"]` ≥ `0.50` → **RECURRING**.
2. Sector in `{utilities}` → **REGULATED**.
3. Revenue coefficient-of-variation ≥ `0.25`, or a cyclical sector → **CYCLICAL**.
4. Gross margin ≥ `0.55` *and* revenue CV ≤ `0.10` (smooth, high-margin) → **RECURRING**.
5. Otherwise **TRANSACTIONAL** (or **UNKNOWN** if no signals at all).

Sector is only a tiebreaker; margins, revenue volatility, and the recurring-mix
input dominate.

### 2. Cash-flow durability — *what % of cash flow persists if growth stalls?*

A hard rule first: **negative FCF ⇒ `capital_markets_dependent`** (score `0.15`),
because a business that does not self-fund relies on external capital. Otherwise
a confidence-weighted blend of:

| Sub-component | Weight | Logic |
|---|---|---|
| FCF stability | 0.35 | Low historical CV of FCF → durable |
| Operating leverage | 0.30 | `(gross_margin − operating_margin) / gross_margin` is fixed-cost intensity; high intensity → FCF collapses when growth stalls |
| Revenue-quality prior | 0.35 | recurring 0.85 / regulated 0.80 / transactional 0.50 / cyclical 0.25 |

Labels: ≥ `0.60` **stable**, ≥ `0.35` **mean_reverting**, else
**capital_markets_dependent**.

### 3. Growth-quality decomposition — *organic vs acquisition/dilution*

| Sub-component | Weight | Logic |
|---|---|---|
| Organic per-share growth | 0.55 | revenue CAGR − share CAGR (growth net of dilution) |
| Marginal ROIC | 0.30 | incremental ROIC vs a 10% neutral anchor |
| TAM realism | 0.15 | optional `qualitative["tam_remaining"]` ∈ [0, 1] |

The `growth_decomposition` dict exposes the raw `revenue_cagr`, `share_cagr`,
`organic_spread`, `incremental_roic`, and `tam_remaining` for auditability.

### 4. Capital-allocation assessment

| Sub-component | Weight | Logic |
|---|---|---|
| Dilution / buyback discipline | 0.35 | buybacks good, issuance bad (shared with QualityFactor) |
| Reinvestment efficiency | 0.30 | incremental ROIC |
| Debt discipline | 0.20 | net-debt / EBITDA vs 1× neutral |
| SBC discipline | 0.15 | SBC / revenue vs 5% neutral (shared with EarningsQualityFactor) |

Labels: ≥ `+0.33` **disciplined**, ≤ `−0.33` **destructive**, else **neutral**.

### 5. ROIC durability — *do excess returns persist or fade?*

Requires ≥ 3 years of `roic_history` (otherwise a neutral `0.5` prior). Blend of:

| Sub-component | Weight | Logic |
|---|---|---|
| Level | 0.45 | mean ROIC above an ~8% cost-of-capital floor (20% = excellent) |
| Stability | 0.35 | low historical stdev of ROIC |
| Fade signal | 0.20 | incremental ROIC / mean ROIC (Damodaran Law 4) |

### 6. Fragility / robustness

The headline synthesis. `robustness` is a weighted blend (cash-flow durability
0.35, ROIC durability 0.25, capital allocation 0.20, growth quality 0.10,
revenue quality 0.10), with the two [-1, 1] scores mapped onto [0, 1].
`fragility = 1 − robustness`.

## Consistency with existing factors

Where logic overlaps with `QualityFactor` (ROIC persistence, dilution,
net-debt/EBITDA) and `EarningsQualityFactor` (SBC), the **same formulas and
anchors are reused intentionally**, so the platform reasons consistently rather
than contradicting itself. The Business Reality Engine sits at a higher
altitude: it *classifies* and emits durability/fragility, not a tradable alpha.

## No magic numbers

Every threshold is an explicit, documented module constant in
`src/iam/reasoning/business_reality.py` (e.g. `RECURRING_MIX_FLOOR`,
`FCF_CV_FRAGILE`, `ROIC_LEVEL_FLOOR`, `ROBUSTNESS_WEIGHTS`). Tune them there;
the engine carries no hidden defaults.
