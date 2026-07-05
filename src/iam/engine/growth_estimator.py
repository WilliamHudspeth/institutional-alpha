"""Questionnaire-driven fundamental growth estimator.

Implements the three approaches to estimating growth laid out in Damodaran,
*Investment Valuation* ch. 11 ("Estimating Growth"):

  1. **Historical growth** — trailing revenue/EPS growth. Backward-looking,
     and the chapter is blunt about its limits: standard error balloons with
     firm size and earnings volatility, and the estimation period matters
     more than most people assume (longer windows cut noise but grow stale
     as the business changes).
  2. **Analyst estimates** — external consensus. Useful, but the chapter
     documents a persistent optimism bias and herding among analysts, so raw
     consensus numbers get a small de-bias haircut here rather than being
     taken at face value.
  3. **Fundamental growth** — the "iron law" the chapter leans on hardest,
     because it ties growth to the return earned on capital a firm actually
     retains, instead of extrapolating a trend or borrowing someone else's
     forecast:

         g_equity    = retention ratio (b)     x  ROE
         g_operating = reinvestment rate (RR)  x  ROIC

     Growth built this way is only as good as the excess returns funding it
     — a firm reinvesting heavily at a ROIC below its cost of capital is
     buying growth that *destroys* value, a point the chapter returns to
     repeatedly. The qualitative half of the questionnaire (moat, industry
     lifecycle stage, reinvestment opportunity, management discipline) feeds
     a bounded multiplier on this component for exactly that reason: two
     businesses with identical retention/ROE math deserve different
     confidence in whether that return persists long enough to matter.

None of the three is authoritative alone, so ``QuestionnaireGrowthEngine``
blends them (confidence-weighted, like ``iam.factors`` contributions) into a
single estimate, and — because the whole point of a bottom-up growth number
is to compare it against what the market is already pricing in —
``contrast_with_reverse_dcf`` sits it next to Stage 1's reverse DCF
(``iam.engine.market_implied.MarketImpliedEngine``) so the fundamental case
and the market-implied case are never viewed in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from iam.data.security import Security
from iam.valuation.types import ImpliedExpectations, ValuationResult

# Damodaran ch. 11: analyst estimates skew optimistic and herd toward
# consensus. Applied as a flat de-bias haircut rather than trusted raw.
ANALYST_DEBIAS_HAIRCUT = 0.90

# Bounds for the qualitative overlay on fundamental growth. Kept narrow —
# the qualitative read should nudge confidence in *persistence* of the
# reinvestment story, not substitute for the reinvestment math itself.
QUALITATIVE_MULTIPLIER_MIN = 0.85
QUALITATIVE_MULTIPLIER_MAX = 1.15

DEFAULT_WEIGHTS: dict[str, float] = {
    "historical": 0.20,
    "analyst": 0.30,
    "fundamental": 0.50,
}

_MOAT_SCORE = {"none": -1.0, "narrow": 0.0, "wide": 1.0}
_LIFECYCLE_SCORE = {
    "high_growth": 1.0,
    "mature_growth": 0.5,
    "mature": 0.0,
    "decline": -1.0,
}
_OPPORTUNITY_SCORE = {"scarce": -1.0, "adequate": 0.0, "abundant": 1.0}
_DISCIPLINE_SCORE = {"poor": -1.0, "average": 0.0, "excellent": 1.0}


@dataclass
class GrowthQuestionnaire:
    """Raw answers to the growth questionnaire.

    Every field is optional: a component is skipped (not zero-filled) when
    its inputs are missing, and the blend renormalizes over whatever
    components actually have data.
    """

    # --- 1. Historical growth ---
    historical_revenue_growth: float | None = None  # trailing CAGR, decimal
    historical_eps_growth: float | None = None  # trailing EPS CAGR, decimal
    historical_growth_years: int = 5
    earnings_volatility: str = "moderate"  # "low" | "moderate" | "high"

    # --- 2. Analyst estimates ---
    analyst_consensus_growth: float | None = None  # e.g. 3-5y consensus EPS growth
    analyst_coverage_count: int | None = None  # number of estimates in consensus
    analyst_dispersion: float | None = None  # stdev(estimates) / |mean(estimates)|

    # --- 3. Fundamental drivers ---
    retention_ratio: float | None = None  # b = 1 - dividend payout ratio
    return_on_equity: float | None = None  # ROE, for equity earnings growth
    reinvestment_rate: float | None = None  # RR = (Capex - Dep + dWC) / EBIT(1-t)
    return_on_capital: float | None = None  # ROIC, for operating income growth

    # --- Qualitative overlay on the fundamental component ---
    competitive_moat_strength: str | None = None  # "none" | "narrow" | "wide"
    industry_lifecycle_stage: str | None = None
    # "high_growth" | "mature_growth" | "mature" | "decline"
    reinvestment_opportunity: str | None = None  # "scarce" | "adequate" | "abundant"
    management_capital_discipline: str | None = None  # "poor" | "average" | "excellent"

    # --- Optional weight overrides (normalized over available components) ---
    weight_historical: float | None = None
    weight_analyst: float | None = None
    weight_fundamental: float | None = None


@dataclass
class GrowthEstimateComponent:
    """One method's contribution to the blended growth estimate."""

    label: str
    value: float | None
    weight: float
    confidence: float
    notes: list[str] = field(default_factory=list)

    def effective(self) -> float:
        """Confidence-weighted contribution (0 when the component has no value)."""
        if self.value is None:
            return 0.0
        return self.value * self.confidence


