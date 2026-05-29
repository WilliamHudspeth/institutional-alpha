"""Thesis scenarios and Bayesian updating engine.

Two main components:
1. Scenario Ontology: Formal theses with mathematical bounds and narratives
2. Bayesian Updating: Probability updates based on evidence with dampening
"""

from .battlefield import BattlefieldReport, ValuationBattlefield
from .bayesian.evidence import Evidence, ScenarioLikelihood
from .bayesian.updater import BayesianUpdater, ThesisEngine
from .drift import ThesisDriftDetector, ThesisDriftReport
from .engine import ThesisEngine as ThesisEvaluator
from .engine import ThesisEvaluation
from .scenarios import ScenarioAssumptions, ScenarioMatrix, ValuationScenario

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
    # Operational Drift & Battlefield
    "ThesisDriftDetector",
    "ThesisDriftReport",
    "ValuationBattlefield",
    "BattlefieldReport",
]
