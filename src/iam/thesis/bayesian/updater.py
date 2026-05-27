"""Core Bayesian Math Engine for scenario probability updating.

This module executes Bayes' Theorem without touching the DCF engine or
scenario assumptions. When new evidence arrives, we update probabilities,
not fundamentals. This keeps the model mathematically coherent and prevents
narrative drift.

Formula (Bayes' Theorem):
    P(Scenario | Evidence) = [P(Evidence | Scenario) × P(Scenario)] / P(Evidence)

Where:
    P(Scenario) = Prior probability
    P(Evidence | Scenario) = Likelihood (how likely is this evidence under this scenario?)
    P(Evidence) = Marginal likelihood (probability of observing this evidence overall)
"""

from __future__ import annotations

from typing import List, Union

from .priors import ScenarioPrior
from .evidence import Evidence
from iam.thesis.scenarios import ValuationScenario, ScenarioMatrix


class BayesianUpdater:
    """Computes posterior probabilities using Bayes' Theorem with signal dampening."""

    @staticmethod
    def update(
        priors: List[ScenarioPrior], evidence: Evidence
    ) -> List[ScenarioPrior]:
        """Updates scenario probabilities based on new evidence.

        Formula: P(Scenario | Evidence) = [P(Evidence | Scenario) * P(Scenario)] / P(Evidence)

        Args:
            priors: List of ScenarioPrior objects with current probabilities
            evidence: Evidence object with likelihoods and reliability

        Returns:
            Updated list of ScenarioPrior objects with posterior probabilities
        """
        if not priors:
            return []

        # 1. Calculate unnormalized posteriors: P(Evidence | Scenario) * P(Scenario)
        unnormalized_posteriors = {}
        marginal_probability_of_evidence = 0.0

        for prior in priors:
            # Get dampened likelihood (prevents overfitting based on reliability)
            likelihood = evidence.get_dampened_likelihood(prior.label)
            numerator = likelihood * prior.probability

            unnormalized_posteriors[prior.label] = numerator
            marginal_probability_of_evidence += numerator

        # Safeguard: if evidence is impossible in all scenarios, no update
        if marginal_probability_of_evidence <= 0:
            return [ScenarioPrior(p.label, p.probability) for p in priors]

        # 2. Normalize to get posterior probabilities (sum to 1.0)
        return [
            ScenarioPrior(label, prob / marginal_probability_of_evidence)
            for label, prob in unnormalized_posteriors.items()
        ]


class ThesisEngine:
    """High-level interface for updating ValuationScenario matrices with evidence.

    This wraps BayesianUpdater but works directly with ValuationScenario objects,
    making the API more intuitive for investment applications.
    """

    @staticmethod
    def apply_update(
        matrix: Union[ScenarioMatrix, List[ValuationScenario]], evidence: Evidence
    ) -> Union[ScenarioMatrix, List[ValuationScenario]]:
        """Apply Bayesian update to a scenario matrix.

        Args:
            matrix: Either a ScenarioMatrix or list of ValuationScenario objects
            evidence: Evidence to apply

        Returns:
            Updated matrix/scenarios with new posterior probabilities
        """
        if isinstance(matrix, ScenarioMatrix):
            # Convert scenarios to priors
            priors = [
                ScenarioPrior(label, scenario.probability)
                for label, scenario in matrix.scenarios.items()
            ]

            # Apply Bayesian update
            posteriors = BayesianUpdater.update(priors, evidence)

            # Map posteriors back to scenarios
            for posterior in posteriors:
                if posterior.label in matrix.scenarios:
                    matrix.scenarios[posterior.label].probability = posterior.probability

            return matrix
        else:
            # Handle list of ValuationScenario objects
            priors = [ScenarioPrior(s.name, s.probability) for s in matrix]
            posteriors = BayesianUpdater.update(priors, evidence)

            # Update probabilities
            for scenario, posterior in zip(matrix, posteriors):
                scenario.probability = posterior.probability

            return matrix