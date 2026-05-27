from dataclasses import dataclass, field
from typing import Dict


@dataclass
class ScenarioLikelihood:
    """P(Evidence | Scenario) - How likely is this evidence if the scenario is true?"""
    probability: float


@dataclass
class Evidence:
    """A new piece of information (e.g., Macro weakens, Earnings beat)."""
    description: str

    # 0.0 to 1.0. A low strength means the data is noisy, poorly calibrated, or old.
    # This directly prevents overfitting by dampening the Bayesian update.
    signal_strength: float = 1.0

    # Maps scenario labels (e.g., "Bull") to their likelihoods
    likelihoods: Dict[str, ScenarioLikelihood] = field(default_factory=dict)

    def get_dampened_likelihood(self, scenario_label: str) -> float:
        """Shrinks the likelihood toward 1.0 (neutral) if signal strength is low."""
        raw_prob = self.likelihoods.get(scenario_label, ScenarioLikelihood(1.0)).probability

        # If strength is 0, effective likelihood is 1.0 (no update).
        return 1.0 - (self.signal_strength * (1.0 - raw_prob))
