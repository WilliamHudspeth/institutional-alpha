"""Bayesian inference for scenario probability updating.

Core components:
- Evidence: Incoming data with likelihoods and reliability
- ScenarioPrior: Probability distribution over scenarios
- BayesianUpdater: Applies Bayes' Theorem with dampening
- ThesisEngine: High-level API for scenario matrices
"""

from .evidence import Evidence, ScenarioLikelihood
from .priors import ScenarioPrior
from .updater import BayesianUpdater, ThesisEngine

__all__ = [
    "Evidence",
    "ScenarioLikelihood",
    "ScenarioPrior",
    "BayesianUpdater",
    "ThesisEngine",
]
