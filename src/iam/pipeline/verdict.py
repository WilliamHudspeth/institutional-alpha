from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from iam.data.security import Security
from iam.valuation.types import TriangulationResult, ValuationResult
from iam.pipeline.arbitration import ConsensusEngine, ArbitrationResult


@dataclass
class VerdictResult:
    """The final actionable output of the Valuation Pipeline."""
    rating: str
    confidence_band: str
    notes: list[str] = field(default_factory=list)
    arbitration: Optional[ArbitrationResult] = None
    blended_upside: Optional[float] = None


class VerdictGenerator:
    """Stage 7: Generates a final actionable verdict from the valuation pipeline."""

    def __init__(self, buy_threshold: float = 0.15, sell_threshold: float = -0.10):
        self.buy_threshold = buy_threshold
        self.sell_threshold = sell_threshold

    def generate(
        self,
        triangulation: TriangulationResult,
        relative: ValuationResult,
        security: Security,
        synthesis_upside: Optional[float] = None,
    ) -> VerdictResult:
        """Generate verdict using Master Arbitration Layer if synthesis available.

        Args:
            triangulation: Stage 4 triangulation result (traditional pipeline)
            relative: Stage 2 relative valuation result
            security: Security object
            synthesis_upside: Optional weighted upside from multi-lens synthesis
        """
        notes = []
        pipeline_upside = triangulation.cluster_center or 0.0
        arbitration = None
        blended_upside = None

        # 1. Use Consensus Engine if synthesis data is available
        if synthesis_upside is not None and triangulation.cluster_center is not None:
            arbitration = ConsensusEngine.arbitrate_verdict(
                pipeline_upside=triangulation.cluster_center,
                synthesis_upside=synthesis_upside,
                primary_confidence=triangulation.confidence,
            )
            rating = arbitration.rating
            blended_upside = arbitration.blended_upside
            notes.append(
                f"Rating '{rating}' derived from Master Arbitration Layer (consensus engine)."
            )
            notes.append(
                f"Blended Implied Move: {arbitration.blended_upside * 100:+.1f}%"
            )
            notes.append(
                f"  ↳ Traditional Engine Weight: {arbitration.pipeline_weight_used * 100:.0f}%"
            )
            notes.append(
                f"  ↳ Multi-Lens Synthesis Weight: {arbitration.synthesis_weight_used * 100:.0f}%"
            )
            if arbitration.confidence_regime != "HIGH":
                notes.append(
                    "Confidence band is MODERATE due to conflicting valuation methodologies."
                )
        else:
            # Legacy single-lens verdict generation
            if triangulation.verdict in ("no_data", "disagree"):
                rating = "INCONCLUSIVE"
                notes.append(
                    "Triangulation failed to cluster; cannot issue a definitive rating."
                )
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

        return VerdictResult(
            rating=rating,
            confidence_band=band,
            notes=notes,
            arbitration=arbitration,
            blended_upside=blended_upside,
        )

EXPLAIN_STAGE_1 = """### Stage 1: Reverse DCF — What does the market expect?
**What we do:** We take the current stock price and solve backwards for the growth rate the market is already pricing in. No opinions yet, just math.

**Why it matters:** If the market expects 25% growth and the company has never done more than 10%, that is a red flag before we build any model."""

EXPLAIN_STAGE_2 = """### Stage 2: Relative — Do peers and history support it?
**What we do:** We check the stock against four independent yardsticks: (1) peers' EV/EBITDA, (2) its own 10-year P/E history, (3) FCF yield vs peers, and (4) Damodaran regression — what the multiple *should* be given its fundamentals.

**Why it matters:** A great story that trades at 40x when peers trade at 20x needs a reason. This stage finds that reason or flags the gap."""

EXPLAIN_STAGE_3 = """### Stage 3: Intrinsic — What is it worth bottom-up?
**What we do:** We build a fresh DCF from your fundamentals only. We use your revenue, margins, reinvestment needs, and a WACC derived from the company's actual debt rating — not a market multiple.

**Why it matters:** This is your independent anchor. It does not care what peers trade at."""

EXPLAIN_STAGE_4 = """### Stage 4: Triangulation — Do the three answers agree?
**What we do:** We put Stage 1, 2, and 3 on the same chart. We do not average them. We look for clustering.

**Why it matters:** Agreement = high conviction. Disagreement = risk. If Reverse DCF says $180, Relative says $95, and Intrinsic says $98, the market is pricing something the fundamentals do not support."""

EXPLAIN_STAGE_5 = """### Stage 5: Macro Outlier — What breaks under stress?
**What we do:** We shock interest rates (+50 bps, +100 bps) and credit spreads. We do not re-run everything — we test which names move more than 10% on that shock.

**Why it matters:** Some businesses are rate-sensitive by design. You want to know before the Fed moves."""

EXPLAIN_STAGE_6 = """### Stage 6: Macro Re-overlay — Re-price only what matters
**What we do:** If Stage 5 flagged a name, we re-run Stages 1-3 with the stressed WACC. If not flagged, we keep the original numbers. This saves time and avoids noise.

**Why it matters:** You get a real stress-test verdict without re-pricing the whole universe."""

EXPLAIN_STAGE_7 = """### Stage 7: Verdict — So what do we do?
**What we do:** We combine everything into one action. We weight the three valuations by confidence, apply penalty factors (leverage, fragility), and rank the stock vs its Damodaran industry.

**Why it matters:** This is the only line most users need."""