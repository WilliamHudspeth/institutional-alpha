"""Stage 3b: Sum-of-the-Parts (SOTP) valuation.

For multi-segment businesses (think Amazon: retail + AWS + ads + logistics),
a single-discount-rate FCFE DCF systematically misprices because each
segment has different growth, margins, and risk.

SOTP values each segment independently using the appropriate method:
  - Mature cash-cow segments → standalone DCF or peer multiple
  - High-growth segments → forward revenue multiple
  - Optionality segments → real-options or scenario-weighted

Then sums to enterprise value, adjusts for net debt and minorities, and
divides by share count.

Status: scaffolded. The full implementation requires segment-level
financials which aren't in the v0.1 Fundamentals dataclass. A real
implementation would extend Fundamentals with a `segments` list and
let SOTP iterate over each one.

For now, this module is a placeholder that the pipeline can call but
will skip with reduced confidence when segment data is absent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from iam.data.security import Security
from iam.valuation.types import Method, ValuationResult


@dataclass
class Segment:
    """A single business segment for SOTP purposes."""
    name: str
    revenue_ttm: Optional[float] = None
    operating_income_ttm: Optional[float] = None
    growth_rate: Optional[float] = None
    multiple: Optional[float] = None        # e.g. EV/Sales for high-growth
    multiple_type: str = "ev_sales"           # "ev_sales", "ev_ebit", "ev_ebitda"
    notes: str = ""


class SOTP:
    """Stage 3b — sum-of-the-parts.

    Currently a scaffolded placeholder. To use, attach segments to
    ``security.qualitative['segments']`` as a list of ``Segment`` instances.
    """

    def compute(self, security: Security) -> ValuationResult:
        segments = security.qualitative.get("segments")
        if not segments:
            return ValuationResult(
                method=Method.INTRINSIC,
                confidence=0.0,
                notes=[
                    "SOTP requires segment-level data — none provided. "
                    "Attach segments to security.qualitative['segments']."
                ],
                verdict_text="SOTP skipped: no segments provided.",
            )

        m = security.market
        f = security.fundamentals
        if m.price is None or f.shares_outstanding is None:
            return ValuationResult(
                method=Method.INTRINSIC, confidence=0.0,
                notes=["SOTP requires price and shares outstanding."],
                verdict_text="Insufficient data for SOTP.",
            )

        notes: list[str] = []
        confidence = 1.0
        total_ev = 0.0
        components: dict[str, float] = {}

        for seg in segments:
            seg_ev = self._segment_ev(seg)
            if seg_ev is None:
                confidence *= 0.7
                notes.append(f"Segment '{seg.name}' missing inputs.")
                continue
            total_ev += seg_ev
            components[f"segment_{seg.name}_ev"] = seg_ev

        if total_ev == 0:
            return ValuationResult(
                method=Method.INTRINSIC, confidence=0.0,
                notes=notes + ["Could not value any segment."],
                verdict_text="SOTP yielded no valuable segments.",
            )

        # Bridge from enterprise to equity value.
        net_debt = (f.total_debt or 0) - (f.cash_and_equivalents or 0)
        equity_value = total_ev - net_debt
        fair_value_per_share = equity_value / f.shares_outstanding
        fair_value_to_price = (fair_value_per_share / m.price) - 1
        fair_value_to_price = max(-0.9, min(3.0, fair_value_to_price))

        return ValuationResult(
            method=Method.INTRINSIC,
            fair_value_per_share=fair_value_per_share,
            fair_value_to_price=fair_value_to_price,
            confidence=confidence,
            components=components,
            notes=notes,
            verdict_text=(
                f"SOTP across {len(segments)} segments implies "
                f"{fair_value_to_price*100:+.0f}% vs current price."
            ),
        )

    @staticmethod
    def _segment_ev(seg: Segment) -> Optional[float]:
        if seg.multiple is None:
            return None
        if seg.multiple_type == "ev_sales" and seg.revenue_ttm is not None:
            return seg.revenue_ttm * seg.multiple
        if seg.multiple_type in ("ev_ebit", "ev_ebitda") and seg.operating_income_ttm is not None:
            return seg.operating_income_ttm * seg.multiple
        return None