@dataclass
class GrowthEstimateResult:
    """Blended questionnaire-based growth estimate for a security."""

    ticker: str
    blended_growth: float | None
    equity_growth_fundamental: float | None  # b x ROE
    operating_growth_fundamental: float | None  # RR x ROIC
    components: dict[str, GrowthEstimateComponent] = field(default_factory=dict)
    confidence: float = 0.0
    narrative: str = ""
    notes: list[str] = field(default_factory=list)

    # Populated by contrast_with_reverse_dcf().
    market_implied_growth: float | None = None
    growth_gap: float | None = None  # blended - market_implied
    gap_verdict: str = ""

    def explain(self) -> str:
        lines = [f"=== {self.ticker} | Questionnaire Growth Estimate ==="]
        if self.blended_growth is not None:
            lines.append(f"Blended fundamental growth: {self.blended_growth:+.2%}")
        lines.append(f"Confidence: {self.confidence:.2f}")
        lines.append("")
        lines.append("Components:")
        for c in self.components.values():
            val = f"{c.value:+.2%}" if c.value is not None else "n/a"
            lines.append(
                f"  {c.label:24s} value={val:>8s}  weight={c.weight:.2f}  conf={c.confidence:.2f}"
            )
            for note in c.notes:
                lines.append(f"    - {note}")
        if self.market_implied_growth is not None:
            lines.append("")
            lines.append(f"Reverse DCF (market-implied) growth: {self.market_implied_growth:+.2%}")
            if self.growth_gap is not None:
                lines.append(f"Gap (fundamental - market): {self.growth_gap:+.2%}")
            lines.append(f"Verdict: {self.gap_verdict}")
        if self.notes:
            lines.append("")
            lines.extend(f"note: {n}" for n in self.notes)
        return "\n".join(lines)


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _historical_component(q: GrowthQuestionnaire, security: Security) -> GrowthEstimateComponent:
    notes: list[str] = []
    value: float | None = None

    candidates = [g for g in (q.historical_revenue_growth, q.historical_eps_growth) if g is not None]
    if candidates:
        value = sum(candidates) / len(candidates)
        if len(candidates) == 1:
            notes.append("Only one of revenue/EPS historical growth supplied.")
    else:
        history = security.fundamentals.revenue_history
        if len(history) >= 2 and history[-1] > 0:
            years = len(history) - 1
            value = (history[0] / history[-1]) ** (1 / years) - 1
            notes.append(f"Derived from {years}yr revenue history (no questionnaire override).")
        else:
            notes.append("No historical growth data available (questionnaire or fundamentals).")

    confidence = 0.0 if value is None else 0.7
    if value is not None:
        if q.earnings_volatility == "high":
            confidence *= 0.6
            notes.append("High earnings volatility widens the estimation error on trailing growth.")
        elif q.earnings_volatility == "low":
            confidence *= 1.1
        if q.historical_growth_years < 3:
            confidence *= 0.7
            notes.append("Fewer than 3 years of history — small-sample growth rate is noisy.")
        confidence = _clamp(confidence, 0.0, 1.0)

    return GrowthEstimateComponent(
        label="historical", value=value, weight=DEFAULT_WEIGHTS["historical"],
        confidence=confidence, notes=notes,
    )


