from __future__ import annotations

from dataclasses import dataclass, field

from iam.data.security import Security
from iam.valuation.types import TriangulationResult, ValuationResult


@dataclass
class VerdictResult:
    """The final actionable output of the Valuation Pipeline."""
    rating: str
    confidence_band: str
    notes: list[str] = field(default_factory=list)


class VerdictGenerator:
    """Stage 7: Generates a final actionable verdict from the valuation pipeline."""

    def __init__(self, buy_threshold: float = 0.15, sell_threshold: float = -0.10):
        self.buy_threshold = buy_threshold
        self.sell_threshold = sell_threshold

    def generate(self, triangulation: TriangulationResult, relative: ValuationResult, security: Security) -> VerdictResult:
        notes = []
        
        # 1. Determine Rating
        if triangulation.verdict in ("no_data", "disagree"):
            rating = "INCONCLUSIVE"
            notes.append("Triangulation failed to cluster; cannot issue a definitive rating.")
        elif triangulation.cluster_center is None:
            rating = "INCONCLUSIVE"
            notes.append("No implied upside available to generate a rating.")
        else:
            upside = triangulation.cluster_center
            if upside >= self.buy_threshold:
                rating = "BUY"
            elif upside <= self.sell_threshold:
                rating = "SELL"
            else:
                rating = "HOLD"
            notes.append(f"Rating '{rating}' derived from {upside:+.1%} triangulated upside.")

        # 2. Determine Base Confidence
        if triangulation.confidence >= 0.8:
            band = "HIGH"
        elif triangulation.confidence >= 0.5:
            band = "MEDIUM"
        else:
            band = "LOW"
            if rating != "INCONCLUSIVE":
                notes.append("Confidence band is LOW due to weak cluster agreement or missing data.")

        # 3. Peer-Relative Ranking (Damodaran Sector Context)
        if relative.fair_value_to_price is not None and security.sector:
            rel_ratio = relative.fair_value_to_price
            # A positive ratio means fair value > price (discount to peers)
            premium_discount = "discount" if rel_ratio > 0 else "premium"
            notes.append(
                f"[PEER RANKING] Trades at a ~{abs(rel_ratio):.0%} {premium_discount} to {security.sector} peers/history."
            )

        # 4. Apply Penalties (e.g., Leverage Risk)
        # You can expand this to incorporate the Fragility / Execution Risk penalties from v0.1.0
        f = security.fundamentals
        if f.total_debt is not None and f.ebitda_ttm is not None and f.ebitda_ttm > 0:
            leverage = f.total_debt / f.ebitda_ttm
            if leverage >= 4.0:
                notes.append(f"[RISK PENALTY] High leverage detected (Debt/EBITDA = {leverage:.1f}x).")
                if band == "HIGH":
                    band = "MEDIUM"
                    notes.append("Conviction downgraded due to balance sheet risk.")

        return VerdictResult(rating=rating, confidence_band=band, notes=notes)