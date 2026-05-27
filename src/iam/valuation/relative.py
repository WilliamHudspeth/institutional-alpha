from __future__ import annotations

import statistics
from typing import Optional

from iam.data.security import Security
from iam.valuation.types import Method, ValuationResult
from iam.valuation.damodaran_defaults import DamodaranUniverse


class RelativeValuation:
    """Stage 2: Relative Valuation.
    
    Combines Damodaran Sector Medians (if a universe is provided) with
    historical and peer-relative market data.
    """
    
    def __init__(self, universe: Optional[DamodaranUniverse] = None):
        self.universe = universe

    def compute(self, security: Security) -> ValuationResult:
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
