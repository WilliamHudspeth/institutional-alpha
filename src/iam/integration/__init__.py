"""Integration layer: hardened wiring between deterministic data and probabilistic valuation.

This module bridges:
- Immutable EquityRiskProfile (ground truth)
- ModelResult (probabilistic shape for arbitration)
- Orchestrator (single entry point)
"""

from .adapter import from_ground_truth
from .orchestrator import Orchestrator
from .types import ModelResult

__all__ = [
    "from_ground_truth",
    "Orchestrator",
    "ModelResult",
]
