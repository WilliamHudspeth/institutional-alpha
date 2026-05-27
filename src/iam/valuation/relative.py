from __future__ import annotations

import statistics
from typing import TYPE_CHECKING, Optional

from iam.data.security import Security
from iam.valuation.types import Method, ValuationResult
from iam.valuation.damodaran_defaults import DamodaranUniverse

if TYPE_CHECKING:
    from iam.valuation.multiples_regression import RegressionInputs


class RelativeValuation:
    """Stage 2: Relative Valuation.

    Combines up to four independent signals:
      1. Damodaran sector median multiples (EV/EBITDA, P/E)
      2. Own P/E history percentile
      3. FCF yield vs peer set
      4. Damodaran Jan 2026 regression-predicted multiples (optional)

    Signal 4 anchors the valuation to what the multiples *should* be given
    the company's own fundamentals, independent of what peers happen to trade
    at today.  Pass ``regression_inputs`` to activate it.
    """

    def __init__(self, universe: Optional[DamodaranUniverse] = None):
        self.universe = universe

    def compute(
        self,
        security: Security,
        regression_inputs: Optional[RegressionInputs] = None,
    ) -> ValuationResult:
        m = security.market
        f = security.fundamentals
        notes: list[str] = []
        confidence = 1.0
        components: dict[str, float] = {}

        if m.price is None or m.price <= 0:
            return ValuationResult(
                method=Method.RELATIVE, confidence=0.0,
                notes=["Relative valuation requires a positive current price."],
                verdict_text="Insufficient data for relative valuation.",
            )

        implied_prices = []

        # 1. Damodaran Sector Multiples (if available)
        damodaran_used = False
        if self.universe and security.sector and security.sector in self.universe.sector_multiples:
            multiples = self.universe.sector_multiples[security.sector]
            
            # Implied value based on EV/EBITDA
            if f.ebitda_ttm and f.ebitda_ttm > 0 and 'ev_ebitda' in multiples:
                target_ev = f.ebitda_ttm * multiples['ev_ebitda']
                target_eq = target_ev - (f.total_debt or 0) + (f.cash_and_equivalents or 0)
                if f.shares_outstanding and f.shares_outstanding > 0:
                    impl_price = target_eq / f.shares_outstanding
                    implied_prices.append(impl_price)
                    components["implied_price_ev_ebitda"] = impl_price
                    damodaran_used = True

            # Implied value based on P/E
            if f.net_income_ttm and f.net_income_ttm > 0 and 'pe' in multiples:
                target_mc = f.net_income_ttm * multiples['pe']
                if f.shares_outstanding and f.shares_outstanding > 0:
                    impl_price = target_mc / f.shares_outstanding
                    implied_prices.append(impl_price)
                    components["implied_price_pe"] = impl_price
                    damodaran_used = True
        
        # 1b. Fallback to basic MarketData sector multiples
        if not damodaran_used:
            if m.ev_ebitda and m.sector_ev_ebitda_median and m.ev_ebitda > 0:
                impl_price = m.price * (m.sector_ev_ebitda_median / m.ev_ebitda)
                implied_prices.append(impl_price)
                components["implied_price_ev_ebitda"] = impl_price
            else:
                notes.append("No sector multiples available.")
                confidence *= 0.85

        # 2. P/E vs Own History
        if m.pe_ttm and m.pe_history and len(m.pe_history) >= 24:
            median_pe = statistics.median(m.pe_history)
            if m.pe_ttm > 0 and median_pe > 0:
                impl_price = m.price * (median_pe / m.pe_ttm)
                implied_prices.append(impl_price)
                components["implied_price_pe_history"] = impl_price
        else:
            notes.append("Insufficient P/E history (need >=24 datapoints).")
            confidence *= 0.85

        # 3. FCF Yield vs Peer Set
        if m.fcf_yield and m.peer_fcf_yields:
            peer_median = statistics.median(m.peer_fcf_yields)
            if peer_median > 0 and m.fcf_yield > 0:
                impl_price = m.price * (m.fcf_yield / peer_median)
                implied_prices.append(impl_price)
                components["implied_price_fcf_yield"] = impl_price
        else:
            notes.append("FCF yield or peer set missing.")
            confidence *= 0.85

        # 4. Damodaran regression-predicted multiples (optional)
        if regression_inputs is not None:
            from iam.valuation.multiples_regression import predict_all
            predicted = predict_all(regression_inputs.region, regression_inputs.to_dict())
            reg_signals = 0

            if m.pe_ttm and m.pe_ttm > 0 and predicted.get("PE") and predicted["PE"] > 0:
                impl_price = m.price * (predicted["PE"] / m.pe_ttm)
                implied_prices.append(impl_price)
                components["implied_price_regression_pe"] = impl_price
                reg_signals += 1

            if m.ev_ebitda and m.ev_ebitda > 0 and predicted.get("EV_EBITDA") and predicted["EV_EBITDA"] > 0:
                impl_price = m.price * (predicted["EV_EBITDA"] / m.ev_ebitda)
                implied_prices.append(impl_price)
                components["implied_price_regression_ev_ebitda"] = impl_price
                reg_signals += 1

            if reg_signals:
                notes.append(
                    f"Regression anchor ({regression_inputs.region}): "
                    f"{reg_signals} fundamentals-predicted multiple(s)."
                )
            else:
                notes.append("Regression inputs provided but no matching market multiples available.")

        if not implied_prices:
            return ValuationResult(
                method=Method.RELATIVE, confidence=0.0,
                notes=notes + ["No relative signals available."],
                verdict_text="Insufficient data for relative valuation.",
            )

        blended_fair_value = sum(implied_prices) / len(implied_prices)
        composite_ratio = (blended_fair_value / m.price) - 1

        # Clamp to a sensible range
        composite_ratio = max(-0.8, min(2.0, composite_ratio))
        blended_fair_value = m.price * (1 + composite_ratio)

        pct = composite_ratio * 100
        signals = f"{len(implied_prices)} signal{'s' if len(implied_prices) != 1 else ''}"
        
        if composite_ratio > 0.20:
            verdict = f"Relative valuation suggests ~{pct:+.0f}% upside vs peers/history ({signals})."
        elif composite_ratio > 0.05:
            verdict = f"Modestly cheap on relative basis ({pct:+.0f}%, {signals})."
        elif composite_ratio > -0.05:
            verdict = f"Roughly fair on relative basis ({pct:+.0f}%, {signals})."
        elif composite_ratio > -0.20:
            verdict = f"Modestly expensive on relative basis ({pct:+.0f}%, {signals})."
        else:
            verdict = f"Expensive vs peers/history ({pct:+.0f}%, {signals})."

        return ValuationResult(
            method=Method.RELATIVE,
            fair_value_per_share=blended_fair_value,
            fair_value_to_price=composite_ratio,
            confidence=confidence,
            components=components,
            notes=notes,
            verdict_text=verdict,
        )
