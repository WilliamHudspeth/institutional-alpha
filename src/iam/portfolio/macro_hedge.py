"""Macro hedge recommendations driven by portfolio elasticity.

This module answers *what kind of hedge* and *how much*, not specific
option strikes — live options pricing is out of scope.

Hedge sizing is driven by the **portfolio's aggregate elasticity profile**
(weighted average of position-level elasticities from
:class:`iam.elasticity.ElasticityScorer`), not generic textbook rules.
This makes it consistent with the rest of the codebase's theory-first
design (see :mod:`iam.elasticity` and ``docs/business_reality.md``).
"""

from __future__ import annotations

from dataclasses import dataclass

from iam.elasticity.types import ElasticityProfile
from iam.pipeline.macro_regimes import MacroRegimeAssessment, MacroRegime
from iam.portfolio.types import Portfolio

# ── Elasticity thresholds ──────────────────────────────────────────────────
# Aggregate rate elasticity above which a duration hedge is recommended.
# 1.5 on the 0-3 scale corresponds to a cash-flow duration significantly
# above the baseline (a 100bps rate move would swing value by ~1.5× the
# baseline DCF sensitivity).
HIGH_RATE_ELASTICITY_THRESHOLD: float = 1.5

# Aggregate growth elasticity above which a growth-shock hedge
# (index put / sector short) is recommended.
HIGH_GROWTH_ELASTICITY_THRESHOLD: float = 1.3

# ── Hedge sizing ──────────────────────────────────────────────────────────
# Base hedge size as a fraction of portfolio value when threshold is met.
HEDGE_BASE_FRACTION: float = 0.05  # 5% of portfolio

# Additional hedge fraction per unit of elasticity above threshold.
HEDGE_SCALE_PER_UNIT: float = 0.03  # 3% per extra elasticity unit

# Maximum recommended hedge size as a fraction of portfolio value.
MAX_HEDGE_FRACTION: float = 0.20  # 20% of portfolio

# Fraction applied to hedges when the regime is not supportive of the
# portfolio's primary risk (e.g., rate hedge during an easing regime).
REGIME_DISCOUNT_FACTOR: float = 0.5


@dataclass
class HedgeRecommendation:
    """A concrete, sizeable hedge recommendation.

    ``instrument_type`` describes the kind of hedge (e.g. ``"index_put"``,
    ``"duration_hedge"``, ``"sector_short"``).  ``suggested_size_pct`` is
    the notional size as a percentage of portfolio value.  No specific
    option contracts or strikes are provided — that would require live
    pricing integration which is out of scope.
    """

    instrument_type: str
    rationale: str
    suggested_size_pct: float


