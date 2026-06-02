"""Bayesian thesis engine: formalize investment thesis and update with evidence.

Core workflow:
  Prior Thesis → New Evidence → Bayesian Update → Posterior Thesis

Maintains:
- Scenario probabilities and confidence
- Evidence reliability weighting
- Thesis confidence delta tracking
- Scenario migration on new data
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class EvidenceType(Enum):
    """Types of evidence for thesis updating."""

    EARNINGS_BEAT = "earnings_beat"
    EARNINGS_MISS = "earnings_miss"
    GUIDANCE_RAISE = "guidance_raise"
    GUIDANCE_LOWER = "guidance_lower"
    ANALYST_UPGRADE = "analyst_upgrade"
    ANALYST_DOWNGRADE = "analyst_downgrade"
    PRICE_TARGET_RAISE = "price_target_raise"
    PRICE_TARGET_LOWER = "price_target_lower"
    MACRO_SHOCK = "macro_shock"
    COMPETITIVE_THREAT = "competitive_threat"
    NEW_PRODUCT = "new_product"
    M_AND_A = "m_and_a"
    INSIDER_BUYING = "insider_buying"
    INSIDER_SELLING = "insider_selling"
    REGULATORY = "regulatory"


@dataclass
class Scenario:
    """Investment scenario with probability and returns."""

    name: str  # "Bull Case", "Base Case", "Bear Case"
    description: str
    probability: float  # Prior probability (0-1)
    target_price: float
    expected_return: float  # % return if scenario realizes
    thesis: str  # Key assumptions in this scenario

    # Confidence in this scenario's assumptions
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict."""
        return {
            "name": self.name,
            "description": self.description,
            "probability": self.probability,
            "target_price": self.target_price,
            "expected_return": self.expected_return,
            "thesis": self.thesis,
            "confidence": self.confidence,
        }


@dataclass
class Evidence:
    """Piece of evidence for Bayesian updating."""

    evidence_type: EvidenceType
    description: str
    reliability: float  # 0-1, how reliable is this evidence
    impact_magnitude: float  # 0-1, how strong an impact
    bullish_scenarios: list[str]  # Scenarios this supports
    bearish_scenarios: list[str]  # Scenarios this hurts
    timestamp: datetime = field(default_factory=datetime.now)

    def impact_probability(self) -> float:
        """Likelihood factor for Bayesian update."""
        return self.reliability * self.impact_magnitude


@dataclass
class InvestmentThesis:
    """Complete investment thesis with scenarios."""

    ticker: str
    name: str
    current_price: float

    # Scenarios and their probabilities
    scenarios: list[Scenario] = field(default_factory=list)

    # Thesis metadata
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    conviction: str = "MODERATE"  # HIGH, MODERATE, LOW

    # Evidence trail
    evidence_history: list[Evidence] = field(default_factory=list)

    # Return stats
    expected_return: float = 0.0  # Probability-weighted expected return
    return_variance: float = 0.0  # Variance of returns
    sharpe_ratio: float = 0.0  # Risk-adjusted return estimate

    @property
    def total_probability(self) -> float:
        """Sum of scenario probabilities (should be 1.0)."""
        return sum(s.probability for s in self.scenarios)

    @property
    def probability_weighted_price(self) -> float:
        """Probability-weighted expected target price."""
        if not self.scenarios:
            return self.current_price
        return sum(s.target_price * s.probability for s in self.scenarios)

    @property
    def bull_probability(self) -> float:
        """Probability of bull/upside scenarios."""
        if not self.scenarios:
            return 0.0
        upside_scenarios = [s for s in self.scenarios if s.expected_return > 0]
        return sum(s.probability for s in upside_scenarios)

    @property
    def base_probability(self) -> float:
        """Probability of base case."""
        base = next((s for s in self.scenarios if "base" in s.name.lower()), None)
        return base.probability if base else 0.0

    @property
    def bear_probability(self) -> float:
        """Probability of bear/downside scenarios."""
        if not self.scenarios:
            return 0.0
        downside_scenarios = [s for s in self.scenarios if s.expected_return < 0]
        return sum(s.probability for s in downside_scenarios)

    def get_scenario(self, name: str) -> Scenario | None:
        """Get scenario by name."""
        return next((s for s in self.scenarios if s.name == name), None)

    def compute_expected_return(self) -> float:
        """Compute probability-weighted expected return."""
        if not self.scenarios:
            return 0.0
        return sum(s.expected_return * s.probability for s in self.scenarios)

    def compute_return_variance(self) -> float:
        """Compute variance of returns across scenarios."""
        if not self.scenarios or len(self.scenarios) < 2:
            return 0.0

        expected_ret = self.compute_expected_return()
        variance = sum(
            s.probability * (s.expected_return - expected_ret) ** 2 for s in self.scenarios
        )
        return variance

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict."""
        return {
            "ticker": self.ticker,
            "name": self.name,
            "current_price": self.current_price,
            "scenarios": [s.to_dict() for s in self.scenarios],
            "bull_probability": self.bull_probability,
            "base_probability": self.base_probability,
            "bear_probability": self.bear_probability,
            "expected_return": self.compute_expected_return(),
            "conviction": self.conviction,
        }


class ThesisBuilder:
    """Builder for creating investment theses."""

    def __init__(self, ticker: str, name: str, current_price: float) -> None:
        self.thesis = InvestmentThesis(
            ticker=ticker,
            name=name,
            current_price=current_price,
        )

    def add_scenario(
        self,
        name: str,
        description: str,
        probability: float,
        target_price: float,
        expected_return: float,
        thesis_statement: str,
        confidence: float = 1.0,
    ) -> ThesisBuilder:
        """Add a scenario to the thesis."""
        scenario = Scenario(
            name=name,
            description=description,
            probability=probability,
            target_price=target_price,
            expected_return=expected_return,
            thesis=thesis_statement,
            confidence=confidence,
        )
        self.thesis.scenarios.append(scenario)
        return self

    def set_conviction(self, conviction: str) -> ThesisBuilder:
        """Set thesis conviction level."""
        self.thesis.conviction = conviction
        return self

    def build(self) -> InvestmentThesis:
        """Build and return the thesis."""
        # Normalize probabilities
        total_prob = self.thesis.total_probability
        if total_prob > 0 and total_prob != 1.0:
            for scenario in self.thesis.scenarios:
                scenario.probability = scenario.probability / total_prob

        return self.thesis
