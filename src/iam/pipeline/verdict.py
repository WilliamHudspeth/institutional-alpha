from dataclasses import dataclass, field
from typing import Optional
from iam.data.security import Security
from iam.valuation.types import TriangulationResult, ValuationResult

@dataclass
class VerdictResult:
    rating: str
    notes: list[str] = field(default_factory=list)

class VerdictGenerator:
    def generate(self, tri: TriangulationResult, rel: ValuationResult, sec: Security) -> VerdictResult:
        notes = []
        move = tri.cluster_center if tri.cluster_center is not None else 0.0
        conf = tri.confidence
        
        if tri.verdict in ("no_data", "disagree"):
            return VerdictResult("INCONCLUSIVE", ["Methods disagree or lack data."])
            
        if move > 0.20 and conf >= 0.70: rating = "STRONG BUY"
        elif move > 0.10: rating = "BUY"
        elif move > -0.10: rating = "HOLD"
        elif move > -0.20: rating = "SELL"
        else: rating = "STRONG SELL"
            
        # Value Trap Detection
        if move > 0.15 and rel.fair_value_to_price is not None and rel.fair_value_to_price < -0.15:
             rating = "VALUE TRAP WARNING"
             notes.append("WARNING: Intrinsic upside high, but peers trade at a discount.")
             
        notes.append(f"Base rating: {rating} (Implied Move: {move*100:+.1f}%, Conviction: {conf:.2f})")
        return VerdictResult(rating=rating, notes=notes)
