"""Business Reality Engine (Seven-Engine architecture, Engine #3).

A *theory-first* reasoning layer that decodes how durable a business actually
is, rather than producing yet another fair-value number. It answers the
Damodaran "Business Reality" question:

    *Revenue durability, cash-flow quality, capital efficiency, management
    discipline — does the business deserve the story the price is telling?*

The engine produces a structured :class:`BusinessReality` assessment with six
reasoning dimensions:

1. **Revenue-quality classification** — recurring / transactional / cyclical /
   regulated. *What kind of top line is this?*
2. **Cash-flow durability** (0–1) — what fraction of cash flow plausibly
   persists if growth stalls? Labelled stable / mean-reverting /
   capital-markets-dependent. (Damodaran operating leverage; Mauboussin
   reflexivity.)
3. **Growth-quality decomposition** (−1…1) — organic, per-share, high-marginal-
   ROIC growth (good) vs dilution/acquisition-funded growth (bad).
   (Damodaran Law 2: growth requires reinvestment.)
4. **Capital-allocation assessment** (−1…1) — disciplined / neutral /
   destructive, from dilution, buyback discipline, reinvestment efficiency,
   debt and SBC discipline.
5. **ROIC durability** (0–1) — confidence that excess returns persist rather
   than mean-revert. (Damodaran Law 4: excess returns fade.)
6. **Fragility / robustness** (0–1) — the headline synthesis. ``fragility`` is
   the hook a future Thesis-Drift Detector / Valuation Battlefield consumes to
   degrade conviction on fragile names.

Design notes
------------
* This is a *reasoning module*, not an alpha factor. It deliberately does **not**
  feed the composite score (that would require re-normalising the existing
  factor weights and re-baselining backtests). It is surfaced as a *diagnostic*
  lens (see :mod:`iam.lenses.business_reality_lens`) and as structured output
  for downstream reasoning.
* Every threshold is an explicit, documented module constant (the roadmap's
  "No Magic Numbers" principle). Where logic overlaps with
  :class:`iam.factors.quality.QualityFactor` or
  :class:`iam.factors.earnings_quality.EarningsQualityFactor`, the same
  formulas/constants are reused intentionally so the platform reasons
  consistently.
* Missing data never raises: each dimension degrades ``confidence`` and falls
  back to a neutral prior, mirroring the factor/lens convention.

Conventions (inherited from :mod:`iam.data.security`):
  - Percentages are decimals (0.15 == 15%).
  - Historical lists are most-recent-first (index 0 == newest).
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from enum import Enum

from iam.data.security import Security
from iam.factors.base import Factor

# ---------------------------------------------------------------------------
# Tunable constants (documented; no silent magic numbers)
# ---------------------------------------------------------------------------

# --- Revenue-quality classification ---
# Qualitative recurring_revenue_mix at/above this => clearly subscription-like.
RECURRING_MIX_FLOOR = 0.50
# A stable-margin business with gross margin above this looks recurring-like
# (software/subscription economics) when its revenue is also smooth.
RECURRING_MARGIN_FLOOR = 0.55
# Coefficient of variation (stdev/mean) of revenue history thresholds.
REVENUE_CV_CYCLICAL = 0.25  # at/above => lumpy/cyclical top line
REVENUE_CV_STABLE = 0.10  # at/below => smooth top line

# yfinance-style sector buckets. Sector is only a tiebreaker; margins, revenue
# volatility, and the recurring-mix input dominate the classification.
CYCLICAL_SECTORS = frozenset(
    {
        "energy",
        "basic materials",
        "materials",
        "industrials",
        "consumer cyclical",
        "real estate",
        "financial services",
        "financials",
    }
)
REGULATED_SECTORS = frozenset({"utilities"})

# --- Cash-flow durability ---
# CV of FCF history: low variance => durable cash flows.
FCF_CV_DURABLE = 0.15  # at/below => very stable
FCF_CV_FRAGILE = 0.50  # at/above => highly variable
# Durability label cut points on the [0, 1] durability score.
DURABILITY_STABLE_FLOOR = 0.60
DURABILITY_MEAN_REVERTING_FLOOR = 0.35
# Revenue-quality coupling: how much each class lifts/cuts durability prior.
REVENUE_QUALITY_DURABILITY = {
    "recurring": 0.85,
    "regulated": 0.80,
    "transactional": 0.50,
    "cyclical": 0.25,
    "unknown": 0.50,
}

# --- Growth quality ---
# Revenue-per-share growth spread (revenue CAGR − share CAGR) that counts as a
# strong organic signal when normalised to [-1, 1].
ORGANIC_SPREAD_STRONG = 0.10  # 10pp of per-share growth == strong
# Incremental ROIC neutral / great anchors (shared with QualityFactor logic:
# 10% neutral, 20%+ great).
INCREMENTAL_ROIC_NEUTRAL = 0.10
INCREMENTAL_ROIC_SPAN = 0.10

# --- Capital allocation ---
# Dilution: +5%/yr issuance is bad, buybacks are good. Scale chosen so that
# 5%/yr dilution maps to ≈ −1 (shared with QualityFactor.dilution_control).
DILUTION_SCALE = 20.0
# Net-debt / EBITDA neutral anchor (shared with QualityFactor balance sheet).
NET_DEBT_EBITDA_NEUTRAL = 1.0
NET_DEBT_EBITDA_SPAN = 2.0
# SBC as % of revenue: <2% great, 5% neutral, 15%+ bad (shared with
# EarningsQualityFactor).
SBC_NEUTRAL_PCT = 0.05
SBC_SCALE = 10.0
# Capital-allocation label cut points on the [-1, 1] score.
CAPITAL_ALLOCATION_DISCIPLINED_FLOOR = 0.33
CAPITAL_ALLOCATION_DESTRUCTIVE_CEIL = -0.33

# --- ROIC durability ---
# Level anchor: ~8% approximates a cost-of-capital floor, 20% is excellent.
ROIC_LEVEL_FLOOR = 0.08
ROIC_LEVEL_SPAN = 0.12
# Stability: 6% stdev of historical ROIC ~ neutral.
ROIC_STDEV_NEUTRAL = 0.06

# --- Fragility / robustness synthesis weights (sum to 1.0) ---
ROBUSTNESS_WEIGHTS = {
    "cashflow_durability": 0.35,
    "roic_durability": 0.25,
    "capital_allocation": 0.20,
    "growth_quality": 0.10,
    "revenue_quality": 0.10,
}

# Neutral prior used when a dimension cannot be computed at all.
NEUTRAL = 0.5


class RevenueQuality(Enum):
    """Classification of the durability/character of a company's top line."""

    RECURRING = "recurring"
    TRANSACTIONAL = "transactional"
    CYCLICAL = "cyclical"
    REGULATED = "regulated"
    UNKNOWN = "unknown"


