"""Thesis scenarios and Bayesian updating engine.

Two main components:
1. Scenario Ontology: Formal theses with mathematical bounds and narratives
2. Bayesian Updating: Probability updates based on evidence with dampening
"""

from .engine import ThesisEngine as ThesisEvaluator, ThesisEvaluation
from .scenarios import ScenarioAssumptions, ValuationScenario, ScenarioMatrix
from .bayesian.evidence import Evidence, ScenarioLikelihood
from .bayesian.updater import BayesianUpdater, ThesisEngine

__all__ = [
    # Legacy
    "ThesisEvaluator",
    "ThesisEvaluation",
    # New scenario ontology
    "ScenarioAssumptions",
    "ValuationScenario",
    "ScenarioMatrix",
    # Bayesian inference
    "Evidence",
    "ScenarioLikelihood",
    "BayesianUpdater",
    "ThesisEngine",  # New Bayesian version
]