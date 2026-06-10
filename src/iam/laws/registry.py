"""Damodaran Laws constraint layer (v0.5 reasoning engine).

Theory-first consistency checks that *flag fragile analyses* rather than
inventing numbers (ROADMAP, "Damodaran Laws — Theory-First Consistency
Checks"):

  * **LAW 1 — Narrative must match numbers.** High growth + expanding margins
    is a competitive-moat story that needs an explanation; high growth +
    shrinking margins is a reinvestment story (probably valid).
  * **LAW 2 — Growth requires reinvestment.** ``g = ROIC × reinvestment_rate``
    is a law. Forecast growth the company's economics cannot support is
    flagged, not silently accepted.
  * **LAW 3 — Terminal growth ≤ risk-free rate.** Already enforced by the
    input guards; folded into the registry so every analysis carries the
    check in its audit trail.
  * **LAW 4 — Excess returns fade.** High ROIC attracts competition. A model
    that holds aggressive growth flat for a decade while ROIC sits far above
    the cost of capital is assuming an unexplained perpetual moat.
  * **LAW 5 — Risk is not double-counted.** Risk lives in the cash flows OR
    the discount rate, never both. An elevated WACC *and* haircut growth
    (or a depressed WACC *and* heroic growth) double-counts in one direction.

Design notes
------------
* Pure function of the ``Security`` plus the assumptions the valuation
  actually used (the ``assumptions`` dict of the Stage 3 intrinsic
  ``ValuationResult``). No I/O, no mutation — the same contract as
  ``iam.lenses.base.BaseLens`` and ``iam.elasticity``.
* Missing data never raises: a law that cannot be checked reports
  ``NOT_EVALUATED`` and the report's conviction multiplier is unaffected.
* Every threshold is an explicit, documented module constant (the roadmap's
  "No Magic Numbers" principle).

Conventions (inherited from :mod:`iam.data.security`):
  - Percentages are decimals (0.15 == 15%).
  - Historical lists are most-recent-first (index 0 == newest).
"""

from __future__ import annotations

from collections.abc import Mapping

from iam.data.security import Security
from iam.elasticity.math_utils import clamp, mean
from iam.laws.fade import (
    DEFAULT_FADE_YEARS,
    excess_return_fade_path,
    fade_adjusted_growth,
)
from iam.laws.types import LawCheck, LawReport, LawStatus
from iam.valuation.types import ImpliedExpectations

# --- Shared anchors ----------------------------------------------------------

# Risk-free anchor when the caller supplies none; matches the rf used by the
# orchestrator's dynamic-WACC build.
DEFAULT_RISK_FREE = 0.043
# Generalist equity cost of capital; matches MarketImpliedEngine / FCFEDCF.
DEFAULT_WACC_BASELINE = 0.09

# --- LAW 1: narrative must match numbers --------------------------------------

# Forecast growth at/above this is "high growth" and triggers the
# narrative-vs-numbers interrogation.
HIGH_GROWTH_FLOOR = 0.12
# Margin trend (newest vs trailing mean) beyond which margins count as
# expanding / contracting rather than flat.
MARGIN_TREND_BAND = 0.02
# Minimum operating-margin history points to read a trend.
MIN_MARGIN_POINTS = 3
# Qualitative keys accepted as a supplied moat narrative.
MOAT_NARRATIVE_KEYS = ("moat", "moat_narrative", "narrative")

# --- LAW 2: growth requires reinvestment ---------------------------------------

# Number of recent ROIC observations averaged for sustainable growth.
ROIC_LOOKBACK = 5
# Gap between forecast growth and sustainable growth (g − ROIC×RR) that earns
# a flag vs a violation. 3pp of unexplained growth is aggressive; 8pp is
# inconsistent with the company's own economics.
GROWTH_GAP_FLAG = 0.03
GROWTH_GAP_VIOLATION = 0.08

# --- LAW 3: terminal growth ≤ risk-free ----------------------------------------

