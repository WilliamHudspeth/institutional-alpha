"""Core data layer: Security models and institutional data providers."""

from .security import Security, Fundamentals, MarketData, MacroContext, Assumption, Thesis, show_spread, apply_scenario
from .damodaran import DamodaranProvider, MacroBaselines
from .ground_truth import GroundTruthProvider, EquityRiskProfile
from .provenance import attach_provenance

__all__ = [
    # Security models
    "Security",
    "Fundamentals",
    "MarketData",
    "MacroContext",
    "Assumption",
    "Thesis",
    "show_spread",
    "apply_scenario",
    # Institutional providers
    "DamodaranProvider",
    "MacroBaselines",
    "GroundTruthProvider",
    "EquityRiskProfile",
    # Auditing
    "attach_provenance",
]