"""Monte Carlo layer over the two-stage FCFE DCF.

Where ``FCFEDCF`` blends three hand-picked scenarios (Bear/Base/Bull) into a
PWEV, this engine samples the *joint* assumption space — growth, discount
rate, and operating margin — and reports the resulting fair-value
distribution: percentiles instead of a point estimate, and P(upside) instead
of a binary verdict.

Contract (same as ``iam.elasticity``): pure function of the ``Security``, no
I/O, no mutation. Missing inputs degrade confidence rather than raising.

Sampling model
--------------
Each dimension is an independent normal around the analyst's base case:

  * ``growth ~ N(forecast_growth, GROWTH_STD)``
  * ``wacc   ~ N(forecast_discount_rate, WACC_STD)`` floored at ``MIN_WACC``
  * ``margin ~ N(operating_margin, MARGIN_STD)`` floored at ``MIN_MARGIN``;
    the draw scales base FCFE proportionally (margin_draw / base_margin).
    When ``operating_margin`` is absent the margin dimension is not sampled
    and confidence is reduced.

Standard deviations are explicit module constants (the roadmap's "No Magic
Numbers" principle) and overridable per security via ``qualitative`` keys
``mc_growth_std`` / ``mc_wacc_std`` / ``mc_margin_std``.

Draws where the model would not converge (wacc <= terminal growth) are
dropped, not clamped — ``two_stage_pv`` returns None for them and the
effective sample count is reported in ``components``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from iam.data.security import Security
from iam.lenses.base import two_stage_pv

DEFAULT_WACC = 0.09
DEFAULT_GROWTH = 0.08
DEFAULT_TERMINAL_GROWTH = 0.025
DEFAULT_HIGH_GROWTH_YEARS = 10

DEFAULT_N_SAMPLES = 2000
DEFAULT_SEED = 7

GROWTH_STD = 0.020
WACC_STD = 0.010
MARGIN_STD = 0.020

MIN_WACC = 0.02
MIN_MARGIN = 0.01

PERCENTILES = (5, 25, 50, 75, 95)

# If more than this share of draws fail to converge, the assumption cloud
# sits too close to the r <= g_terminal boundary to trust the tails.
MAX_DROPPED_SHARE = 0.5


@dataclass
class MonteCarloDistribution:
    """Fair-value distribution from sampled DCF assumptions.

    Mirrors the conventions of ``iam.elasticity.types``: a ``confidence`` in
    [0, 1], a ``components`` audit dict, a plain-English ``narrative``, and
    ``notes`` for caveats. ``percentiles`` is keyed by the integer percentile
    (5, 25, 50, 75, 95); empty when the distribution could not be computed.
    """

    percentiles: dict[int, float] = field(default_factory=dict)
    mean_fair_value: float | None = None
    std_fair_value: float | None = None
    prob_upside: float | None = None  # P(fair value > current price)
    confidence: float = 0.0
    components: dict[str, float] = field(default_factory=dict)
    narrative: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def median_fair_value(self) -> float | None:
        return self.percentiles.get(50)


class MonteCarloDCF:
    """Sample growth/WACC/margin and return fair-value percentiles."""

    def __init__(self, n_samples: int = DEFAULT_N_SAMPLES, seed: int = DEFAULT_SEED):
        self.n_samples = n_samples
        self.seed = seed

    def run(self, security: Security) -> MonteCarloDistribution:
        f = security.fundamentals
        m = security.market
        q = security.qualitative or {}
        notes: list[str] = []
        confidence = 1.0

        if f.fcf_ttm is None or not f.shares_outstanding:
            return MonteCarloDistribution(
                confidence=0.0,
                narrative="Monte Carlo DCF requires FCF TTM and shares outstanding.",
                notes=["Missing fcf_ttm or shares_outstanding — nothing to sample."],
            )

        fcfe0 = f.fcf_ttm / f.shares_outstanding
        growth = float(q.get("forecast_growth", DEFAULT_GROWTH))
        wacc = float(q.get("forecast_discount_rate", DEFAULT_WACC))
        terminal = float(q.get("forecast_terminal_growth", DEFAULT_TERMINAL_GROWTH))
        years = int(q.get("forecast_high_growth_years", DEFAULT_HIGH_GROWTH_YEARS))

        growth_std = float(q.get("mc_growth_std", GROWTH_STD))
        wacc_std = float(q.get("mc_wacc_std", WACC_STD))
        margin_std = float(q.get("mc_margin_std", MARGIN_STD))

        rng = np.random.default_rng(self.seed)
        growth_draws = rng.normal(growth, growth_std, self.n_samples)
        wacc_draws = np.maximum(rng.normal(wacc, wacc_std, self.n_samples), MIN_WACC)

        base_margin = f.operating_margin
        if base_margin is not None and base_margin > 0:
            margin_draws = np.maximum(
                rng.normal(base_margin, margin_std, self.n_samples), MIN_MARGIN
            )
            fcfe_scales = margin_draws / base_margin
        else:
            fcfe_scales = np.ones(self.n_samples)
            confidence *= 0.7
            notes.append("No operating margin — margin dimension not sampled.")

        values: list[float] = []
        for g, r, scale in zip(growth_draws, wacc_draws, fcfe_scales):
            pv = two_stage_pv(fcfe0 * scale, float(g), years, terminal, float(r))
            if pv is not None:
                values.append(pv)

        dropped = self.n_samples - len(values)
        if not values:
            return MonteCarloDistribution(
                confidence=0.0,
                narrative="No converging draws: sampled WACC never cleared terminal growth.",
                notes=notes + ["All draws dropped (wacc <= terminal growth)."],
            )
        if dropped / self.n_samples > MAX_DROPPED_SHARE:
            confidence *= 0.5
            notes.append(
                f"{dropped}/{self.n_samples} draws dropped near the r <= g_terminal "
                "boundary; tails are unreliable."
            )

        arr = np.array(values)
        percentiles = {p: float(np.percentile(arr, p)) for p in PERCENTILES}

        prob_upside: float | None = None
        if m.price is not None and m.price > 0:
            prob_upside = float(np.mean(arr > m.price))
        else:
            confidence *= 0.7
            notes.append("No current price — P(upside) not computable.")

        components = {
            "base_fcfe_per_share": fcfe0,
            "base_growth": growth,
            "base_wacc": wacc,
            "terminal_growth": terminal,
            "growth_std": growth_std,
            "wacc_std": wacc_std,
            "margin_std": margin_std,
            "n_samples": float(self.n_samples),
            "n_effective": float(len(values)),
        }

        narrative = (
            f"Fair value P5 {percentiles[5]:.2f} / P50 {percentiles[50]:.2f} / "
            f"P95 {percentiles[95]:.2f} across {len(values)} draws"
        )
        if prob_upside is not None:
            narrative += f"; P(upside) = {prob_upside:.0%}"
        narrative += "."

        return MonteCarloDistribution(
            percentiles=percentiles,
            mean_fair_value=float(arr.mean()),
            std_fair_value=float(arr.std()),
            prob_upside=prob_upside,
            confidence=confidence,
            components=components,
            narrative=narrative,
            notes=notes,
        )
