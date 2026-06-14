"""Tests for the IC term-structure and country-risk engines."""

from __future__ import annotations

import math

import numpy as np
import pytest

from iam.backtest.term_structure import (
    HorizonIC,
    build_term_structure,
    fit_marginal_decay,
)
from iam.valuation.country_risk import (
    DEFAULT_MATURE_ERP,
    blended_erp,
    country_risk,
)


# --------------------------------------------------------------------------- #
# IC term structure
# --------------------------------------------------------------------------- #
def _series(mean: float, std: float, n: int = 60, seed: int = 0):
    rng = np.random.default_rng(seed)
    return list(rng.normal(mean, std, n))


def test_velocity_prefers_shorter_horizon_when_ic_merely_accumulates():
    # Raw IC rises with horizon, but proportionally to ~sqrt(h): velocity flat-ish,
    # short horizon should win on a tie-break toward less capital lock-up.
    ic = {
        21: _series(0.030, 0.05, seed=1),
        63: _series(0.052, 0.05, seed=2),  # ~0.030 * sqrt(63/21)
        126: _series(0.073, 0.05, seed=3),  # ~0.030 * sqrt(126/21)
        252: _series(0.104, 0.05, seed=4),
    }
    ts = build_term_structure(ic)
    # Peak raw IC is the longest horizon...
    assert ts.peak_ic_horizon_days == 252
    # ...but velocity should not blindly pick the longest.
    assert ts.optimal_horizon_days <= 252
    assert ts.recommended_rebalance_days >= 1


def test_decay_detected_when_marginal_ic_shrinks():
    # IC accumulates but each extra block adds less -> positive, decaying marginal.
    ic = {
        21: _series(0.040, 0.04, seed=11),
        63: _series(0.070, 0.04, seed=12),  # +0.030 over 42d
        126: _series(0.085, 0.04, seed=13),  # +0.015 over 63d  (smaller per-day)
        252: _series(0.092, 0.04, seed=14),  # +0.007 over 126d (smaller still)
    }
    ts = build_term_structure(ic)
    assert ts.half_life_days is not None
    assert ts.half_life_days > 0
    assert ts.decay_tau_days is not None


def test_no_decay_reported_when_marginal_flat_or_growing():
    horizons = [
        HorizonIC(21, 0.02, 0.04, 60),
        HorizonIC(63, 0.04, 0.04, 60),  # +0.02 over 42d -> 0.476/kd
        HorizonIC(126, 0.10, 0.04, 60),  # +0.06 over 63d -> 0.952/kd (accelerating)
    ]
    tau, hl, monotonic = fit_marginal_decay(horizons)
    assert hl is None  # accelerating marginal => no half-life


def test_horizon_weights_track_information_ratio():
    # Same mean IC, very different consistency -> the steadier horizon gets more.
    ic = {
        63: _series(0.05, 0.02, n=120, seed=21),  # high IR
        126: _series(0.05, 0.20, n=120, seed=22),  # low IR
    }
    ts = build_term_structure(ic)
    w = ts.horizon_weights()
    assert w[63] > w[126]
    assert math.isclose(sum(w.values()), 1.0, rel_tol=1e-9)


def test_empty_input_raises():
    with pytest.raises(ValueError):
        build_term_structure({})


# --------------------------------------------------------------------------- #
# Country risk
# --------------------------------------------------------------------------- #
def test_mature_market_has_zero_crp():
    cr = country_risk("US")
    assert cr.default_spread == 0.0
    assert cr.crp == 0.0
    assert math.isclose(cr.erp, DEFAULT_MATURE_ERP)


def test_riskier_country_has_higher_erp():
    us = country_risk("US")
    br = country_risk("BR")  # Ba2
    assert br.crp > us.crp
    assert br.erp > us.erp


def test_rel_vol_scales_crp_linearly():
    a = country_risk("BR", rel_vol=1.0)
    b = country_risk("BR", rel_vol=2.0)
    assert math.isclose(b.crp, 2.0 * a.crp, rel_tol=1e-9)


def test_cds_override_bypasses_rating_table():
    cr = country_risk("US", default_spread_override=0.02, rel_vol=1.5)
    assert math.isclose(cr.crp, 0.03, rel_tol=1e-9)
    assert math.isclose(cr.erp, DEFAULT_MATURE_ERP + 0.03, rel_tol=1e-9)


def test_blended_erp_between_pure_country_endpoints():
    pure_us = country_risk("US").erp
    pure_cn = country_risk("CN").erp
    mix = blended_erp({"US": 0.6, "CN": 0.4})
    assert pure_us <= mix.erp <= pure_cn or pure_cn <= mix.erp <= pure_us
    assert math.isclose(sum(w for _, w, _ in mix.components), 1.0, rel_tol=1e-9)


def test_blended_erp_normalises_unnormalised_weights():
    a = blended_erp({"US": 60, "BR": 40})
    b = blended_erp({"US": 0.6, "BR": 0.4})
    assert math.isclose(a.erp, b.erp, rel_tol=1e-12)


def test_region_aliases_resolve():
    # APAC -> cn, EMEA -> de; should not fall back to the unknown-country default.
    out = blended_erp({"north_america": 0.5, "apac": 0.3, "emea": 0.2})
    isos = {iso for iso, _, _ in out.components}
    assert {"us", "cn", "de"} == isos


def test_lambda_overrides_revenue_weights():
    rev = {"US": 0.9, "AR": 0.1}  # mostly US revenue
    # But operating exposure to Argentina is much larger:
    lam = {"us": 0.4, "ar": 0.6}
    base = blended_erp(rev)
    skewed = blended_erp(rev, lambdas=lam)
    assert skewed.erp > base.erp  # heavier Argentina weight lifts ERP


def test_empty_revenue_mix_defaults_to_mature():
    out = blended_erp({})
    assert math.isclose(out.erp, DEFAULT_MATURE_ERP)
