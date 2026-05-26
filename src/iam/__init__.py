"""Institutional Alpha Model (IAM).

A multi-factor equity scoring framework. See docs/framework.md for the
conceptual overview and docs/factors.md for per-factor definitions.
"""

from iam.data.security import Security, Fundamentals, MarketData, MacroContext
from iam.engine.composite import score, ScoreResult, DEFAULT_WEIGHTS

__version__ = "0.1.0"

__all__ = [
    "Security",
    "Fundamentals",
    "MarketData",
    "MacroContext",
    "score",
    "ScoreResult",
    "DEFAULT_WEIGHTS",
]
