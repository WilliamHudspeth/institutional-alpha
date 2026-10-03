"""Unit tests for GUI formatting helpers and value extractors."""

from __future__ import annotations

from types import SimpleNamespace

from iam.ui.gui import (
    _extract_cost_of_equity,
    _extract_discount_rate,
    _extract_pwev_target,
    _fmt_delta,
    _fmt_money,
    _fmt_pct,
)


def test_fmt_money_helper_cases():
    """Test _fmt_money handles None as 'n/a', genuine 0.0, and positive numbers."""
    assert _fmt_money(None) == "n/a"
    assert _fmt_money(0.0) == "$0.00"
    assert _fmt_money(0) == "$0.00"
    assert _fmt_money(123.456) == "$123.46"
    assert _fmt_money(123.4) == "$123.40"


def test_fmt_pct_helper_cases():
    """Test _fmt_pct handles None as 'n/a', unsigned and signed formatting."""
    assert _fmt_pct(None) == "n/a"
    assert _fmt_pct(0.0) == "0.00%"
    assert _fmt_pct(0.08) == "8.00%"
    assert _fmt_pct(0.08, digits=1) == "8.0%"
    assert _fmt_pct(0.08, digits=0) == "8%"
    assert _fmt_pct(0.1234, digits=1, signed=True) == "+12.3%"
    assert _fmt_pct(-0.056, digits=1, signed=True) == "-5.6%"
    assert _fmt_pct(0.0, digits=1, signed=True) == "+0.0%"


def test_fmt_delta_helper_cases():
    """Test _fmt_delta handles None as 'n/a' and signed floating point values."""
    assert _fmt_delta(None) == "n/a"
    assert _fmt_delta(1.234) == "+1.23"
    assert _fmt_delta(-1.234) == "-1.23"
    assert _fmt_delta(0.0) == "+0.00"


def test_extract_pwev_target_when_absent_returns_none():
    """Missing or empty pwev_target must return None, not 0.0."""
    assert _extract_pwev_target(None) is None
    assert _extract_pwev_target(SimpleNamespace()) is None
    assert _extract_pwev_target(SimpleNamespace(intrinsic=None)) is None
    assert _extract_pwev_target(SimpleNamespace(intrinsic=SimpleNamespace(components={}))) is None
    assert (
        _extract_pwev_target(
            SimpleNamespace(intrinsic=SimpleNamespace(components={"other_key": 100.0}))
        )
        is None
    )


def test_extract_pwev_target_when_present_returns_real_value():
    """Real pwev_target (including 0.0) is preserved as float."""
    rep1 = SimpleNamespace(intrinsic=SimpleNamespace(components={"pwev_target": 142.50}))
    assert _extract_pwev_target(rep1) == 142.50

    rep_zero = SimpleNamespace(intrinsic=SimpleNamespace(components={"pwev_target": 0.0}))
    assert _extract_pwev_target(rep_zero) == 0.0


def test_extract_discount_rate_cases():
    """Discount rate extraction falls back to cost_of_equity or returns None."""
    assert _extract_discount_rate(None) is None
    assert _extract_discount_rate(SimpleNamespace(intrinsic=None)) is None
    assert (
        _extract_discount_rate(SimpleNamespace(intrinsic=SimpleNamespace(assumptions={}))) is None
    )
    rep_wacc = SimpleNamespace(intrinsic=SimpleNamespace(assumptions={"discount_rate": 0.095}))
    assert _extract_discount_rate(rep_wacc) == 0.095
    rep_coe = SimpleNamespace(intrinsic=SimpleNamespace(assumptions={"cost_of_equity": 0.105}))
    assert _extract_discount_rate(rep_coe) == 0.105


def test_extract_cost_of_equity_cases():
    """Cost of equity extraction returns float or None."""
    assert _extract_cost_of_equity(None) is None
    assert _extract_cost_of_equity({}) is None
    assert _extract_cost_of_equity({"model_result": None}) is None
    assert _extract_cost_of_equity({"model_result": SimpleNamespace(value=0.091)}) == 0.091
