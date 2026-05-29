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

import sys

# Prevent potential Windows terminal Unicode encoding crashes (e.g. yfinance printing unicode arrows)
if sys.platform.startswith("win"):
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(errors="backslashreplace")
        except Exception:
            pass
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(errors="backslashreplace")
        except Exception:
            pass


from iam.data.security import Fundamentals, MacroContext, MarketData, Security
from iam.engine.composite import DEFAULT_WEIGHTS, ScoreResult, score
from iam.pipeline import PipelineReport, ValuationPipeline

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
