"""Elasticity scoring: how sharply value re-prices under stress.

STATUS: framework stub. ``ElasticityScorer.profile`` raises
NotImplementedError. The docstring below is the implementation spec;
``tests/test_elasticity.py`` encodes it as assertions.
"""

from __future__ import annotations

from iam.data.security import Security
from iam.elasticity.math_utils import clamp
from iam.elasticity.types import ElasticityProfile
from iam.lenses.base import two_stage_pv

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
        f = security.fundamentals
        q = security.qualitative or {}
        components: dict[str, float] = {}
        notes: list[str] = []
        confidence = 1.0

        # Read WACC, growth, terminal growth from qualitative or use defaults
        wacc = q.get("forecast_discount_rate", DEFAULT_WACC)
        g_high = q.get("forecast_growth", DEFAULT_GROWTH)
        g_terminal = q.get("forecast_terminal_growth", DEFAULT_TERMINAL_GROWTH)
        n = DEFAULT_HIGH_GROWTH_YEARS

        # Growth elasticity from operating leverage
        growth_elasticity = None
        if f.gross_margin is not None and f.operating_margin is not None:
            opex_ratio = clamp(f.gross_margin - f.operating_margin, 0.0, 1.0)
            components["opex_ratio"] = opex_ratio
            growth_elasticity = clamp(1.0 + opex_ratio, 0.0, GROWTH_ELASTICITY_MAX)
        else:
            confidence *= 0.7
            notes.append("Missing gross_margin or operating_margin for growth elasticity.")

        # Rate elasticity from DCF duration numerically
        rate_elasticity = None
        try:
            pv_base = two_stage_pv(1.0, g_high, n, g_terminal, wacc)
            if pv_base is not None and pv_base > 0:
                pv_up = two_stage_pv(1.0, g_high, n, g_terminal, wacc + RATE_PROBE_BPS / 10000.0)
                if pv_up is not None:
                    components["pv_base"] = pv_base
                    components["pv_up"] = pv_up
                    # raw = |pv_up / pv_base - 1| / 0.01 (%-swing per 100bps, normalized)
                    rate_swing_raw = abs(pv_up / pv_base - 1.0) / 0.01
                    components["rate_swing_raw"] = rate_swing_raw

                    # Compute baseline: 9% WACC, 0% growth, 2.5% terminal, 10y
                    baseline_pv = two_stage_pv(1.0, 0.0, n, DEFAULT_TERMINAL_GROWTH, DEFAULT_WACC)
                    baseline_pv_up = two_stage_pv(
                        1.0, 0.0, n, DEFAULT_TERMINAL_GROWTH, DEFAULT_WACC + RATE_PROBE_BPS / 10000.0
                    )
                    if baseline_pv is not None and baseline_pv_up is not None and baseline_pv > 0:
                        baseline_swing = abs(baseline_pv_up / baseline_pv - 1.0) / 0.01
                        components["baseline_swing"] = baseline_swing
                        if baseline_swing > 0:
                            rate_elasticity = clamp(
                                rate_swing_raw / baseline_swing, 0.0, RATE_ELASTICITY_MAX
                            )
                    else:
                        confidence *= 0.7
                        notes.append("Could not compute baseline rate swing.")
                else:
                    confidence *= 0.7
                    notes.append("two_stage_pv failed for rate-shocked scenario.")
            else:
                confidence *= 0.7
                notes.append("two_stage_pv returned None or zero for base case.")
        except Exception as e:
            confidence *= 0.7
            notes.append(f"Rate elasticity computation error: {e}")

        if growth_elasticity is None and rate_elasticity is None:
            confidence = 0.0

        narrative = "Elasticity profile:"
        if growth_elasticity is not None:
            narrative += f" growth={growth_elasticity:.2f}"
        if rate_elasticity is not None:
            if growth_elasticity is not None:
                narrative += ","
            narrative += f" rate={rate_elasticity:.2f}"

        return ElasticityProfile(
            growth_elasticity=growth_elasticity,
            rate_elasticity=rate_elasticity,
            confidence=confidence,
            components=components,
            narrative=narrative,
            notes=notes,
        )
