"""Stage 3a: FCFE DCF (Probabilistic Valuation Matrix).

Where reverse DCF takes price as given and solves for growth, this builds
fair value bottom-up from forecast growth, margin, and reinvestment
assumptions. Instead of a fragile single-point estimate, this engine natively
computes a Probability-Weighted Expected Value (PWEV) across institutional
scenarios (Bear 20%, Base 60%, Bull 20%) based on the user's anchor assumptions.

The scenario matrix becomes the foundation for Bayesian updating when
real-world evidence (earnings beats, margin shifts) arrives.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import logging

from iam.data.security import Security
from iam.data.ground_truth import GroundTruthProvider
from iam.valuation.beta import get_custom_beta_for_intrinsic
from iam.valuation.reverse_dcf import _present_value_two_stage
from iam.valuation.types import Method, ValuationResult

logger = logging.getLogger(__name__)


@dataclass
class FCFEAssumptions:
    """The explicit forecast inputs for the base case.

    These should come from outside the model — analyst consensus,
    management guidance, your own bottom-up. The model's job is to compute
    a fair value *given* these inputs, not to invent them.
    """
    high_growth: float          # FCFE CAGR during forecast period
    terminal_growth: float = 0.025
    high_growth_years: int = 10
    discount_rate: float = 0.09
    roe: float = 0.15           # Return on Equity for reinvestment constraint


class FCFEDCF:
    """Stage 3a — Probability-Weighted intrinsic value via FCFE DCF.

    If the security has analyst-provided or user-provided forecast assumptions
    on ``security.qualitative`` (keys: ``forecast_growth``,
    ``forecast_terminal_growth``, ``forecast_discount_rate``), those are used
    as the BASE case. The engine then generates Bear (20%), Bull (20%) scenarios
    and blends them probabilistically.

    Output is Probability-Weighted Expected Value (PWEV), not a fragile
    single-point estimate. The scenario matrix enables Bayesian updating.
    """

    def __init__(self, default_assumptions: Optional[FCFEAssumptions] = None):
        self.defaults = default_assumptions or FCFEAssumptions(high_growth=0.08)

    def compute(
        self,
        security: Security,
        assumptions: Optional[FCFEAssumptions] = None,
    ) -> ValuationResult:
        """Compute intrinsic value via probabilistic scenario analysis."""
        m = security.market
        f = security.fundamentals
        notes: list[str] = []
        confidence = 1.0

        if m.price is None or f.fcf_ttm is None or f.shares_outstanding is None:
            return ValuationResult(
                method=Method.INTRINSIC,
                confidence=0.0,
                notes=["FCFE DCF requires price, FCF TTM, and shares outstanding."],
                verdict_text="Insufficient data for intrinsic DCF.",
            )

        # Resolve assumptions: explicit > qualitative dict > defaults.
        base_a = assumptions or self._resolve_assumptions(security)
        if assumptions is None and not self._has_explicit_assumptions(security):
            confidence *= 0.7
            notes.append(
                "Using model defaults — supply assumptions for a tailored estimate."
            )

        # Cost of Equity Hierarchy:
        # 1. Explicit risk_free_rate + equity_risk_premium (custom CAPM)
        # 2. Institutional Damodaran baselines (GroundTruthProvider)
        # 3. Forecast discount rate from qualitative
        q = security.qualitative
        rfr = q.get("risk_free_rate")
        erp = q.get("equity_risk_premium")

        if rfr is not None and erp is not None:
            # Custom CAPM with explicit rates
            try:
                beta = get_custom_beta_for_intrinsic(security)
                base_a.discount_rate = float(rfr) + beta * float(erp)
                notes.append(
                    f"CAPM discount rate: {rfr:.3f} + {beta:.4f} × {erp:.3f} = {base_a.discount_rate:.4f} "
                    f"(custom CAPM, Stage 3)"
                )
            except Exception:
                pass
        else:
            # Institutional baseline: Damodaran unlevered beta + Implied ERP
            try:
                profile = GroundTruthProvider.get_equity_risk_profile(security)
                base_a.discount_rate = profile.cost_of_equity
                notes.append(
                    f"Cost of Equity: {profile.risk_free_rate*100:.2f}% + {profile.industry_unlevered_beta:.2f} "
                    f"(relevered) × {profile.erp*100:.2f}% = {profile.cost_of_equity*100:.2f}% "
                    f"(Damodaran institutional baseline)"
                )
            except Exception as e:
                logger.debug(f"GroundTruthProvider failed: {e}; using forecast discount rate")
                pass

        # Base cash flow: use Net Income if available, else FCF TTM
        ni = f.net_income_ttm if f.net_income_ttm and f.net_income_ttm > 0 else f.fcf_ttm
        if ni is None or ni <= 0:
            return ValuationResult(
                method=Method.INTRINSIC,
                confidence=0.3,
                notes=["Base Net Income/FCFE is non-positive; FCFE DCF unreliable."],
                verdict_text="Base cash flow non-positive; method skipped.",
            )

        ni_per_share = ni / f.shares_outstanding

        if base_a.discount_rate <= base_a.terminal_growth:
            return ValuationResult(
                method=Method.INTRINSIC,
                confidence=0.0,
                notes=["Discount rate must exceed terminal growth."],
                verdict_text="Bad assumptions: r <= g_terminal.",
            )

        # ====================================================================
        # Probabilistic Scenario Matrix
        # ====================================================================
        # Bear (20%):  -40% growth, +150bps WACC, -20% Terminal Growth
        # Base (60%):  Anchor assumptions
        # Bull (20%):  +30% growth, -100bps WACC, +20% Terminal Growth
        scenarios = [
            {
                "name": "Bear Case",
                "prob": 0.20,
                "g": base_a.high_growth * 0.60,
                "wacc": base_a.discount_rate + 0.015,
                "tv_g": base_a.terminal_growth * 0.80,
            },
            {
                "name": "Base Case",
                "prob": 0.60,
                "g": base_a.high_growth,
                "wacc": base_a.discount_rate,
                "tv_g": base_a.terminal_growth,
            },
            {
                "name": "Bull Case",
                "prob": 0.20,
                "g": base_a.high_growth * 1.30,
                "wacc": base_a.discount_rate - 0.010,
                "tv_g": base_a.terminal_growth * 1.20,
            },
        ]

        pwev_target = 0.0
        matrix_results = {}

        # Run the DCF math for each scenario
        for s in scenarios:
            try:
                target = _present_value_two_stage(
                    base_ni=ni_per_share,
                    g_high=s["g"],
                    g_terminal=s["tv_g"],
                    n=base_a.high_growth_years,
                    r=s["wacc"],
                    roe=base_a.roe,
                )
                upside = (target / m.price) - 1 if m.price > 0 else 0

                matrix_results[s["name"]] = {
                    "prob": s["prob"],
                    "target": target,
                    "upside": upside,
                    "g": s["g"],
                    "wacc": s["wacc"],
                    "tv_g": s["tv_g"],
                }

                # Accumulate Probability-Weighted Expected Value
                pwev_target += target * s["prob"]
            except Exception as e:
                notes.append(f"Scenario '{s['name']}' calculation failed: {e}")

        if pwev_target <= 0:
            return ValuationResult(
                method=Method.INTRINSIC,
                confidence=0.0,
                notes=notes + ["All scenarios failed; PWEV invalid."],
                verdict_text="Intrinsic DCF failed across all scenarios.",
            )

        # ====================================================================
        # Final PWEV Synthesis
        # ====================================================================
        pwev_upside = (pwev_target / m.price) - 1 if m.price > 0 else 0

        # Format the scenario matrix for output
        verdict_lines = [
            f"Probability-Weighted Fair Value (PWEV): ${pwev_target:.2f} ({pwev_upside * 100:+.1f}%)",
            "  Scenario Matrix:",
            f"    • Bear (20%): ${matrix_results['Bear Case']['target']:.2f} "
            f"| Growth: {matrix_results['Bear Case']['g'] * 100:.1f}% "
            f"| WACC: {matrix_results['Bear Case']['wacc'] * 100:.2f}%",
            f"    • Base (60%): ${matrix_results['Base Case']['target']:.2f} "
            f"| Growth: {matrix_results['Base Case']['g'] * 100:.1f}% "
            f"| WACC: {matrix_results['Base Case']['wacc'] * 100:.2f}%",
            f"    • Bull (20%): ${matrix_results['Bull Case']['target']:.2f} "
            f"| Growth: {matrix_results['Bull Case']['g'] * 100:.1f}% "
            f"| WACC: {matrix_results['Bull Case']['wacc'] * 100:.2f}%",
        ]

        return ValuationResult(
            method=Method.INTRINSIC,
            fair_value_per_share=pwev_target,
            fair_value_to_price=pwev_upside,
            confidence=confidence,
            components={
                "pwev_target": pwev_target,
                "scenarios": matrix_results,
                "base_ni_per_share": ni_per_share,
            },
            assumptions={
                "high_growth": base_a.high_growth,
                "terminal_growth": base_a.terminal_growth,
                "high_growth_years": float(base_a.high_growth_years),
                "discount_rate": base_a.discount_rate,
                "roe": base_a.roe,
            },
            notes=notes,
            verdict_text="\n".join(verdict_lines),
        )

    @staticmethod
    def _has_explicit_assumptions(security: Security) -> bool:
        """Check if user provided explicit forecast assumptions."""
        return "forecast_growth" in security.qualitative

    def _resolve_assumptions(self, security: Security) -> FCFEAssumptions:
        """Resolve assumptions from security qualitative dict or defaults."""
        q = security.qualitative
        return FCFEAssumptions(
            high_growth=float(q.get("forecast_growth", self.defaults.high_growth)),
            terminal_growth=float(
                q.get("forecast_terminal_growth", self.defaults.terminal_growth)
            ),
            high_growth_years=int(
                q.get("forecast_high_growth_years", self.defaults.high_growth_years)
            ),
            discount_rate=float(
                q.get("forecast_discount_rate", self.defaults.discount_rate)
            ),
            roe=float(q.get("forecast_roe", self.defaults.roe)),
        )
