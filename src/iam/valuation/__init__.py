"""Valuation methods for the IAM pipeline.

Each method produces a ``ValuationResult`` with a consistent shape, which
lets the triangulator compare them like-for-like.
"""

from iam.valuation.types import (
    Method, ValuationResult, ImpliedExpectations, TriangulationResult,
)
from iam.valuation.reverse_dcf import ReverseDCF
from iam.valuation.relative import RelativeValuation
from iam.valuation.fcfe_dcf import FCFEDCF, FCFEAssumptions
from iam.valuation.sotp import SOTP, Segment
from iam.valuation.triangulator import Triangulator

__all__ = [
    "Method", "ValuationResult", "ImpliedExpectations", "TriangulationResult",
    "ReverseDCF", "RelativeValuation", "FCFEDCF", "FCFEAssumptions",
    "SOTP", "Segment", "Triangulator",
]