def _analyst_component(q: GrowthQuestionnaire) -> GrowthEstimateComponent:
    notes: list[str] = []
    value = q.analyst_consensus_growth
    if value is None:
        return GrowthEstimateComponent(
            label="analyst", value=None, weight=DEFAULT_WEIGHTS["analyst"],
            confidence=0.0, notes=["No analyst consensus supplied."],
        )

    debiased = value * ANALYST_DEBIAS_HAIRCUT
    notes.append(
        f"De-biased {ANALYST_DEBIAS_HAIRCUT:.0%} of raw consensus "
        f"({value:+.2%} -> {debiased:+.2%}) — analyst estimates skew optimistic."
    )

    confidence = 0.6
    if q.analyst_coverage_count is not None:
        if q.analyst_coverage_count >= 10:
            confidence += 0.2
        elif q.analyst_coverage_count < 3:
            confidence -= 0.2
            notes.append("Thin coverage (<3 estimates) — consensus is fragile.")
    if q.analyst_dispersion is not None:
        if q.analyst_dispersion > 0.5:
            confidence -= 0.25
            notes.append(f"High dispersion ({q.analyst_dispersion:.0%}) — estimates disagree.")
        elif q.analyst_dispersion < 0.15:
            confidence += 0.1

    confidence = _clamp(confidence, 0.0, 1.0)
    return GrowthEstimateComponent(
        label="analyst", value=debiased, weight=DEFAULT_WEIGHTS["analyst"],
        confidence=confidence, notes=notes,
    )


def _qualitative_multiplier(q: GrowthQuestionnaire) -> tuple[float, list[str]]:
    """Bounded multiplier on fundamental growth reflecting how likely the
    reinvestment story is to persist (moat, lifecycle, opportunity, discipline).
    """
    scores = []
    notes: list[str] = []

    if q.competitive_moat_strength is not None:
        s = _MOAT_SCORE.get(q.competitive_moat_strength)
        if s is not None:
            scores.append(s)
            if s < 0:
                notes.append("No moat — excess returns funding reinvestment growth may not persist.")
    if q.industry_lifecycle_stage is not None:
        s = _LIFECYCLE_SCORE.get(q.industry_lifecycle_stage)
        if s is not None:
            scores.append(s)
            if s < 0:
                notes.append("Industry in decline — reinvestment opportunity is shrinking.")
    if q.reinvestment_opportunity is not None:
        s = _OPPORTUNITY_SCORE.get(q.reinvestment_opportunity)
        if s is not None:
            scores.append(s)
            if s < 0:
                notes.append("Scarce reinvestment opportunity caps how much growth reinvestment can buy.")
    if q.management_capital_discipline is not None:
        s = _DISCIPLINE_SCORE.get(q.management_capital_discipline)
        if s is not None:
            scores.append(s)
            if s < 0:
                notes.append("Weak capital discipline — reinvestment may not earn its cost of capital.")

    if not scores:
        return 1.0, notes

    avg = sum(scores) / len(scores)
    span = QUALITATIVE_MULTIPLIER_MAX - 1.0
    multiplier = 1.0 + avg * span
    return _clamp(multiplier, QUALITATIVE_MULTIPLIER_MIN, QUALITATIVE_MULTIPLIER_MAX), notes


