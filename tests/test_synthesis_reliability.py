"""Tests for reliability-weighted lens synthesis.

The contract: adding the reliability hook must not change any existing output
unless a genuinely *non-uniform* calibration is supplied. These tests pin that
guarantee so the feature can ship dormant and be activated later with
confidence.
"""

from __future__ import annotations

import math

from iam.lenses.base import LensResult
from iam.lenses.synthesis import (
    _DEFAULT_RELIABILITY,
    _LENS_TO_SIGNAL,
    synthesize_lenses,
)


def _lens(name: str, low: float, high: float, move: float, conf: float) -> LensResult:
    return LensResult(
        lens_name=name,
        fair_value_low=low,
        fair_value_high=high,
        implied_move_pct=move,
        confidence=conf,
        narrative="test",
    )


def _sample() -> list[LensResult]:
    return [
        _lens("rate_sensitive", 80.0, 100.0, -0.05, 0.5),
        _lens("platform_compounder", 90.0, 110.0, 0.12, 0.8),
        _lens("business_reality", 95.0, 120.0, 0.20, 0.6),
    ]


def test_none_reliabilities_is_identical_to_legacy() -> None:
    """Passing no reliabilities reproduces confidence-only weighting exactly."""
    lenses = _sample()
    base = synthesize_lenses(lenses)
    explicit_none = synthesize_lenses(lenses, reliabilities=None)
    assert base.weighted_implied_move_pct == explicit_none.weighted_implied_move_pct
    assert base.weighted_fair_value_low == explicit_none.weighted_fair_value_low
    assert base.weighted_fair_value_high == explicit_none.weighted_fair_value_high


def test_uniform_reliabilities_is_a_noop() -> None:
    """A constant reliability across all signals cancels in the normalised mean."""
    lenses = _sample()
    base = synthesize_lenses(lenses)
    # Every signal that any sample lens maps to, set to the same constant.
    signals = {_LENS_TO_SIGNAL.get(l.lens_name, l.lens_name) for l in lenses}
    uniform = {s: 0.70 for s in signals}
    out = synthesize_lenses(lenses, reliabilities=uniform)
    assert math.isclose(
        base.weighted_implied_move_pct,
        out.weighted_implied_move_pct,
        rel_tol=1e-12,
        abs_tol=1e-12,
    )


def test_skewed_reliabilities_shift_toward_higher_weighted_signal() -> None:
    """Up-weighting the bullish lens's signal must raise the blended move."""
    lenses = _sample()
    base = synthesize_lenses(lenses).weighted_implied_move_pct
    # platform_compounder (move +0.12) maps to fcfe_upside; boost it, cut the
    # bearish rate_sensitive (cost_of_equity).
    skew = {"fcfe_upside": 0.95, "cost_of_equity": 0.50, "relative_value": 0.70}
    boosted = synthesize_lenses(lenses, reliabilities=skew).weighted_implied_move_pct
    assert boosted > base


def test_unmapped_lens_falls_back_to_default() -> None:
    """A lens with no signal mapping uses _DEFAULT_RELIABILITY, not a crash."""
    lenses = [
        _lens("totally_new_lens", 100.0, 120.0, 0.10, 0.7),
        _lens("platform_compounder", 90.0, 110.0, 0.12, 0.8),
    ]
    # Calibration omits the unmapped lens's (defaulted) signal entirely.
    rel = {"fcfe_upside": 0.9}
    out = synthesize_lenses(lenses, reliabilities=rel)
    # Recompute by hand: unmapped -> default reliability; mapped -> 0.9.
    w_new = 0.7 * _DEFAULT_RELIABILITY
    w_plat = 0.8 * 0.9
    expected = (0.10 * w_new + 0.12 * w_plat) / (w_new + w_plat)
    assert math.isclose(out.weighted_implied_move_pct, expected, rel_tol=1e-12)


def test_empty_and_zero_weight_inputs_are_safe() -> None:
    """No valid lenses -> None outputs, regardless of reliabilities."""
    diagnostic = _lens("expectations_difficulty", 0.0, 0.0, 0.0, 0.0)
    diagnostic.fair_value_low = None
    diagnostic.implied_move_pct = None
    out = synthesize_lenses([diagnostic], reliabilities={"cost_of_equity": 0.9})
    assert out.weighted_implied_move_pct is None
