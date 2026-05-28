"""Valuation methods for the IAM pipeline.

Each method produces a ``ValuationResult`` with a consistent shape, which
lets the triangulator compare them like-for-like.
"""

from iam.valuation.beta import (
    get_custom_beta_for_intrinsic,
    get_yahoo_beta,
    market_value_of_debt,
    relever_beta,
    unlever_beta,
)
from iam.valuation.fcfe_dcf import FCFEDCF, FCFEAssumptions
from iam.valuation.multiples_regression import (
    REGRESSIONS,
    RegressionInputs,
    predict_all,
    predict_multiple,
)
from iam.valuation.relative import RelativeValuation
from iam.valuation.reverse_dcf import ReverseDCF
from iam.valuation.sotp import SOTP, Segment
from iam.valuation.triangulator import Triangulator
from iam.valuation.types import (
    ImpliedExpectations,
    Method,
    TriangulationResult,
    ValuationResult,
)

__all__ = [
    "Method",
    "ValuationResult",
    "ImpliedExpectations",
    "TriangulationResult",
    "ReverseDCF",
    "RelativeValuation",
    "FCFEDCF",
    "FCFEAssumptions",
    "SOTP",
    "Segment",
    "Triangulator",
    "RegressionInputs",
    "predict_multiple",
    "predict_all",
    "REGRESSIONS",
    "unlever_beta",
    "relever_beta",
    "market_value_of_debt",
    "get_yahoo_beta",
    "get_custom_beta_for_intrinsic",
]
