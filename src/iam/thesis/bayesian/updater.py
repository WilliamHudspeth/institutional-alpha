from typing import List

from .priors import ScenarioPrior
from .evidence import Evidence


class BayesianUpdater:
    """Computes posterior probabilities using Bayes' Theorem with signal dampening."""

    def update(self, priors: List[ScenarioPrior], evidence: Evidence) -> List[ScenarioPrior]:
        """
        Updates scenario probabilities based on new evidence.
        
        Formula: P(Scenario | Evidence) = [P(Evidence | Scenario) * P(Scenario)] / P(Evidence)
        """
        if not priors:
            return []

        # 1. Calculate the numerator: P(Evidence | Scenario) * P(Scenario)
        unnormalized_posteriors = {}
        marginal_probability_of_evidence = 0.0

        for prior in priors:
            likelihood = evidence.get_dampened_likelihood(prior.label)
            numerator = likelihood * prior.probability
            
            unnormalized_posteriors[prior.label] = numerator
            marginal_probability_of_evidence += numerator

        # If the evidence is impossible in all scenarios, no update occurs to prevent division by zero
        if marginal_probability_of_evidence <= 0:
            return [ScenarioPrior(p.label, p.probability) for p in priors]

        # 2. Normalize to get the Posteriors
        return [
            ScenarioPrior(label, prob / marginal_probability_of_evidence)
            for label, prob in unnormalized_posteriors.items()
        ]