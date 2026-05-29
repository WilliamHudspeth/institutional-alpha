"""Elasticity scoring: how sharply value re-prices under stress.

STATUS: framework stub. ``ElasticityScorer.profile`` raises
NotImplementedError. The docstring below is the implementation spec;
``tests/test_elasticity.py`` encodes it as assertions.
"""

from __future__ import annotations

from iam.data.security import Security
from iam.elasticity.types import ElasticityProfile

# --- Specification constants (the implementation MUST use these) ------------

# Default discount rate / growth used when the Security doesn't supply them.
DEFAULT_WACC = 0.09
DEFAULT_GROWTH = 0.08
DEFAULT_TERMINAL_GROWTH = 0.025
DEFAULT_HIGH_GROWTH_YEARS = 10

# Probe sizes used to measure elasticity numerically.
GROWTH_PROBE_PCT = 0.05  # measure FCFE response to a 5pp growth drop
RATE_PROBE_BPS = 50.0  # measure value response to a 50bps rate rise

# Output clamps (see ElasticityProfile field docs).
GROWTH_ELASTICITY_MAX = 2.0
RATE_ELASTICITY_MAX = 3.0


class ElasticityScorer:
    """Derive growth- and rate-elasticity from the business's cost and
    cash-flow structure. Pure function of the ``Security`` (no I/O, no
    mutation).

    Inputs are read from ``fundamentals``/``qualitative`` with the defaults
    above when absent: ``forecast_discount_rate`` (WACC), ``forecast_growth``
    (high-growth rate), ``forecast_terminal_growth``.

    Growth elasticity (operating leverage proxy)
    --------------------------------------------
    Operating leverage rises with the share of fixed costs. Approximate the
    fixed-cost share from the gap between gross and operating margin::

        opex_ratio = clamp(gross_margin - operating_margin, 0, 1)

    A business that keeps most of its gross margin as operating profit has low
    fixed-cost drag (elasticity near 1.0, proportional). A business that
    spends most of its gross margin on operating costs has high leverage
    (elasticity > 1.0). Map linearly and clamp::

        growth_elasticity = clamp(1.0 + opex_ratio, 0, GROWTH_ELASTICITY_MAX)

    Requires both ``gross_margin`` and ``operating_margin``; otherwise
    ``growth_elasticity = None`` and confidence is reduced.

    Rate elasticity (cash-flow duration proxy)
    ------------------------------------------
    Measure the actual DCF duration numerically using the shared
    ``two_stage_pv`` helper on a unit FCFE stream (fcfe0 = 1.0):

        pv_base = two_stage_pv(1.0, g, N, g_term, wacc)
        pv_up   = two_stage_pv(1.0, g, N, g_term, wacc + RATE_PROBE_BPS/10000)

        raw = |pv_up / pv_base - 1| / 0.01   # %-swing per 100bps, normalized

    Then express it relative to a *baseline* duration so the score lands on the
    documented 0..3 band. Use the baseline of a 9% WACC / 2.5% terminal /
    no-growth 10y stream computed the same way (call it ``baseline_swing``)::

        rate_elasticity = clamp(raw / baseline_swing, 0, RATE_ELASTICITY_MAX)

    If ``two_stage_pv`` returns None (non-converging assumptions),
    ``rate_elasticity = None`` and confidence is reduced.

    Confidence
    ----------
    Start at 1.0; multiply by 0.7 for each elasticity that could not be
    computed. If neither could be computed, confidence is 0.0.

    Components
    ----------
    Populate ``components`` with the intermediate values that were computed:
    ``opex_ratio``, ``pv_base``, ``pv_up``, ``rate_swing_raw``,
    ``baseline_swing``.
    """

    def profile(self, security: Security) -> ElasticityProfile:
        raise NotImplementedError(
            "ElasticityScorer.profile is a framework stub — implement per the "
            "class docstring spec until tests/test_elasticity.py passes."
        )
