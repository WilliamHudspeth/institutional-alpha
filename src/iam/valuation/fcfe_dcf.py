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

import logging
from dataclasses import dataclass
from typing import TypedDict

from iam.data.ground_truth import GroundTruthProvider
from iam.data.security import Security
from iam.valuation.beta import get_custom_beta_for_intrinsic
from iam.valuation.equity_returns import company_roe
from iam.valuation.reverse_dcf import (
    _present_value_path,
    _present_value_two_stage,
    as_rate,
    cap_terminal_growth,
)
from iam.valuation.types import Method, ValuationResult

logger = logging.getLogger(__name__)


class _Scenario(TypedDict):
    """One row of the Bear/Base/Bull scenario matrix."""

    name: str
    prob: float
    g: float
    wacc: float
    tv_g: float


@dataclass
class FCFEAssumptions:
    """The explicit forecast inputs for the base case.

    These should come from outside the model — analyst consensus,
    management guidance, your own bottom-up. The model's job is to compute
    a fair value *given* these inputs, not to invent them.
    """

    high_growth: float  # FCFE CAGR during forecast period
    terminal_growth: float = 0.025
    high_growth_years: int = 10
    discount_rate: float = 0.09
    roe: float = 0.15  # Return on Equity for reinvestment constraint


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

    def __init__(self, default_assumptions: FCFEAssumptions | None = None):
        self.defaults = default_assumptions or FCFEAssumptions(high_growth=0.08)

    def compute(
        self,
        security: Security,
        assumptions: FCFEAssumptions | None = None,
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
            notes.append("Using model defaults — supply assumptions for a tailored estimate.")

        # Cost of Equity Hierarchy ("what is it worth?"):
        # 1. Caller-supplied risk_free_rate / equity_risk_premium (explicit custom CAPM;
        #    a missing half is filled from the macro Rf / revenue-weighted ERP).
        # 2. Bottom-up Ke: Rf + industry unlevered beta relevered at current market D/E
        #    x revenue-weighted ERP (GroundTruthProvider).
        # 3. Forecast discount rate from qualitative / model default, stated in the notes.
        q = security.qualitative
        rfr = as_rate(q.get("risk_free_rate"))
        erp = as_rate(q.get("equity_risk_premium"))
        rf_used: float | None = None

        if rfr is not None or erp is not None:
            try:
                if rfr is None or erp is None:
                    from iam.data.damodaran import DamodaranProvider
                    from iam.valuation.country_risk import company_erp

                    if rfr is None:
                        rfr = DamodaranProvider.get_risk_free_rate()
                    if erp is None:
                        erp = company_erp(security)[0]
                beta = get_custom_beta_for_intrinsic(security)
                base_a.discount_rate = float(rfr) + beta * float(erp)
                rf_used = float(rfr)
                notes.append(
                    f"CAPM discount rate: {rfr:.3f} + {beta:.4f} × {erp:.3f} = {base_a.discount_rate:.4f} "
                    f"(custom CAPM, Stage 3)"
                )
            except Exception:
                pass
        else:
            gt = GroundTruthProvider()
            try:
                profile, reason = gt.get_equity_risk_profile_with_reason(security)
            except Exception as e:
                logger.debug(f"GroundTruthProvider failed: {e}; using forecast discount rate")
                profile, reason = None, f"bottom-up cost of equity failed: {e}"
            if profile is not None:
                base_a.discount_rate = profile.cost_of_equity
                rf_used = profile.risk_free_rate
                notes.append(
                    f"bottom-up Ke (industry beta relevered, revenue-weighted ERP): "
                    f"{profile.risk_free_rate:.2%} + {profile.levered_beta:.2f} × "
                    f"{profile.erp:.2%} = {profile.cost_of_equity:.2%} "
                    f"(unlevered beta {profile.industry_unlevered_beta:.2f}, "
                    f"D/E {profile.debt_to_equity:.2f}, tax {profile.tax_rate:.0%}; "
                    f"rf: {profile.rf_source}; ERP: {profile.erp_source})"
                )
                notes.extend(f"default used: {d}" for d in profile.defaults_used)
            else:
                notes.append(
                    f"{reason}; using forecast/default discount rate "
                    f"{base_a.discount_rate:.2%} (not a computed cost of equity)"
                )

        # Terminal growth never exceeds the risk-free rate used by this stage.
        terminal_growth, cap_note = cap_terminal_growth(base_a.terminal_growth, rf_used)
        if cap_note:
            notes.append(cap_note)

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

        if base_a.discount_rate <= terminal_growth:
            return ValuationResult(
                method=Method.INTRINSIC,
                confidence=0.0,
                notes=["Discount rate must exceed terminal growth."],
                verdict_text="Bad assumptions: r <= g_terminal.",
            )

        raw_path = q.get("forecast_growth_path") if assumptions is None else None
        use_path = isinstance(raw_path, list | tuple) and len(raw_path) == base_a.high_growth_years
        base_path: list[float] | None = (
            [float(x) for x in raw_path] if use_path and raw_path is not None else None
        )
        if base_path is not None:
            notes.append("growth path from the growth engine (years 1-5 flat, fade over 6-10)")

        # Reinvestment is priced at the company's own normalised ROE, fading to the market ROE
        # over years 6-10 and in the terminal value (iam.valuation.equity_returns). Explicit
        # assumptions passed by the caller keep their single ROE.
        roe_terminal: float | None = None
        roe_path: list[float] | None = None
        if assumptions is None:
            equity_return = company_roe(security, default=self.defaults.roe)
            base_a.roe = equity_return.roe
            roe_terminal = equity_return.terminal(self.defaults.roe)
            roe_path = equity_return.path(years=base_a.high_growth_years, terminal=roe_terminal)
            notes.append(
                f"reinvestment priced at ROE {base_a.roe:.1%} ({equity_return.source}), "
                f"fading to {roe_terminal:.1%} by year {base_a.high_growth_years}"
            )

        def _bear_g(g: float) -> float:
            return g * 0.60 if g >= 0 else g * 1.40

        def _bull_g(g: float) -> float:
            return g * 1.30 if g >= 0 else g * 0.70

        # ====================================================================
        # Probabilistic Scenario Matrix
        # ====================================================================
        # (Scenario terminal growth = capped base x factor, re-capped at Rf.)
        # Bear (20%):  -40% growth (or +40% decline if < 0), +150bps WACC, -20% Terminal Growth
        # Base (60%):  Anchor assumptions
        # Bull (20%):  +30% growth (or -30% decline if < 0), -100bps WACC, +20% Terminal Growth
        scenarios: list[_Scenario] = [
            {
                "name": "Bear Case",
                "prob": 0.20,
                "g": _bear_g(base_a.high_growth),
                "wacc": base_a.discount_rate + 0.015,
                "tv_g": cap_terminal_growth(terminal_growth * 0.80, rf_used)[0],
            },
            {
                "name": "Base Case",
                "prob": 0.60,
                "g": base_a.high_growth,
                "wacc": base_a.discount_rate,
                "tv_g": terminal_growth,
            },
            {
                "name": "Bull Case",
                "prob": 0.20,
                "g": _bull_g(base_a.high_growth),
                "wacc": base_a.discount_rate - 0.010,
                "tv_g": cap_terminal_growth(terminal_growth * 1.20, rf_used)[0],
            },
        ]

        scenario_paths: dict[str, list[float]] = {}
        if base_path is not None:
            scenario_paths = {
                "Bear Case": [_bear_g(g) for g in base_path],
                "Base Case": list(base_path),
                "Bull Case": [_bull_g(g) for g in base_path],
            }

        matrix_results: dict[str, dict[str, float]] = {}

        # Run the DCF math for each scenario
        for s in scenarios:
            if s["wacc"] <= s["tv_g"]:
                notes.append(
                    f"Scenario '{s['name']}' skipped: discount rate {s['wacc']:.2%} "
                    f"<= terminal growth {s['tv_g']:.2%}."
                )
                continue
            try:
                if base_path is not None:
                    target = _present_value_path(
                        base_ni=ni_per_share,
                        growth_path=scenario_paths[s["name"]],
                        g_terminal=s["tv_g"],
                        r=s["wacc"],
                        roe=roe_path if roe_path is not None else base_a.roe,
                        roe_terminal=roe_terminal,
                    )
                else:
                    target = _present_value_two_stage(
                        base_ni=ni_per_share,
                        g_high=s["g"],
                        g_terminal=s["tv_g"],
                        n=base_a.high_growth_years,
                        r=s["wacc"],
                        roe=base_a.roe,
                        roe_terminal=roe_terminal,
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
            except Exception as e:
                notes.append(f"Scenario '{s['name']}' calculation failed: {e}")

        total_prob = sum(r["prob"] for r in matrix_results.values())
        if not matrix_results or total_prob <= 0:
            return ValuationResult(
                method=Method.INTRINSIC,
                confidence=0.0,
                notes=notes + ["All scenarios failed; PWEV invalid."],
                verdict_text="Intrinsic DCF failed across all scenarios.",
            )

        for r in matrix_results.values():
            r["prob"] = r["prob"] / total_prob

        pwev_target = sum(r["target"] * r["prob"] for r in matrix_results.values())
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
        ]
        for s_name, s_res in matrix_results.items():
            short_name = s_name.replace(" Case", "")
            verdict_lines.append(
                f"    • {short_name} ({s_res['prob'] * 100:.0f}%): ${s_res['target']:.2f} "
                f"| Growth: {s_res['g'] * 100:.1f}% "
                f"| WACC: {s_res['wacc'] * 100:.2f}%"
            )

        components: dict[str, object] = {
            "pwev_target": pwev_target,
            "scenarios": matrix_results,
            "base_ni_per_share": ni_per_share,
        }
        if base_path is not None:
            components["growth_path"] = base_path

        return ValuationResult(
            method=Method.INTRINSIC,
            fair_value_per_share=pwev_target,
            fair_value_to_price=pwev_upside,
            confidence=confidence,
            components=components,
            assumptions={
                "high_growth": base_a.high_growth,
                "terminal_growth": terminal_growth,
                "high_growth_years": float(base_a.high_growth_years),
                "discount_rate": base_a.discount_rate,
                "roe": base_a.roe,
                "roe_terminal": roe_terminal if roe_terminal is not None else base_a.roe,
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
        high_growth = q.get("forecast_growth")
        terminal_growth = q.get("forecast_terminal_growth")
        high_growth_years = q.get("forecast_high_growth_years")
        discount_rate = q.get("forecast_discount_rate")
        roe = q.get("forecast_roe")
        return FCFEAssumptions(
            high_growth=float(
                high_growth if high_growth is not None else self.defaults.high_growth
            ),
            terminal_growth=float(
                terminal_growth if terminal_growth is not None else self.defaults.terminal_growth
            ),
            high_growth_years=int(
                high_growth_years
                if high_growth_years is not None
                else self.defaults.high_growth_years
            ),
            discount_rate=float(
                discount_rate if discount_rate is not None else self.defaults.discount_rate
            ),
            roe=float(roe if roe is not None else self.defaults.roe),
        )