def _fundamental_component(
    q: GrowthQuestionnaire,
) -> tuple[GrowthEstimateComponent, float | None, float | None]:
    """Returns (component, equity_growth, operating_growth)."""
    notes: list[str] = []

    equity_growth: float | None = None
    if q.retention_ratio is not None and q.return_on_equity is not None:
        equity_growth = q.retention_ratio * q.return_on_equity
        if q.return_on_equity < 0:
            notes.append("Negative ROE — equity growth from reinvestment is not meaningful.")
        if not 0.0 <= q.retention_ratio <= 1.5:
            notes.append(f"Retention ratio {q.retention_ratio:.2f} outside plausible [0, 1.5] range.")

    operating_growth: float | None = None
    if q.reinvestment_rate is not None and q.return_on_capital is not None:
        operating_growth = q.reinvestment_rate * q.return_on_capital
        if q.return_on_capital < 0:
            notes.append("Negative ROIC — reinvestment is destroying value, not buying growth.")
        if not 0.0 <= q.reinvestment_rate <= 1.5:
            notes.append(
                f"Reinvestment rate {q.reinvestment_rate:.2f} outside plausible [0, 1.5] range."
            )

    parts = [g for g in (equity_growth, operating_growth) if g is not None]
    if not parts:
        return (
            GrowthEstimateComponent(
                label="fundamental (b x ROE / RR x ROIC)", value=None,
                weight=DEFAULT_WEIGHTS["fundamental"], confidence=0.0,
                notes=["No reinvestment-rate/return-on-capital inputs supplied."],
            ),
            None,
            None,
        )

    raw_value = sum(parts) / len(parts)
    multiplier, qual_notes = _qualitative_multiplier(q)
    value = raw_value * multiplier
    notes.extend(qual_notes)
    if multiplier != 1.0:
        notes.append(f"Qualitative overlay applied: x{multiplier:.2f} ({raw_value:+.2%} -> {value:+.2%}).")

    confidence = 0.85 if len(parts) == 2 else 0.7
    if any("Negative" in n or "destroying" in n for n in notes):
        confidence *= 0.5
    confidence = _clamp(confidence, 0.0, 1.0)

    return (
        GrowthEstimateComponent(
            label="fundamental (b x ROE / RR x ROIC)", value=value,
            weight=DEFAULT_WEIGHTS["fundamental"], confidence=confidence, notes=notes,
        ),
        equity_growth,
        operating_growth,
    )


