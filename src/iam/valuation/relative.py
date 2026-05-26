"""Stage 2: Relative valuation.

Acts as the confirm/deny on Stage 1. The reverse DCF told us what the
market is implying. Now we ask: do peer multiples and the stock's own
history support those implied expectations, or do they contradict them?

A reverse DCF says "the market expects 15% growth." Relative valuation
asks "are peers at 15% growth trading at this multiple, or much lower?
Has this stock ever traded at this multiple before, and what happened
the last time it did?"

Output: a fair-value-to-price ratio derived from peer/history medians,
not from a discounted cash flow.
"""

from __future__ import annotations

import statistics
from typing import Optional

from iam.data.security import Security
from iam.valuation.types import Method, ValuationResult


class RelativeValuation:
    """Stage 2 of the pipeline.

    Combines three signals into a single fair_value/price ratio:
      - EV/EBITDA vs sector median
      - P/E vs own 10y history (percentile)
      - FCF yield vs peer set

    Each signal is independently weighted; missing signals reduce confidence
    but don't poison the whole result.
    """

    def __init__(
        self,
        weight_sector_multiple: float = 0.40,
        weight_own_history: float = 0.30,
        weight_peer_fcf_yield: float = 0.30,
    ):
        self.w_sec = weight_sector_multiple
        self.w_own = weight_own_history
        self.w_fcf = weight_peer_fcf_yield

    def compute(self, security: Security) -> ValuationResult:
        m = security.market
        notes: list[str] = []
        confidence = 1.0
        components: dict[str, float] = {}

        if m.price is None:
            return ValuationResult(
                method=Method.RELATIVE, confidence=0.0,
                notes=["Relative valuation requires a current price."],
                verdict_text="Insufficient data for relative valuation.",
            )

        # --- Signal 1: EV/EBITDA vs sector median ---
        # If the stock trades at 80% of the sector multiple, that suggests it
        # could move ~25% higher to reach median, treating peer median as fair.
        sec_signal: Optional[float] = None
        if m.ev_ebitda is not None and m.sector_ev_ebitda_median:
            current_multiple = m.ev_ebitda
            peer_multiple = m.sector_ev_ebitda_median
            # fair price / current price = peer_multiple / current_multiple
            # (assuming EBITDA constant, the multiple expansion/contraction
            # would map directly to enterprise value, and approximately to
            # equity value for not-too-levered names.)
            sec_signal = (peer_multiple / current_multiple) - 1
            components["ev_ebitda_vs_sector_pct"] = sec_signal
        else:
            confidence *= 0.85
            notes.append("EV/EBITDA or sector median missing.")

        # --- Signal 2: P/E vs own history percentile ---
        # If the stock is in the bottom quartile of its own 10y range, that's
        # usually a +30% to +50% setup if the historical range is fair.
        own_signal: Optional[float] = None
        if m.pe_ttm is not None and len(m.pe_history) >= 24:
            sorted_pes = sorted(m.pe_history)
            below = sum(1 for x in sorted_pes if x < m.pe_ttm)
            percentile = below / len(sorted_pes)
            median = statistics.median(m.pe_history)
            if m.pe_ttm > 0 and median > 0:
                # Where median is fair, % move = (median / current - 1)
                own_signal = (median / m.pe_ttm) - 1
            components["pe_percentile"] = percentile
            components["pe_vs_own_median_pct"] = own_signal if own_signal is not None else 0.0
        else:
            confidence *= 0.85
            notes.append("Insufficient P/E history (need >=24 datapoints).")

        # --- Signal 3: FCF yield vs peer set ---
        # If the stock's FCF yield is 5% and peers are at 4%, we're cheaper.
        # The implied move to peer-median yield is roughly +25% (peer/current - 1).
        fcf_signal: Optional[float] = None
        if m.fcf_yield is not None and m.peer_fcf_yields:
            peer_median = statistics.median(m.peer_fcf_yields)
            if peer_median > 0 and m.fcf_yield > 0:
                fcf_signal = (m.fcf_yield / peer_median) - 1
                components["fcf_yield_vs_peers_pct"] = fcf_signal
        else:
            confidence *= 0.85
            notes.append("FCF yield or peer set missing.")

        # --- Combine ---
        parts: list[tuple[float, float]] = []
        if sec_signal is not None:
            parts.append((sec_signal, self.w_sec))
        if own_signal is not None:
            parts.append((own_signal, self.w_own))
        if fcf_signal is not None:
            parts.append((fcf_signal, self.w_fcf))

        if not parts:
            return ValuationResult(
                method=Method.RELATIVE, confidence=0.0,
                notes=notes + ["No relative signals available."],
                verdict_text="Insufficient data for relative valuation.",
            )

        total_weight = sum(w for _, w in parts)
        composite_ratio = sum(s * w for s, w in parts) / total_weight

        # Clamp to a sensible range; absurd peer ratios indicate bad data.
        composite_ratio = max(-0.8, min(2.0, composite_ratio))

        fair_value_per_share = m.price * (1 + composite_ratio)

        verdict = self._verdict_text(composite_ratio, len(parts))

        return ValuationResult(
            method=Method.RELATIVE,
            fair_value_per_share=fair_value_per_share,
            fair_value_to_price=composite_ratio,
            confidence=confidence,
            components=components,
            notes=notes,
            verdict_text=verdict,
        )

    @staticmethod
    def _verdict_text(ratio: float, n_signals: int) -> str:
        pct = ratio * 100
        signals = f"{n_signals} signal{'s' if n_signals != 1 else ''}"
        if ratio > 0.20:
            return f"Relative valuation suggests ~{pct:+.0f}% upside vs peers/history ({signals})."
        if ratio > 0.05:
            return f"Modestly cheap on relative basis ({pct:+.0f}%, {signals})."
        if ratio > -0.05:
            return f"Roughly fair on relative basis ({pct:+.0f}%, {signals})."
        if ratio > -0.20:
            return f"Modestly expensive on relative basis ({pct:+.0f}%, {signals})."
        return f"Expensive vs peers/history ({pct:+.0f}%, {signals})."
