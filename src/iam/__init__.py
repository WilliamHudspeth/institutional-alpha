"""Institutional Alpha Model (IAM).

A multi-factor equity scoring framework with institutional cost of capital baselines
and empirical backtesting. As of v0.3.4, the project includes:

  - ``iam.score(security)`` -- the parallel factor-scoring engine.
    Useful for cross-sectional ranking and as inputs to the pipeline.

  - ``iam.ValuationPipeline().run(security)`` -- the sequential pipeline:
    Reverse DCF -> Relative -> Intrinsic -> Triangulation.

  - ``iam.api.value_security(security)`` -- the institutional orchestrator.
    Unified cost of capital baselines (Damodaran) + Bayesian updating.

  - ``iam.backtest.run_backtest(universe, dates)`` -- production-grade historical backtest.
    Measures Information Coefficient to calibrate Bayesian reliability weights empirically.
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
