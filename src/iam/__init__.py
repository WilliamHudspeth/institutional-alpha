"""Institutional Alpha Model (IAM).

A multi-factor equity scoring framework. As of v0.2.0-alpha, the project has
two complementary entry points:

  - ``iam.score(security)`` -- the parallel factor-scoring engine from v0.1.0.
    Useful for cross-sectional ranking and as inputs to the pipeline.

  - ``iam.ValuationPipeline().run(security)`` -- the new sequential pipeline:
    Reverse DCF -> Relative -> Intrinsic -> Triangulation.
"""

from iam.data.security import Security, Fundamentals, MarketData, MacroContext
from iam.engine.composite import score, ScoreResult, DEFAULT_WEIGHTS
from iam.pipeline import ValuationPipeline, PipelineReport

__version__ = "0.2.0a0"

__all__ = [
    "Security",
    "Fundamentals",
    "MarketData",
    "MacroContext",
    "score",
    "ScoreResult",
    "DEFAULT_WEIGHTS",
    "ValuationPipeline",
    "PipelineReport",
]
