"""Scenario Ontology for the Bayesian Thesis Engine.

Formalizes the relationship between narrative (thesis), mathematical bounds
(assumptions), and price targets. Each scenario is a semantic unit that ties
a coherent business case to specific valuation outcomes.

This is the bridge between qualitative investment theses and quantitative
Bayesian updating. When evidence arrives, we don't tweak arbitrary numbers—
we update the probability of formally-defined scenarios.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ScenarioAssumptions:
    """The explicit mathematical bounds for a scenario.

    These are not independent variables. They form a coherent narrative:
    - If "fee compression" is the thesis, then forecast_growth drops
      AND operating_margin compresses.
    - If "AUM momentum" is the thesis, then forecast_growth rises
      AND WACC compresses (lower risk premium).
    """

    forecast_growth: float  # CAGR during projection period
    wacc: float  # Discount rate (reflects risk in this scenario)
    terminal_growth: float  # Perpetuity growth rate
    operating_margin: float | None = None  # If known for this scenario


@dataclass
class ValuationScenario:
    """A formal hypothesis tying a narrative to mathematical bounds.

    Each scenario represents a coherent business thesis. The orthogonality
    principle demands that scenarios should NOT overlap in their narratives—
    you should never have a "Bull" case that assumes fee compression.
    """

    name: str  # e.g., "Bull Case", "Base Case", "Bear Case"
    probability: float  # Prior: P(Scenario)
    thesis: str  # The narrative (e.g., "Fee compression + AUM slowdown")
    expected_signals: list[
        str
    ]  # Evidence that would confirm this (e.g., ["Missed EPS", "Declining inflows"])
    assumptions: ScenarioAssumptions  # Mathematical bounds
    target_price: float = 0.0  # Fair value from DCF (populated by valuation engine)

    def __post_init__(self):
        """Clamp probability to [0, 1] after initialization."""
        self.probability = max(0.0, min(1.0, self.probability))

    def summarize(self) -> str:
        """Return a human-readable summary of the scenario."""
        return (
            f"{self.name} ({self.probability * 100:.0f}%)\n"
            f"  Thesis: {self.thesis}\n"
            f"  Target: ${self.target_price:.2f}\n"
            f"  Growth: {self.assumptions.forecast_growth * 100:.1f}% | "
            f"WACC: {self.assumptions.wacc * 100:.2f}% | "
            f"Terminal g: {self.assumptions.terminal_growth * 100:.2f}%"
        )


@dataclass
class ScenarioMatrix:
    """A complete set of valuation scenarios for a security.

    This is the "state space" of the investment thesis. Any Bayesian update
    changes the probabilities of these scenarios, not the price targets or
    assumptions (those stay constant until the thesis changes).
    """

    ticker: str
    scenarios: dict[str, ValuationScenario] = field(default_factory=dict)
    created_at: str | None = None

    def get_pwev(self) -> float:
        """Calculate Probability-Weighted Expected Value across all scenarios."""
        if not self.scenarios:
            return 0.0
        total_prob = sum(s.probability for s in self.scenarios.values())
        if total_prob == 0:
            return 0.0
        return sum(s.target_price * s.probability / total_prob for s in self.scenarios.values())

    def get_upside(self, current_price: float) -> float:
        """Calculate implied upside from PWEV to current price."""
        pwev = self.get_pwev()
        if current_price <= 0:
            return 0.0
        return (pwev / current_price) - 1.0

    def summarize(self) -> str:
        """Return a human-readable summary of all scenarios."""
        lines = [f"Scenario Matrix for {self.ticker}"]
        lines.append(f"PWEV: ${self.get_pwev():.2f}")
        lines.append("")
        for scenario in self.scenarios.values():
            lines.append(scenario.summarize())
            lines.append("")
        return "\n".join(lines)