@dataclass
class BusinessReality:
    """Structured output of the :class:`BusinessRealityEngine`.

    All scores are bounded:
      - ``*_durability`` and ``robustness``/``fragility`` are in [0, 1].
      - ``growth_quality`` and ``capital_allocation`` are in [-1, 1]
        (positive == healthy).
      - ``confidence`` in [0, 1] reflects how much data was available.
    """

    ticker: str
    revenue_quality: RevenueQuality
    revenue_quality_confidence: float
    cashflow_durability: float
    cashflow_durability_label: str
    growth_quality: float
    growth_decomposition: dict[str, float]
    capital_allocation: float
    capital_allocation_label: str
    roic_durability: float
    fragility: float
    robustness: float
    narrative: str
    confidence: float
    components: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def _coefficient_of_variation(values: list[float]) -> float | None:
    """Return stdev/|mean| for a series, or None if undefined.

    Uses population stdev (matches the factor library convention). Needs at
    least two points and a non-zero mean.
    """
    cleaned = [v for v in values if v is not None]
    if len(cleaned) < 2:
        return None
    mean = statistics.mean(cleaned)
    if mean == 0:
        return None
    return statistics.pstdev(cleaned) / abs(mean)


def _cagr(history: list[float]) -> float | None:
    """Compound annual growth rate from a most-recent-first history list.

    newest == history[0], oldest == history[-1]. Returns None when the series
    is too short or the oldest value is non-positive (CAGR undefined).
    """
    cleaned = [v for v in history if v is not None]
    if len(cleaned) < 2:
        return None
    newest = cleaned[0]
    oldest = cleaned[-1]
    periods = len(cleaned) - 1
    if oldest <= 0 or newest <= 0:
        return None
    return float((newest / oldest) ** (1 / periods) - 1)


