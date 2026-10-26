"""Relative value factor — vs. sector peers and own history."""

from __future__ import annotations

import statistics

from iam.data.security import Security
from iam.factors.base import Factor, FactorContribution


class RelativeValueFactor(Factor):
    name = "relative_value"

    def compute(self, security: Security) -> FactorContribution:
        components: dict[str, float] = {}
        notes: list[str] = []
        confidence = 1.0
        m = security.market

        # EV/EBITDA vs sector median
        # A negative multiple (losses) is not "cheaper than peers": skip it.
        if (
            m.ev_ebitda is not None
            and m.ev_ebitda > 0
            and m.sector_ev_ebitda_median is not None
            and m.sector_ev_ebitda_median > 0
        ):
            ratio = m.ev_ebitda / m.sector_ev_ebitda_median
            # ratio < 1 means cheaper than peers
            components["ev_ebitda_vs_sector"] = self.clamp(-(ratio - 1.0))
        else:
            confidence *= 0.8
            if m.ev_ebitda is not None and m.ev_ebitda <= 0:
                notes.append("EV/EBITDA not positive (negative EBITDA): not compared to peers.")

        # P/E vs own 10y range (percentile), positive P/Es only: a loss-year P/E would sit
        # below every positive one and score as the cheapest ever.
        positive_pes = [x for x in m.pe_history if x > 0]
        if m.pe_ttm is not None and m.pe_ttm > 0 and len(positive_pes) >= 24:
            sorted_pes = sorted(positive_pes)
            below = sum(1 for x in sorted_pes if x < m.pe_ttm)
            percentile = below / len(sorted_pes)
            # 0th pct = cheap (+1), 100th = expensive (-1)
            components["pe_own_percentile"] = self.clamp(1 - 2 * percentile)
        else:
            confidence *= 0.85
            if m.pe_ttm is not None and m.pe_ttm <= 0:
                notes.append("P/E not positive (losses): own-history percentile skipped.")

        # FCF yield vs peers
        if m.fcf_yield is not None and m.peer_fcf_yields:
            peer_median = statistics.median(m.peer_fcf_yields)
            spread = m.fcf_yield - peer_median
            components["fcf_yield_vs_peers"] = self.clamp(spread * 25)  # 4% spread = full +1
        else:
            confidence *= 0.85

        # EV/Sales vs peers
        if (
            m.ev_sales is not None
            and m.peer_ev_sales_median is not None
            and m.peer_ev_sales_median > 0
        ):
            ratio = m.ev_sales / m.peer_ev_sales_median
            components["ev_sales_vs_peers"] = self.clamp(-(ratio - 1.0))
        else:
            confidence *= 0.95

        value = self.weighted_average(
            {
                "evebitda": (components.get("ev_ebitda_vs_sector"), 0.30),
                "pe_pct": (components.get("pe_own_percentile"), 0.30),
                "fcfy": (components.get("fcf_yield_vs_peers"), 0.25),
                "evs": (components.get("ev_sales_vs_peers"), 0.15),
            }
        )

        return FactorContribution(
            name=self.name,
            value=self.clamp(value),
            confidence=confidence,
            components=components,
            notes=notes,
        )
