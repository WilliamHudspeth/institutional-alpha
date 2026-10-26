"""Precision-weighted combination, empirical-Bayes shrinkage, and fade path construction.

Combines company-specific growth estimates using inverse-variance weights and
shrinks the composite toward a size-stratified base rate in proportion to
estimation noise (Chan, Karceski and Lakonishok, "The Level and Persistence of
Growth Rates", JF 2003; Mauboussin, Callahan and Majd, *The Base Rate Book*,
2016; Damodaran, *Investment Valuation* ch. 11).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

from iam.data.security import Security
from iam.growth.base_rates import base_rate
from iam.growth.estimators import (
    analyst_forward,
    fundamental,
    historical_operating_income,
    historical_revenue,
    market_implied,
    normalised_fundamental,
)
from iam.growth.types import GrowthAssignment, GrowthEstimate, GrowthProfile

DCF_YEARS = 10
NEAR_TERM_YEARS = 5
DCF_BOUNDS: tuple[float, float] = (-0.10, 0.35)
ANALYST_HORIZON_PENALTY = 2.0
# Which inputs set the DCF rate: "blend" (all, precision-weighted), "replace_fundamental"
# (normalised fundamental instead of the single-year one) or "anchor" (normalised alone,
# shrunk to the base rate; falls back to the blend when it is not usable). Point-in-time
# EDGAR backtest (80 large caps x 9 dates, 2012-2025, realised 3y revenue growth):
# replace_fundamental MAE 6.84 pts / rank corr 0.34, the previous blend 6.97 / 0.33,
# anchor 7.52 / 0.11, so the normalised estimate informs the blend but does not replace it.
DCF_GROWTH_MODE = "replace_fundamental"


def fade_path(
    near_term: float,
    terminal: float,
    years: int = DCF_YEARS,
    hold: int = NEAR_TERM_YEARS,
) -> tuple[float, ...]:
    """Build a multi-year growth path holding near_term for `hold` years then fading linearly."""
    path: list[float] = []
    fade_len = max(1, years - hold)
    for t in range(1, years + 1):
        if t <= hold:
            path.append(float(near_term))
        else:
            step = float(near_term) + (float(terminal) - float(near_term)) * (t - hold) / fade_len
            path.append(step)
    return tuple(path)


def _combine(
    estimates: dict[str, GrowthEstimate],
    methods: Sequence[str],
    base: GrowthEstimate,
    valuation: str,
    inflate: dict[str, float] | None = None,
) -> GrowthAssignment:
    """Precision-weight usable estimates and shrink toward `base`."""
    inflate_map = inflate or {}
    usable: list[tuple[str, float, float]] = []
    for m_name in methods:
        est = estimates.get(m_name)
        if est is not None and est.ok and est.std_error is not None and est.std_error > 0:
            se = est.std_error * inflate_map.get(m_name, 1.0)
            usable.append((m_name, float(est.value), se))  # type: ignore[arg-type]

    assert base.value is not None and base.std_error is not None
    tau = base.std_error

    if not usable:
        return GrowthAssignment(
            valuation=valuation,
            value=base.value,
            std_error=tau,
            sources=(),
            weights={},
            shrinkage_weight=0.0,
            base_rate=base.value,
            notes=("No usable company estimates; falling back to size base rate.",),
        )

    precisions = {name: 1.0 / (se**2) for name, _, se in usable}
    total_prec = sum(precisions.values())
    weights = {name: prec / total_prec for name, prec in precisions.items()}
    m_val = sum(weights[name] * val for name, val, _ in usable)
    var_m = 1.0 / total_prec

    tau_sq = tau**2
    k = tau_sq / (tau_sq + var_m)
    shrunk_value = k * m_val + (1.0 - k) * base.value
    post_se = math.sqrt(1.0 / (1.0 / var_m + 1.0 / tau_sq))

    return GrowthAssignment(
        valuation=valuation,
        value=shrunk_value,
        std_error=post_se,
        sources=tuple(name for name, _, _ in usable),
        weights=weights,
        shrinkage_weight=k,
        base_rate=base.value,
        notes=(),
    )


def build_growth_profile(
    security: Security,
    market_implied_value: float | None = None,
    engine_result: Any = None,
    risk_free_rate: float | None = None,
    terminal_growth: float = 0.025,
    compute_implied: bool = False,
) -> GrowthProfile:
    """Compute all estimators and assemble the valuation-specific GrowthProfile."""
    f = security.fundamentals
    rev = f.revenue_ttm
    if rev is None and f.revenue_history:
        rev = f.revenue_history[0]

    base = base_rate(rev)
    est_rev = historical_revenue(security)
    est_op = historical_operating_income(security)
    est_fund = fundamental(security)
    est_norm_fund = normalised_fundamental(security)
    est_analyst = analyst_forward(security)

    if market_implied_value is not None or engine_result is not None or compute_implied:
        est_implied = market_implied(
            security, engine_result=engine_result, value=market_implied_value
        )
    else:
        est_implied = GrowthEstimate(
            method="market_implied",
            value=None,
            std_error=None,
            horizon_years=10,
            confidence=0.0,
            reason="Market-implied growth not requested.",
        )

    estimates: dict[str, GrowthEstimate] = {
        "base_rate": base,
        "historical_revenue": est_rev,
        "historical_operating_income": est_op,
        "fundamental": est_fund,
        "normalised_fundamental": est_norm_fund,
        "analyst_forward": est_analyst,
        "market_implied": est_implied,
    }

    inflate = {"analyst_forward": ANALYST_HORIZON_PENALTY}

    blend_methods: tuple[str, ...] = (
        "historical_revenue",
        "historical_operating_income",
        "fundamental",
        "normalised_fundamental",
        "analyst_forward",
    )
    if DCF_GROWTH_MODE == "replace_fundamental":
        dcf_methods: tuple[str, ...] = (
            "historical_revenue",
            "historical_operating_income",
            "normalised_fundamental",
            "analyst_forward",
        )
    elif DCF_GROWTH_MODE == "anchor":
        dcf_methods = ("normalised_fundamental",) if est_norm_fund.ok else blend_methods
    else:
        dcf_methods = blend_methods

    dcf_raw = _combine(
        estimates,
        dcf_methods,
        base,
        valuation="dcf",
        inflate=inflate,
    )
    assert dcf_raw.value is not None
    lo, hi = DCF_BOUNDS
    if dcf_raw.value < lo or dcf_raw.value > hi:
        clamped_val = max(lo, min(hi, dcf_raw.value))
        dcf = GrowthAssignment(
            valuation=dcf_raw.valuation,
            value=clamped_val,
            std_error=dcf_raw.std_error,
            sources=dcf_raw.sources,
            weights=dcf_raw.weights,
            shrinkage_weight=dcf_raw.shrinkage_weight,
            base_rate=dcf_raw.base_rate,
            notes=dcf_raw.notes + (f"DCF growth clamped to [{lo:.2f}, {hi:.2f}].",),
        )
    else:
        dcf = dcf_raw

    relative_revenue = _combine(
        estimates,
        ("historical_revenue", "fundamental"),
        base,
        valuation="relative_revenue",
    )

    relative_eps = _combine(
        estimates,
        ("historical_operating_income", "analyst_forward"),
        base,
        valuation="relative_eps",
        inflate=inflate,
    )

    if est_implied.ok and est_implied.value is not None:
        expectations = GrowthAssignment(
            valuation="expectations",
            value=est_implied.value,
            std_error=None,
            sources=("market_implied",),
            weights={"market_implied": 1.0},
            shrinkage_weight=None,
            base_rate=base.value,
        )
        assert dcf.value is not None and base.value is not None and base.std_error is not None
        expectations_gap: float | None = est_implied.value - dcf.value
        z = (est_implied.value - base.value) / base.std_error
        expectations_percentile: float | None = 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
    else:
        expectations = GrowthAssignment(
            valuation="expectations",
            value=None,
            std_error=None,
            sources=(),
            weights={},
            shrinkage_weight=None,
            base_rate=base.value,
        )
        expectations_gap = None
        expectations_percentile = None

    terminal = (
        min(terminal_growth, risk_free_rate) if risk_free_rate is not None else terminal_growth
    )
    assert dcf.value is not None
    path = fade_path(dcf.value, terminal, years=DCF_YEARS, hold=NEAR_TERM_YEARS)

    return GrowthProfile(
        estimates=estimates,
        dcf=dcf,
        dcf_path=path,
        terminal_growth=terminal,
        relative_revenue=relative_revenue,
        relative_eps=relative_eps,
        expectations=expectations,
        expectations_gap=expectations_gap,
        expectations_percentile=expectations_percentile,
    )
