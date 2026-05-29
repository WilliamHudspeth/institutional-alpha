"""Institutional analytics layer.

Advanced analytics engines that provide institutional-grade insights:
- Factor attribution decomposition
- Macro regime detection and dynamic weighting
- Portfolio analytics (future)
- Risk decomposition (future)
"""

from iam.analytics.attribution import AttributionAnalysis, AttributionEngine, FactorContribution
from iam.analytics.regime import (
    MacroRegime,
    RegimeAnalyzer,
    RegimeDetector,
    RegimeIndicators,
    RegimeWeights,
)

__all__ = [
    "AttributionAnalysis",
    "AttributionEngine",
    "FactorContribution",
    "MacroRegime",
    "RegimeAnalyzer",
    "RegimeDetector",
    "RegimeIndicators",
    "RegimeWeights",
]
