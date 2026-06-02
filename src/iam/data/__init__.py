"""Core data layer: Security models and institutional data providers."""

from .damodaran import DamodaranProvider, MacroBaselines
from .ground_truth import EquityRiskProfile, GroundTruthProvider
from .provenance import attach_provenance
from .security import (
    Assumption,
    Fundamentals,
    MacroContext,
    MarketData,
    Security,
    Thesis,
    apply_scenario,
    show_spread,
)

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