class QuestionnaireGrowthEngine:
    """Blends historical, analyst, and fundamental growth estimates.

    Usage:
        result = QuestionnaireGrowthEngine().compute(security, questionnaire)
        result = engine.contrast_with_reverse_dcf(result, reverse_dcf_result)
    """

    name = "questionnaire_growth_engine"

    def compute(
        self, security: Security, questionnaire: GrowthQuestionnaire
    ) -> GrowthEstimateResult:
        hist = _historical_component(questionnaire, security)
        analyst = _analyst_component(questionnaire)
        fundamental, equity_g, operating_g = _fundamental_component(questionnaire)

        components = {"historical": hist, "analyst": analyst, "fundamental": fundamental}

        overrides = {
            "historical": questionnaire.weight_historical,
            "analyst": questionnaire.weight_analyst,
            "fundamental": questionnaire.weight_fundamental,
        }
        if any(v is not None for v in overrides.values()):
            for key, comp in components.items():
                comp.weight = overrides[key] if overrides[key] is not None else DEFAULT_WEIGHTS[key]

        # Renormalize over components that actually produced a value.
        available = {k: c for k, c in components.items() if c.value is not None}
        notes: list[str] = []
        if not available:
            return GrowthEstimateResult(
                ticker=security.ticker,
                blended_growth=None,
                equity_growth_fundamental=equity_g,
                operating_growth_fundamental=operating_g,
                components=components,
                confidence=0.0,
                narrative="No questionnaire inputs or fundamentals available to estimate growth.",
                notes=["Every component was skipped for lack of data."],
            )

        total_weight = sum(c.weight for c in available.values())
        if total_weight <= 0:
            notes.append("All component weights were zero — falling back to equal weighting.")
            for c in available.values():
                c.weight = 1.0 / len(available)
            total_weight = 1.0

        blended = sum(c.value * c.weight for c in available.values()) / total_weight  # type: ignore[operator]
        confidence = sum(c.confidence * c.weight for c in available.values()) / total_weight

        skipped = [k for k in components if k not in available]
        if skipped:
            notes.append(f"Skipped (no data): {', '.join(skipped)}.")

        narrative = self._narrative(blended, confidence, available)

        return GrowthEstimateResult(
            ticker=security.ticker,
            blended_growth=blended,
            equity_growth_fundamental=equity_g,
            operating_growth_fundamental=operating_g,
            components=components,
            confidence=confidence,
            narrative=narrative,
            notes=notes,
        )

    @staticmethod
    def _narrative(
        blended: float, confidence: float, available: dict[str, GrowthEstimateComponent]
    ) -> str:
        used = ", ".join(f"{c.label} ({c.weight:.0%})" for c in available.values())
        return (
            f"Questionnaire-based growth estimate: {blended:+.2%} "
            f"(confidence {confidence:.2f}), blended from: {used}."
        )

    def contrast_with_reverse_dcf(
        self,
        result: GrowthEstimateResult,
        reverse_dcf: ValuationResult | ImpliedExpectations | float,
    ) -> GrowthEstimateResult:
        """Surface the reverse-DCF (market-implied) growth alongside the
        questionnaire-based fundamental estimate, and characterize the gap.

        Accepts the raw implied growth rate, a Stage-1 ``ImpliedExpectations``,
        or the full ``ValuationResult`` produced by ``MarketImpliedEngine``.
        """
        if isinstance(reverse_dcf, ValuationResult):
            implied = reverse_dcf.implied.implied_revenue_growth if reverse_dcf.implied else None
        elif isinstance(reverse_dcf, ImpliedExpectations):
            implied = reverse_dcf.implied_revenue_growth
        else:
            implied = reverse_dcf

        result.market_implied_growth = implied

        if implied is None or result.blended_growth is None:
            result.gap_verdict = "Cannot compare — missing fundamental or market-implied growth."
            return result

        gap = result.blended_growth - implied
        result.growth_gap = gap
        result.gap_verdict = self._gap_verdict(result.blended_growth, implied, gap)
        return result

    @staticmethod
    def _gap_verdict(fundamental: float, market: float, gap: float) -> str:
        gap_pct = gap * 100
        if abs(gap) < 0.01:
            return (
                f"Fundamental growth ({fundamental:+.1%}) and market-implied growth "
                f"({market:+.1%}) are aligned — the price isn't demanding more than the "
                f"business's own reinvestment economics can plausibly deliver."
            )
        if gap > 0:
            return (
                f"Fundamental growth ({fundamental:+.1%}) exceeds what the market is "
                f"pricing in ({market:+.1%}) by {abs(gap_pct):.1f}pp — the business may be "
                f"underpriced relative to its own reinvestment economics, or the market is "
                f"discounting execution risk not captured in this questionnaire."
            )
        return (
            f"The market is pricing in more growth ({market:+.1%}) than the fundamental "
            f"case supports ({fundamental:+.1%}) by {abs(gap_pct):.1f}pp — the price is "
            f"demanding growth the reinvestment math here doesn't yet justify."
        )