class BusinessRealityEngine:
    """Computes a :class:`BusinessReality` assessment for a Security.

    Stateless and side-effect-free: it never mutates the Security and performs
    no I/O, matching the factor/lens contract.
    """

    name = "business_reality"

    def assess(self, security: Security) -> BusinessReality:
        components: dict[str, float] = {}
        notes: list[str] = []

        rev_quality, rev_conf = self._classify_revenue(security, notes)
        durability, durability_label, cf_conf = self._cashflow_durability(
            security, rev_quality, components, notes
        )
        growth_quality, growth_decomp, growth_conf = self._growth_quality(
            security, components, notes
        )
        capital_allocation, ca_label, ca_conf = self._capital_allocation(
            security, components, notes
        )
        roic_durability, roic_conf = self._roic_durability(security, components, notes)

        # --- Fragility / robustness synthesis -------------------------------
        rev_quality_score = REVENUE_QUALITY_DURABILITY[rev_quality.value]
        robustness = Factor.weighted_average(
            {
                "cf": (durability, ROBUSTNESS_WEIGHTS["cashflow_durability"]),
                "roic": (roic_durability, ROBUSTNESS_WEIGHTS["roic_durability"]),
                # map [-1, 1] scores onto [0, 1]
                "ca": ((capital_allocation + 1) / 2, ROBUSTNESS_WEIGHTS["capital_allocation"]),
                "gq": ((growth_quality + 1) / 2, ROBUSTNESS_WEIGHTS["growth_quality"]),
                "rq": (rev_quality_score, ROBUSTNESS_WEIGHTS["revenue_quality"]),
            }
        )
        robustness = Factor.clamp(robustness, 0.0, 1.0)
        fragility = Factor.clamp(1.0 - robustness, 0.0, 1.0)
        components["robustness"] = robustness
        components["fragility"] = fragility

        # Overall confidence: average of the dimension confidences.
        confidence = statistics.mean([rev_conf, cf_conf, growth_conf, ca_conf, roic_conf])

        narrative = self._narrative(
            security.ticker,
            rev_quality,
            durability_label,
            ca_label,
            fragility,
        )

        return BusinessReality(
            ticker=security.ticker,
            revenue_quality=rev_quality,
            revenue_quality_confidence=rev_conf,
            cashflow_durability=durability,
            cashflow_durability_label=durability_label,
            growth_quality=growth_quality,
            growth_decomposition=growth_decomp,
            capital_allocation=capital_allocation,
            capital_allocation_label=ca_label,
            roic_durability=roic_durability,
            fragility=fragility,
            robustness=robustness,
            narrative=narrative,
            confidence=Factor.clamp(confidence, 0.0, 1.0),
            components=components,
            notes=notes,
        )

    # ------------------------------------------------------------------
    # Dimension 1: revenue-quality classification
    # ------------------------------------------------------------------
    def _classify_revenue(
        self, security: Security, notes: list[str]
    ) -> tuple[RevenueQuality, float]:
        f = security.fundamentals
        sector = (security.sector or "").strip().lower()
        recurring_mix = security.qualitative.get("recurring_revenue_mix")
        rev_cv = _coefficient_of_variation(f.revenue_history)
        gm = f.gross_margin

        # Count available signals to scale confidence.
        signals = sum(x is not None for x in (recurring_mix, rev_cv, gm)) + (1 if sector else 0)
        confidence = Factor.clamp(0.4 + 0.15 * signals, 0.0, 1.0)

        # 1. Explicit recurring-revenue mix dominates.
        if recurring_mix is not None and recurring_mix >= RECURRING_MIX_FLOOR:
            return RevenueQuality.RECURRING, confidence

        # 2. Regulated sectors (utilities) are their own category.
        if sector in REGULATED_SECTORS:
            return RevenueQuality.REGULATED, confidence

        # 3. Lumpy revenue or cyclical sector => cyclical.
        if (rev_cv is not None and rev_cv >= REVENUE_CV_CYCLICAL) or sector in CYCLICAL_SECTORS:
            return RevenueQuality.CYCLICAL, confidence

        # 4. High, stable gross margin with smooth revenue => recurring-like.
        if (
            gm is not None
            and gm >= RECURRING_MARGIN_FLOOR
            and rev_cv is not None
            and rev_cv <= REVENUE_CV_STABLE
        ):
            return RevenueQuality.RECURRING, confidence

        # 5. Nothing to classify on at all.
        if signals == 0:
            notes.append("No revenue-quality signals available; classification unknown.")
            return RevenueQuality.UNKNOWN, Factor.clamp(confidence, 0.0, 0.3)

        return RevenueQuality.TRANSACTIONAL, confidence

    # ------------------------------------------------------------------
    # Dimension 2: cash-flow durability
    # ------------------------------------------------------------------
    def _cashflow_durability(
        self,
        security: Security,
        rev_quality: RevenueQuality,
        components: dict[str, float],
        notes: list[str],
    ) -> tuple[float, str, float]:
        f = security.fundamentals
        confidence = 1.0

        # Hard rule (Damodaran): a business that does not self-fund — negative
        # FCF — is capital-markets-dependent regardless of other signals.
        if f.fcf_ttm is not None and f.fcf_ttm < 0:
            notes.append("Negative FCF: cash flows are capital-markets-dependent.")
            components["cashflow_durability"] = 0.15
            return 0.15, "capital_markets_dependent", 0.9

        parts: dict[str, tuple[float | None, float]] = {}

        # (a) FCF stability from historical variation.
        fcf_cv = _coefficient_of_variation(f.fcf_history)
        if fcf_cv is not None:
            # CV at/below FCF_CV_DURABLE -> 1.0; at/above FCF_CV_FRAGILE -> 0.0.
            span = FCF_CV_FRAGILE - FCF_CV_DURABLE
            stability = Factor.clamp((FCF_CV_FRAGILE - fcf_cv) / span, 0.0, 1.0)
            components["fcf_stability"] = stability
            parts["fcf_stability"] = (stability, 0.35)
        else:
            confidence *= 0.85

        # (b) Operating-leverage proxy: share of gross profit consumed by fixed
        # opex. High fixed-cost intensity -> FCF collapses if growth stalls.
        if f.gross_margin is not None and f.operating_margin is not None and f.gross_margin > 0:
            fixed_cost_intensity = (f.gross_margin - f.operating_margin) / f.gross_margin
            fixed_cost_intensity = Factor.clamp(fixed_cost_intensity, 0.0, 1.0)
            # Low intensity (variable cost base) -> durable; high -> fragile.
            op_leverage_score = 1.0 - fixed_cost_intensity
            components["operating_leverage"] = op_leverage_score
            parts["operating_leverage"] = (op_leverage_score, 0.30)
        else:
            confidence *= 0.9

        # (c) Revenue-quality coupling prior.
        rq_prior = REVENUE_QUALITY_DURABILITY[rev_quality.value]
        components["revenue_quality_prior"] = rq_prior
        parts["revenue_quality"] = (rq_prior, 0.35)

        durability = Factor.weighted_average(parts)
        durability = Factor.clamp(durability, 0.0, 1.0)
        components["cashflow_durability"] = durability

        label = self._durability_label(durability)
        return durability, label, Factor.clamp(confidence, 0.0, 1.0)

    @staticmethod
    def _durability_label(durability: float) -> str:
        if durability >= DURABILITY_STABLE_FLOOR:
            return "stable"
        if durability >= DURABILITY_MEAN_REVERTING_FLOOR:
            return "mean_reverting"
        return "capital_markets_dependent"

    # ------------------------------------------------------------------
    # Dimension 3: growth-quality decomposition
    # ------------------------------------------------------------------
    def _growth_quality(
        self,
        security: Security,
        components: dict[str, float],
        notes: list[str],
    ) -> tuple[float, dict[str, float], float]:
        f = security.fundamentals
        confidence = 1.0
        decomp: dict[str, float] = {}
        parts: dict[str, tuple[float | None, float]] = {}

        revenue_cagr = _cagr(f.revenue_history)
        share_cagr = _cagr(f.shares_outstanding_history)

        # (a) Organic, per-share growth spread: revenue growth net of dilution.
        if revenue_cagr is not None:
            decomp["revenue_cagr"] = revenue_cagr
            sc = share_cagr if share_cagr is not None else 0.0
            if share_cagr is None:
                confidence *= 0.85
                notes.append("Share-count history unavailable; assumed flat for growth quality.")
            decomp["share_cagr"] = sc
            organic_spread = revenue_cagr - sc
            decomp["organic_spread"] = organic_spread
            spread_score = Factor.clamp(organic_spread / ORGANIC_SPREAD_STRONG, -1.0, 1.0)
            components["organic_growth"] = spread_score
            parts["organic"] = (spread_score, 0.55)
        else:
            confidence *= 0.8
            notes.append("Revenue history unavailable; growth quality is low-confidence.")

        # (b) Marginal returns on reinvested capital (Damodaran Law 2).
        if f.incremental_roic is not None:
            decomp["incremental_roic"] = f.incremental_roic
            iroic_score = Factor.clamp(
                (f.incremental_roic - INCREMENTAL_ROIC_NEUTRAL) / INCREMENTAL_ROIC_SPAN
            )
            components["marginal_roic"] = iroic_score
            parts["marginal_roic"] = (iroic_score, 0.30)
        else:
            confidence *= 0.85

        # (c) TAM realism (qualitative, optional). Expected in [0, 1].
        tam = security.qualitative.get("tam_remaining")
        if tam is not None:
            tam_score = Factor.clamp(tam * 2 - 1)
            decomp["tam_remaining"] = float(tam)
            components["tam_realism"] = tam_score
            parts["tam"] = (tam_score, 0.15)
        else:
            confidence *= 0.95

        growth_quality = Factor.clamp(Factor.weighted_average(parts))
        components["growth_quality"] = growth_quality
        return growth_quality, decomp, Factor.clamp(confidence, 0.0, 1.0)

    # ------------------------------------------------------------------
    # Dimension 4: capital-allocation assessment
    # ------------------------------------------------------------------
    def _capital_allocation(
        self,
        security: Security,
        components: dict[str, float],
        notes: list[str],
    ) -> tuple[float, str, float]:
        f = security.fundamentals
        confidence = 1.0
        parts: dict[str, tuple[float | None, float]] = {}

        # (a) Dilution / buyback discipline (shared with QualityFactor).
        share_cagr = _cagr(f.shares_outstanding_history)
        if share_cagr is not None:
            dilution_score = Factor.clamp(-share_cagr * DILUTION_SCALE)
            components["dilution_discipline"] = dilution_score
            parts["dilution"] = (dilution_score, 0.35)
        else:
            confidence *= 0.85

        # (b) Reinvestment efficiency (incremental ROIC).
        if f.incremental_roic is not None:
            reinvest_score = Factor.clamp(
                (f.incremental_roic - INCREMENTAL_ROIC_NEUTRAL) / INCREMENTAL_ROIC_SPAN
            )
            components["reinvestment_efficiency"] = reinvest_score
            parts["reinvest"] = (reinvest_score, 0.30)
        else:
            confidence *= 0.9

        # (c) Debt discipline: net-debt / EBITDA (shared with QualityFactor).
        if (
            f.ebitda_ttm
            and f.total_debt is not None
            and f.cash_and_equivalents is not None
            and f.ebitda_ttm != 0
        ):
            net_debt = f.total_debt - f.cash_and_equivalents
            nd_ebitda = net_debt / f.ebitda_ttm
            debt_score = Factor.clamp(-(nd_ebitda - NET_DEBT_EBITDA_NEUTRAL) / NET_DEBT_EBITDA_SPAN)
            components["debt_discipline"] = debt_score
            parts["debt"] = (debt_score, 0.20)
        else:
            confidence *= 0.9

        # (d) SBC discipline (shared with EarningsQualityFactor).
        if f.sbc_ttm is not None and f.revenue_ttm and f.revenue_ttm > 0:
            sbc_pct = f.sbc_ttm / f.revenue_ttm
            sbc_score = Factor.clamp(-(sbc_pct - SBC_NEUTRAL_PCT) * SBC_SCALE)
            components["sbc_discipline"] = sbc_score
            parts["sbc"] = (sbc_score, 0.15)
        else:
            confidence *= 0.95

        capital_allocation = Factor.clamp(Factor.weighted_average(parts))
        components["capital_allocation"] = capital_allocation
        label = self._capital_allocation_label(capital_allocation)
        return capital_allocation, label, Factor.clamp(confidence, 0.0, 1.0)

    @staticmethod
    def _capital_allocation_label(score: float) -> str:
        if score >= CAPITAL_ALLOCATION_DISCIPLINED_FLOOR:
            return "disciplined"
        if score <= CAPITAL_ALLOCATION_DESTRUCTIVE_CEIL:
            return "destructive"
        return "neutral"

    # ------------------------------------------------------------------
    # Dimension 5: ROIC durability (excess-return fade)
    # ------------------------------------------------------------------
    def _roic_durability(
        self,
        security: Security,
        components: dict[str, float],
        notes: list[str],
    ) -> tuple[float, float]:
        f = security.fundamentals
        if len(f.roic_history) < 3:
            notes.append("ROIC history too short; ROIC durability is a neutral prior.")
            components["roic_durability"] = NEUTRAL
            return NEUTRAL, 0.5

        confidence = 1.0
        mean_roic = statistics.mean(f.roic_history)
        stdev = statistics.pstdev(f.roic_history)

        # Level: how far above the cost-of-capital floor.
        level = Factor.clamp((mean_roic - ROIC_LEVEL_FLOOR) / ROIC_LEVEL_SPAN, 0.0, 1.0)
        # Stability: low variance => durable.
        stability = Factor.clamp(1 - (stdev / ROIC_STDEV_NEUTRAL), 0.0, 1.0)

        parts: dict[str, tuple[float | None, float]] = {
            "level": (level, 0.45),
            "stability": (stability, 0.35),
        }

        # Fade signal (Damodaran Law 4): incremental ROIC below the historical
        # mean implies excess returns are already fading.
        if f.incremental_roic is not None and mean_roic > 0:
            fade = Factor.clamp(f.incremental_roic / mean_roic, 0.0, 1.0)
            components["roic_fade"] = fade
            parts["fade"] = (fade, 0.20)
        else:
            confidence *= 0.9

        durability = Factor.clamp(Factor.weighted_average(parts), 0.0, 1.0)
        components["roic_durability"] = durability
        return durability, Factor.clamp(confidence, 0.0, 1.0)

    # ------------------------------------------------------------------
    # Narrative
    # ------------------------------------------------------------------
    @staticmethod
    def _narrative(
        ticker: str,
        rev_quality: RevenueQuality,
        durability_label: str,
        ca_label: str,
        fragility: float,
    ) -> str:
        if fragility >= 0.66:
            robustness_word = "fragile"
        elif fragility >= 0.34:
            robustness_word = "moderately robust"
        else:
            robustness_word = "robust"
        durability_phrase = durability_label.replace("_", " ")
        return (
            f"{ticker}: {rev_quality.value} revenue with {durability_phrase} cash flows; "
            f"{ca_label} capital allocation. Business looks {robustness_word} "
            f"(fragility {fragility:.2f})."
        )