# Terminal growth within this distance below rf is "at the ceiling" — legal,
# but worth a flag because every basis point of headroom is gone.
TERMINAL_CEILING_BAND = 0.0025

# --- LAW 4: excess returns fade -------------------------------------------------

# Excess return (ROIC − WACC) at/above which competition pressure is presumed.
EXCESS_RETURN_FLOOR = 0.05
# Excess return + growth combination that escalates the flag to a violation.
EXCESS_RETURN_EXTREME = 0.10
EXTREME_GROWTH_FLOOR = 0.15
# Horizon (years of flat high growth) at/above which "no fade" is assumed.
NO_FADE_HORIZON = 8

# --- LAW 5: risk is not double-counted ------------------------------------------

# WACC this far above/below the baseline counts as a risk premium/discount
# embedded in the rate.
WACC_PREMIUM_BAND = 0.02
# Forecast growth this far below/above the historical revenue CAGR counts as
# a haircut/heroic cash-flow assumption.
GROWTH_HAIRCUT_BAND = 0.05
# Minimum revenue history points to compute a CAGR.
MIN_REVENUE_POINTS = 3


class DamodaranLawRegistry:
    """Evaluate the five Damodaran laws against an analysis.

    Usage::

        report = DamodaranLawRegistry().evaluate(
            security,
            intrinsic_result.assumptions,   # the inputs Stage 3 actually used
            implied=stage1_result.implied,  # optional reverse-DCF context
        )
        report.conviction_multiplier  # feed the verdict layer
    """

    def evaluate(
        self,
        security: Security,
        assumptions: Mapping[str, float],
        implied: ImpliedExpectations | None = None,
    ) -> LawReport:
        checks = [
            self._law1_narrative_matches_numbers(security, assumptions),
            self._law2_growth_requires_reinvestment(security, assumptions, implied),
            self._law3_terminal_growth_ceiling(security, assumptions),
            self._law4_excess_returns_fade(security, assumptions, implied),
            self._law5_risk_not_double_counted(security, assumptions),
        ]
        return LawReport(checks=checks)

    # -- LAW 1 -----------------------------------------------------------------

    def _law1_narrative_matches_numbers(
        self, security: Security, assumptions: Mapping[str, float]
    ) -> LawCheck:
        check = LawCheck(number=1, name="narrative_matches_numbers", status=LawStatus.NOT_EVALUATED)
        growth = assumptions.get("high_growth")
        history = security.fundamentals.operating_margin_history
        if growth is None or len(history) < MIN_MARGIN_POINTS:
            check.narrative = (
                "Cannot test narrative vs numbers: needs forecast growth and "
                f">= {MIN_MARGIN_POINTS} operating-margin observations."
            )
            return check

        trailing = mean(history[1 : MIN_MARGIN_POINTS + 1])
        assert trailing is not None  # len >= MIN_MARGIN_POINTS guarantees >= 2 trailing points
        margin_trend = history[0] - trailing
        check.components["forecast_growth"] = growth
        check.components["margin_trend"] = margin_trend

        if growth < HIGH_GROWTH_FLOOR:
            check.status = LawStatus.PASS
            check.narrative = (
                f"Forecast growth {growth:.1%} is below the high-growth bar "
                f"({HIGH_GROWTH_FLOOR:.0%}); no aggressive narrative to test."
            )
            return check

        qualitative = security.qualitative or {}
        if margin_trend >= MARGIN_TREND_BAND:
            # High growth + expanding margins = moat story; demand the story.
            if any(qualitative.get(k) for k in MOAT_NARRATIVE_KEYS):
                check.status = LawStatus.PASS
                check.narrative = (
                    f"High growth ({growth:.1%}) with expanding margins "
                    f"({margin_trend:+.1%}) — moat narrative supplied."
                )
                check.notes.append("Moat story accepted from qualitative input.")
            else:
                check.status = LawStatus.FLAG
                check.narrative = (
                    f"High growth ({growth:.1%}) WITH expanding margins "
                    f"({margin_trend:+.1%}) implies a competitive moat — no moat "
                    "narrative supplied to justify it."
                )
        elif margin_trend <= -MARGIN_TREND_BAND:
            check.status = LawStatus.PASS
            check.narrative = (
                f"High growth ({growth:.1%}) with contracting margins "
                f"({margin_trend:+.1%}) is a reinvestment story — internally consistent."
            )
        else:
            check.status = LawStatus.PASS
            check.narrative = (
                f"High growth ({growth:.1%}) with flat margins ({margin_trend:+.1%}); "
                "no narrative inconsistency detected."
            )
        return check

    # -- LAW 2 -----------------------------------------------------------------

    def _law2_growth_requires_reinvestment(
        self,
        security: Security,
        assumptions: Mapping[str, float],
        implied: ImpliedExpectations | None,
    ) -> LawCheck:
        check = LawCheck(
            number=2, name="growth_requires_reinvestment", status=LawStatus.NOT_EVALUATED
        )
        growth = assumptions.get("high_growth")
        roic = self._recent_roic(security)
        reinvestment = self._reinvestment_rate(security, implied, check.notes)

        if growth is None or roic is None or reinvestment is None:
            check.narrative = (
                "Cannot test g = ROIC × reinvestment: needs forecast growth, ROIC "
                "history, and a reinvestment rate (explicit or estimable)."
            )
            return check

        sustainable = roic * reinvestment
        gap = growth - sustainable
        check.components.update(
            {
                "forecast_growth": growth,
                "roic": roic,
                "reinvestment_rate": reinvestment,
                "sustainable_growth": sustainable,
                "growth_gap": gap,
            }
        )

        if gap > GROWTH_GAP_VIOLATION:
            check.status = LawStatus.VIOLATION
            check.narrative = (
                f"Forecast growth {growth:.1%} vs sustainable g = ROIC {roic:.1%} × "
                f"reinvestment {reinvestment:.0%} = {sustainable:.1%}: the "
                f"{gap:+.1%} gap cannot be funded by the business's own economics."
            )
        elif gap > GROWTH_GAP_FLAG:
            check.status = LawStatus.FLAG
            check.narrative = (
                f"Forecast growth {growth:.1%} exceeds sustainable g "
                f"({sustainable:.1%} = ROIC {roic:.1%} × reinvestment "
                f"{reinvestment:.0%}) by {gap:+.1%} — needs improving ROIC or "
                "rising reinvestment to be credible."
            )
        else:
            check.status = LawStatus.PASS
            check.narrative = (
                f"Forecast growth {growth:.1%} is supported by sustainable g "
                f"{sustainable:.1%} (ROIC {roic:.1%} × reinvestment {reinvestment:.0%})."
            )
        return check

    # -- LAW 3 -----------------------------------------------------------------

    def _law3_terminal_growth_ceiling(
        self, security: Security, assumptions: Mapping[str, float]
    ) -> LawCheck:
        check = LawCheck(number=3, name="terminal_growth_ceiling", status=LawStatus.NOT_EVALUATED)
        terminal = assumptions.get("terminal_growth")
        if terminal is None:
            check.narrative = "No terminal growth assumption supplied."
            return check

        qualitative = security.qualitative or {}
        rf = float(qualitative.get("risk_free_rate", DEFAULT_RISK_FREE))
        check.components["terminal_growth"] = terminal
        check.components["risk_free_rate"] = rf

        if terminal > rf:
            check.status = LawStatus.VIOLATION
            check.narrative = (
                f"Terminal growth {terminal:.2%} exceeds the risk-free rate "
                f"({rf:.2%}): the company would eventually outgrow the economy."
            )
        elif terminal > rf - TERMINAL_CEILING_BAND:
            check.status = LawStatus.FLAG
            check.narrative = (
                f"Terminal growth {terminal:.2%} sits at the risk-free ceiling "
                f"({rf:.2%}); no headroom for estimation error."
            )
        else:
            check.status = LawStatus.PASS
            check.narrative = (
                f"Terminal growth {terminal:.2%} is safely below the risk-free rate ({rf:.2%})."
            )
        return check

    # -- LAW 4 -----------------------------------------------------------------

    def _law4_excess_returns_fade(
        self,
        security: Security,
        assumptions: Mapping[str, float],
        implied: ImpliedExpectations | None,
    ) -> LawCheck:
        check = LawCheck(number=4, name="excess_returns_fade", status=LawStatus.NOT_EVALUATED)
        growth = assumptions.get("high_growth")
        wacc = assumptions.get("discount_rate", DEFAULT_WACC_BASELINE)
        horizon = int(assumptions.get("high_growth_years", 10))

        roic = self._recent_roic(security, lookback=1)
        if roic is None and implied is not None:
            roic = implied.implied_roic
            if roic is not None:
                check.notes.append("ROIC taken from reverse-DCF implied value (no history).")

        if growth is None or roic is None:
            check.narrative = "Cannot test excess-return fade: needs forecast growth and ROIC."
            return check

        excess = roic - wacc
        check.components.update(
            {"roic": roic, "wacc": wacc, "excess_return": excess, "horizon_years": float(horizon)}
        )

        if excess < EXCESS_RETURN_FLOOR or growth < HIGH_GROWTH_FLOOR:
            check.status = LawStatus.PASS
            check.narrative = (
                f"Excess return {excess:+.1%} / growth {growth:.1%} — no perpetual-moat "
                "assumption embedded; fade pressure is immaterial."
            )
            return check

        # The two-stage model holds growth flat across the horizon; with high
        # excess returns that is an implicit no-fade assumption.
        fade_path = excess_return_fade_path(roic, wacc)
        check.components["faded_terminal_roic"] = fade_path[-1]
        reinvestment = self._reinvestment_rate(security, implied, check.notes)
        if reinvestment is not None:
            faded_g = fade_adjusted_growth(roic, wacc, reinvestment)
            if faded_g is not None:
                check.components["fade_adjusted_growth"] = faded_g

        if (
            excess >= EXCESS_RETURN_EXTREME
            and growth >= EXTREME_GROWTH_FLOOR
            and horizon >= NO_FADE_HORIZON
        ):
            check.status = LawStatus.VIOLATION
            check.narrative = (
                f"ROIC {roic:.1%} is {excess:+.1%} above WACC and the model holds "
                f"{growth:.1%} growth flat for {horizon} years — a perpetual moat "
                f"with no fade. Law 4 expects ROIC to glide toward "
                f"{fade_path[-1]:.1%} within {DEFAULT_FADE_YEARS} years."
            )
        elif horizon >= NO_FADE_HORIZON:
            check.status = LawStatus.FLAG
            check.narrative = (
                f"ROIC {roic:.1%} ({excess:+.1%} excess) with {growth:.1%} growth held "
                f"flat for {horizon} years assumes no competitive fade; expected "
                f"glide path ends near {fade_path[-1]:.1%}."
            )
        else:
            check.status = LawStatus.PASS
            check.narrative = (
                f"High excess return ({excess:+.1%}) but the explicit horizon "
                f"({horizon}y) is short enough that fade risk is limited."
            )
        return check

    # -- LAW 5 -----------------------------------------------------------------

    def _law5_risk_not_double_counted(
        self, security: Security, assumptions: Mapping[str, float]
    ) -> LawCheck:
        check = LawCheck(number=5, name="risk_not_double_counted", status=LawStatus.NOT_EVALUATED)
        growth = assumptions.get("high_growth")
        wacc = assumptions.get("discount_rate")
        hist_cagr = self._revenue_cagr(security)

        if growth is None or wacc is None or hist_cagr is None:
            check.narrative = (
                "Cannot test risk double-counting: needs forecast growth, discount "
                f"rate, and >= {MIN_REVENUE_POINTS} revenue observations."
            )
            return check

        rate_premium = wacc - DEFAULT_WACC_BASELINE
        growth_haircut = hist_cagr - growth
        check.components.update(
            {
                "wacc": wacc,
                "rate_premium_vs_baseline": rate_premium,
                "historical_revenue_cagr": hist_cagr,
                "forecast_growth": growth,
                "growth_haircut": growth_haircut,
            }
        )

        if rate_premium > WACC_PREMIUM_BAND and growth_haircut > GROWTH_HAIRCUT_BAND:
            check.status = LawStatus.FLAG
            check.narrative = (
                f"Risk may be double-counted: WACC carries a {rate_premium:+.1%} premium "
                f"over baseline AND forecast growth ({growth:.1%}) is haircut "
                f"{growth_haircut:.1%} below the historical CAGR ({hist_cagr:.1%}). "
                "Risk belongs in cash flows OR the discount rate, not both."
            )
        elif rate_premium < -WACC_PREMIUM_BAND and -growth_haircut > GROWTH_HAIRCUT_BAND:
            check.status = LawStatus.FLAG
            check.narrative = (
                f"Optimism may be double-counted: WACC sits {rate_premium:+.1%} below "
                f"baseline AND forecast growth ({growth:.1%}) exceeds the historical "
                f"CAGR ({hist_cagr:.1%}) by {-growth_haircut:.1%}."
            )
        else:
            check.status = LawStatus.PASS
            check.narrative = (
                "No risk double-counting detected between the discount rate and "
                "the cash-flow assumptions."
            )
        return check

    # -- shared input readers ----------------------------------------------------

    @staticmethod
    def _recent_roic(security: Security, lookback: int = ROIC_LOOKBACK) -> float | None:
        history = security.fundamentals.roic_history
        if not history:
            return None
        return mean(history[:lookback])

    @staticmethod
    def _reinvestment_rate(
        security: Security,
        implied: ImpliedExpectations | None,
        notes: list[str],
    ) -> float | None:
        """Reinvestment rate: explicit input first, then an accounting estimate.

        The estimate treats the share of earnings *not* converted to FCF as
        reinvested (1 − FCF/NI) — a coarse proxy for (capex − D&A + ΔWC)/NOPAT
        when the full reconciliation isn't available. The reverse-DCF implied
        rate is the last resort: it describes what the *market* assumes, not
        what the business does.
        """
        qualitative = security.qualitative or {}
        explicit = qualitative.get("reinvestment_rate")
        if explicit is not None:
            return clamp(float(explicit), 0.0, 1.0)

        f = security.fundamentals
        if f.fcf_ttm is not None and f.net_income_ttm is not None and f.net_income_ttm > 0:
            estimate = clamp(1.0 - f.fcf_ttm / f.net_income_ttm, 0.0, 1.0)
            notes.append(
                f"Reinvestment rate estimated from 1 - FCF/NI = {estimate:.0%} (no explicit input)."
            )
            return estimate

        if implied is not None and implied.implied_reinvestment_rate is not None:
            notes.append(
                "Reinvestment rate taken from reverse-DCF implied value — this is "
                "the market's assumption, not the business's track record."
            )
            return clamp(float(implied.implied_reinvestment_rate), 0.0, 1.0)
        return None

    @staticmethod
    def _revenue_cagr(security: Security) -> float | None:
        """Historical revenue CAGR from most-recent-first history."""
        history = security.fundamentals.revenue_history
        if len(history) < MIN_REVENUE_POINTS:
            return None
        newest, oldest = history[0], history[-1]
        if oldest <= 0 or newest <= 0:
            return None
        years = len(history) - 1
        return float((newest / oldest) ** (1.0 / years)) - 1.0
