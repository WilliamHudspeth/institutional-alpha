"""Evidence and Likelihood modeling for Bayesian Updates.

When new information arrives (earnings beat, macro shock, guidance change),
we represent it as an Evidence object with:
1. A description (what happened)
2. Likelihoods under each scenario (how likely is this evidence under each case?)
3. A reliability parameter (how confident are we in this evidence?)

The reliability parameter is CRITICAL. It prevents the model from wildly
overreacting to a single noisy data point. An earnings beat with 70% reliability
gets dampened much more than a macro shock with 95% reliability.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ScenarioLikelihood:
    """P(Evidence | Scenario) - How likely is this evidence if the scenario is true?"""

    probability: float

    def __post_init__(self):
        """Clamp to valid probability range."""
        self.probability = max(0.01, min(1.0, self.probability))


@dataclass
class Evidence:
    """A piece of incoming data (e.g., an earnings report or macro shock).

    Example:
        EPS_Beat = Evidence(
            type="EARNINGS_BEAT",
            description="Missed EPS by 2% but beat guidance",
            likelihoods={"Bear": 0.10, "Base": 0.50, "Bull": 0.90},
            reliability=0.70  # FY24 accuracy was 70%
        )
    """

    type: str  # e.g., "EARNINGS_BEAT", "CREDIT_WIDENING", "AUM_INFLOW"
    description: str  # Human-readable summary

    # How likely is this evidence under each scenario?
    # Maps scenario name (e.g., "Bull Case") to P(Evidence | Scenario)
    likelihoods: dict[str, float | ScenarioLikelihood] = field(default_factory=dict)

    # 0.0 = Pure noise (unreliable), 1.0 = Absolute truth
    # Directly prevents overfitting by dampening Bayesian updates
    reliability: float = 1.0

    def __post_init__(self):
        """Normalize likelihoods and clamp reliability."""
        # Convert dict floats to ScenarioLikelihood objects if needed
        normalized = {}
        for k, v in self.likelihoods.items():
            if isinstance(v, float):
                normalized[k] = ScenarioLikelihood(v)
            else:
                normalized[k] = v
        self.likelihoods = normalized
        self.reliability = max(0.0, min(1.0, self.reliability))

    def get_dampened_likelihood(self, scenario_label: str) -> float:
        """Shrinks the likelihood toward 1.0 (neutral) based on reliability.

        Formula: L_dampened = 1.0 + (L_raw - 1.0) * reliability

        This prevents the model from wildly overfitting:
        - If reliability=1.0 (trusted), use the raw likelihood
        - If reliability=0.5 (noisy), shrink the update halfway to neutral (1.0)
        - If reliability=0.0 (unreliable), the update is neutral regardless
        """
        raw_prob = self.likelihoods.get(scenario_label, ScenarioLikelihood(1.0)).probability

        # Shrink toward 1.0 based on unreliability
        dampened_val = 1.0 + (raw_prob - 1.0) * self.reliability
        return max(0.01, dampened_val)  # Prevent zero-probability trap

    def get_dampened_likelihoods(self) -> dict[str, float]:
        """Return all likelihoods, dampened by reliability."""
        return {
            scenario_label: self.get_dampened_likelihood(scenario_label)
            for scenario_label in self.likelihoods.keys()
        }
