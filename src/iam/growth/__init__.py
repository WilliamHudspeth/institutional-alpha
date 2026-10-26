"""Growth rate estimation and shrinkage package.

Implements independent growth derivations for DCF, relative multiples, and
market-implied expectations, combining company evidence with empirical base
rates via precision weighting and empirical-Bayes shrinkage (Damodaran,
*Investment Valuation* ch. 11; Mauboussin, Callahan and Majd, *The Base Rate
Book*, 2016; Chan, Karceski and Lakonishok, "The Level and Persistence of
Growth Rates", JF 2003).
"""

from __future__ import annotations

from iam.growth.apply import ensure_growth_profile
from iam.growth.base_rates import SIZE_BUCKETS, base_rate
from iam.growth.estimators import (
    MODEL_ERROR,
    analyst_forward,
    fundamental,
    historical_operating_income,
    historical_revenue,
    market_implied,
    normalised_fundamental,
)
from iam.growth.profile import build_growth_profile, fade_path
from iam.growth.types import GrowthAssignment, GrowthEstimate, GrowthProfile

__all__ = [
    "MODEL_ERROR",
    "SIZE_BUCKETS",
    "GrowthAssignment",
    "GrowthEstimate",
    "GrowthProfile",
    "analyst_forward",
    "base_rate",
    "build_growth_profile",
    "ensure_growth_profile",
    "fade_path",
    "fundamental",
    "historical_operating_income",
    "historical_revenue",
    "market_implied",
    "normalised_fundamental",
]
