"""Composite scoring engine.

Orchestrates all factors and penalties, applies weights, and returns a
fully-decomposed score.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from iam.data.security import Security
from iam.factors import (
    CrowdingFactor,
    EarningsQualityFactor,
    ExecutionRiskPenalty,
    ExpectationsDifficultyFactor,
    Factor,
    FactorContribution,
    FragilityPenalty,
    IntrinsicValueFactor,
    LeveragePenalty,
    MacroRegimeFactor,
    QualityFactor,
    ReflexivityFactor,
    RelativeValueFactor,
    RunwayFactor,
    SentimentFactor,
)

# Default weights derived from the framework writeup (docs/framework.md).
# Override these by passing a custom dict to ``score(...)``.
DEFAULT_WEIGHTS: dict[str, float] = {
    "expectations_difficulty": 0.22,
    "intrinsic_value": 0.20,
    "quality": 0.12,
    "relative_value": 0.10,
    "sentiment": 0.08,
    "reflexivity": 0.08,
    "reinvestment_runway": 0.07,
    "macro_regime": 0.05,
    "crowding": 0.04,
    "earnings_quality": 0.04,
}

# Penalty weights are how much of the [0,1] penalty actually subtracts from
# the composite. (i.e. a fragility of 1.0 with weight 0.3 subtracts 0.3.)
DEFAULT_PENALTY_WEIGHTS: dict[str, float] = {
    "fragility_penalty": 0.30,
    "leverage_penalty": 0.20,
    "execution_risk_penalty": 0.15,
}


def _default_factors() -> list[Factor]:
    return [
        IntrinsicValueFactor(),
        ExpectationsDifficultyFactor(),
        QualityFactor(),
        RelativeValueFactor(),
        SentimentFactor(),
        ReflexivityFactor(),
        RunwayFactor(),
        MacroRegimeFactor(),
        CrowdingFactor(),
        EarningsQualityFactor(),
    ]


def _default_penalties() -> list[Factor]:
    return [FragilityPenalty(), LeveragePenalty(), ExecutionRiskPenalty()]


@dataclass
class ScoreResult:
    """Decomposed scoring result for a single security."""

    ticker: str
    composite: float  # final score in roughly [-1, 1]
    factor_breakdown: dict[str, FactorContribution] = field(default_factory=dict)
    penalties: dict[str, FactorContribution] = field(default_factory=dict)
    weights: dict[str, float] = field(default_factory=dict)
    penalty_weights: dict[str, float] = field(default_factory=dict)

    def explain(self) -> str:
        """Pretty-print the breakdown."""
        lines = [f"=== {self.ticker} ===", f"Composite score: {self.composite:+.3f}", ""]
        lines.append("Additive factors:")
        for name, c in self.factor_breakdown.items():
            weight = self.weights.get(name, 0.0)
            contrib = c.effective() * weight
            lines.append(
                f"  {name:28s}  value={c.value:+.3f}  conf={c.confidence:.2f}  "
                f"weight={weight:.2f}  -> {contrib:+.3f}"
            )
        if self.penalties:
            lines.append("")
            lines.append("Penalties (subtracted):")
            for name, c in self.penalties.items():
                weight = self.penalty_weights.get(name, 0.0)
                contrib = c.effective() * weight
                lines.append(
                    f"  {name:28s}  value={c.value:.3f}   conf={c.confidence:.2f}  "
                    f"weight={weight:.2f}  -> -{contrib:.3f}"
                )
        return "\n".join(lines)


def score(
    security: Security,
    weights: dict[str, float] | None = None,
    penalty_weights: dict[str, float] | None = None,
    factors: list[Factor] | None = None,
    penalties: list[Factor] | None = None,
) -> ScoreResult:
    """Compute the composite score for a security.

    Parameters
    ----------
    security : Security
        The security to score.
    weights : dict, optional
        Override default factor weights. Keys are factor names.
    penalty_weights : dict, optional
        Override default penalty weights.
    factors, penalties : list, optional
        Inject custom factor lists (e.g. to add a custom factor or remove one).
    """
    w = dict(DEFAULT_WEIGHTS)
    if weights:
        w.update(weights)
    pw = dict(DEFAULT_PENALTY_WEIGHTS)
    if penalty_weights:
        pw.update(penalty_weights)

    factor_list = factors if factors is not None else _default_factors()
    penalty_list = penalties if penalties is not None else _default_penalties()

    factor_results: dict[str, FactorContribution] = {}
    additive_sum = 0.0
    for f in factor_list:
        result = f.compute(security)
        factor_results[result.name] = result
        weight = w.get(result.name, 0.0)
        additive_sum += result.effective() * weight

    penalty_results: dict[str, FactorContribution] = {}
    penalty_sum = 0.0
    for p in penalty_list:
        result = p.compute(security)
        penalty_results[result.name] = result
        weight = pw.get(result.name, 0.0)
        penalty_sum += result.effective() * weight

    composite = additive_sum - penalty_sum

    return ScoreResult(
        ticker=security.ticker,
        composite=composite,
        factor_breakdown=factor_results,
        penalties=penalty_results,
        weights=w,
        penalty_weights=pw,
    )