class MacroHedgeEngine:
    """Recommend macro hedges based on the portfolio's aggregate elasticity.

    The engine computes a **weighted-average elasticity** across all
    positions (using each position's weight × its
    :class:`~iam.elasticity.types.ElasticityProfile` from
    :class:`~iam.elasticity.ElasticityScorer`) and sizes hedges
    proportionally to the aggregate exposure.

    Missing elasticity data is handled gracefully: positions without a
    measurable elasticity are excluded from the aggregate, and if no
    data is available at all, no hedge is recommended.
    """

    @staticmethod
    def recommend_hedges(
        portfolio: Portfolio,
        positions_elasticity: dict[str, ElasticityProfile],
        current_regime: MacroRegimeAssessment | None = None,
    ) -> list[HedgeRecommendation]:
        """Generate hedge recommendations.

        Args:
            portfolio: The portfolio to hedge.
            positions_elasticity: Elasticity profiles keyed by ticker,
                as produced by :meth:`iam.elasticity.ElasticityScorer.profile`.
            current_regime: Current macro regime assessment (optional).
                Used to discount hedges that work against the prevailing
                regime (e.g., a rate hedge during an easing cycle).

        Returns:
            List of :class:`HedgeRecommendation` — may be empty if no
            material elasticity exposure is detected.
        """
        recommendations: list[HedgeRecommendation] = []

        # Compute weighted-average elasticity
        agg_rate_el, agg_growth_el = MacroHedgeEngine._aggregate_elasticity(
            portfolio, positions_elasticity
        )

        if agg_rate_el is None and agg_growth_el is None:
            return recommendations

        # Determine regime discount
        regime = current_regime.regime if current_regime else MacroRegime.NEUTRAL
        is_easing = regime == MacroRegime.EASING
        is_tightening = regime == MacroRegime.TIGHTENING

        # Duration hedge for rate-sensitive portfolios
        if agg_rate_el is not None and agg_rate_el > HIGH_RATE_ELASTICITY_THRESHOLD:
            excess = agg_rate_el - HIGH_RATE_ELASTICITY_THRESHOLD
            size_pct = HEDGE_BASE_FRACTION + excess * HEDGE_SCALE_PER_UNIT
            # Discount if rates are currently falling (easing reduces rate risk)
            if is_easing:
                size_pct *= REGIME_DISCOUNT_FACTOR
                rationale = (
                    f"Portfolio rate elasticity {agg_rate_el:.1f}/{HIGH_RATE_ELASTICITY_THRESHOLD:.0f}+ "
                    f"suggests duration sensitivity, but easing regime reduces near-term "
                    f"rate risk.  Consider a reduced duration hedge at ~{size_pct*100:.0f}% "
                    f"of portfolio value via long-dated treasury puts or a rate-sensitive "
                    f"sector short."
                )
            else:
                regime_note = (
                    " Current tightening regime amplifies duration risk."
                    if is_tightening
                    else ""
                )
                rationale = (
                    f"Portfolio rate elasticity {agg_rate_el:.1f}/{HIGH_RATE_ELASTICITY_THRESHOLD:.0f}+ "
                    f"indicates significant duration exposure.{regime_note} "
                    f"Consider a duration hedge at ~{size_pct*100:.0f}% of portfolio value "
                    f"via long-dated treasury puts or a rate-sensitive sector short."
                )

            size_pct = min(size_pct, MAX_HEDGE_FRACTION)
            recommendations.append(
                HedgeRecommendation(
                    instrument_type="duration_hedge",
                    rationale=rationale,
                    suggested_size_pct=round(size_pct * 100, 1),
                )
            )

        # Growth-shock hedge for fixed-cost-heavy portfolios
        if agg_growth_el is not None and agg_growth_el > HIGH_GROWTH_ELASTICITY_THRESHOLD:
            excess = agg_growth_el - HIGH_GROWTH_ELASTICITY_THRESHOLD
            size_pct = HEDGE_BASE_FRACTION + excess * HEDGE_SCALE_PER_UNIT

            regime_note = ""
            if is_tightening:
                regime_note = (
                    " Tightening regime compounds growth risk for high-operating-leverage names."
                )

            rationale = (
                f"Portfolio growth elasticity {agg_growth_el:.1f}/{HIGH_GROWTH_ELASTICITY_THRESHOLD:.0f}+ "
                f"reflects high fixed-cost intensity (operating leverage).{regime_note} "
                f"Consider an index put or sector short at ~{size_pct*100:.0f}% of portfolio "
                f"value to hedge against a growth slowdown."
            )

            size_pct = min(size_pct, MAX_HEDGE_FRACTION)
            recommendations.append(
                HedgeRecommendation(
                    instrument_type="index_put",
                    rationale=rationale,
                    suggested_size_pct=round(size_pct * 100, 1),
                )
            )

        return recommendations

    @staticmethod
    def _aggregate_elasticity(
        portfolio: Portfolio,
        positions_elasticity: dict[str, ElasticityProfile],
    ) -> tuple[float | None, float | None]:
        """Compute weighted-average rate and growth elasticity.

        Only positions with measurable elasticity data contribute to the
        aggregate.  Returns ``(None, None)`` when no data is available.
        """
        total_weight = 0.0
        agg_rate = 0.0
        agg_growth = 0.0
        rate_count = 0
        growth_count = 0

        for pos in portfolio.positions:
            ep = positions_elasticity.get(pos.ticker)
            if ep is None:
                continue
            w = pos.weight
            if ep.rate_elasticity is not None:
                agg_rate += w * ep.rate_elasticity
                rate_count += 1
            if ep.growth_elasticity is not None:
                agg_growth += w * ep.growth_elasticity
                growth_count += 1
            total_weight += w

        if total_weight == 0 or (rate_count == 0 and growth_count == 0):
            return None, None

        avg_rate = agg_rate / total_weight if rate_count > 0 else None
        avg_growth = agg_growth / total_weight if growth_count > 0 else None
        return avg_rate, avg_growth
