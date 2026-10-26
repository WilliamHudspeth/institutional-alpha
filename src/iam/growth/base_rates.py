"""Size-conditioned empirical growth base rates and dispersions.

Because corporate growth exhibits weak persistence beyond chance (Chan, Karceski
and Lakonishok, "The Level and Persistence of Growth Rates", JF 2003), company
growth estimates are shrunk toward a population prior stratified by revenue size
(Mauboussin, Callahan and Majd, *The Base Rate Book*, 2016; Damodaran,
*Investment Valuation* ch. 11).
"""

from __future__ import annotations

import math

from iam.growth.types import GrowthEstimate

# (revenue upper bound, exclusive; median nominal annual revenue growth; dispersion).
# Starting values from Mauboussin et al. and the 80-company US backtest (2012-2025),
# to be recalibrated on the Track A universe.
SIZE_BUCKETS: tuple[tuple[float, float, float], ...] = (
    (1e9, 0.080, 0.120),
    (5e9, 0.065, 0.090),
    (25e9, 0.055, 0.070),
    (100e9, 0.045, 0.060),
    (math.inf, 0.040, 0.050),
)


def base_rate(revenue: float | None) -> GrowthEstimate:
    """Return the size-bucketed 5-year revenue growth base rate and dispersion."""
    if revenue is None or revenue <= 0:
        _, median, dispersion = SIZE_BUCKETS[2]
        return GrowthEstimate(
            method="base_rate",
            value=median,
            std_error=dispersion,
            horizon_years=5,
            confidence=0.3,
            inputs={},
            notes=("Revenue missing or non-positive; using middle size bucket (25B).",),
        )

    for upper, median, dispersion in SIZE_BUCKETS:
        if revenue < upper:
            return GrowthEstimate(
                method="base_rate",
                value=median,
                std_error=dispersion,
                horizon_years=5,
                confidence=0.6,
                inputs={"revenue": float(revenue)},
            )

    _, median, dispersion = SIZE_BUCKETS[-1]
    return GrowthEstimate(
        method="base_rate",
        value=median,
        std_error=dispersion,
        horizon_years=5,
        confidence=0.6,
        inputs={"revenue": float(revenue)},
    )
