"""The TI-89 map and the DCF terrain must plot real engine values."""

from __future__ import annotations

import types
from unittest.mock import patch

import pytest

from iam import Fundamentals, MarketData, Security, ValuationPipeline
from iam.ui.ti89_graph import render_ti89_map, ti89_figure
from iam.valuation.reverse_dcf import _present_value_two_stage
from iam.valuation.sensitivity import DCFValuationSurface
from iam.valuation.value_grid import build_value_grid


def _security(**fund) -> Security:
    base = dict(
        fcf_ttm=1000,
        net_income_ttm=1000,
        shares_outstanding=100,
        revenue_history=[5000, 4500, 4000, 3500, 3000],  # most-recent-first
    )
    base.update(fund)
    return Security(
        ticker="TEST",
        fundamentals=Fundamentals(**base),
        market=MarketData(price=180),
        qualitative={"forecast_growth": 0.06},
    )


@pytest.fixture(scope="module")
def report():
    with (
        patch("iam.data.markets.fetch_live_quote", return_value=None),
        patch(
            "iam.data.providers.yfinance_adapter.build_regression_inputs",
            side_effect=RuntimeError("offline"),
        ),
    ):
        return ValuationPipeline().run(_security())


def test_grid_values_are_the_fcfe_maths(report):
    grid = build_value_grid(report)
    assert grid is not None
    a = report.intrinsic.assumptions
    base_ni = report.intrinsic.components["base_ni_per_share"]
    i, j = 2, 3
    expected = _present_value_two_stage(
        base_ni=base_ni,
        g_high=grid.growths[j],
        n=int(a["high_growth_years"]),
        g_terminal=a["terminal_growth"],
        r=grid.rates[i],
        roe=a["roe"],
    )
    assert grid.values[i][j] == pytest.approx(expected)


def test_grid_base_matches_intrinsic_base_case(report):
    grid = build_value_grid(report)
    base_case = report.intrinsic.components["scenarios"]["Base Case"]["target"]
    assert grid.base[2] == pytest.approx(base_case)


def test_grid_recovers_price_and_market_point(report):
    grid = build_value_grid(report)
    assert grid.price == pytest.approx(180.0)
    implied = report.market_implied_engine.implied
    assert grid.market == pytest.approx(
        (implied.implied_revenue_growth, implied.discount_rate_assumed)
    )
    # The market point lies inside the plotted axes.
    assert grid.growths[0] <= grid.market[0] <= grid.growths[-1]


def test_no_grid_without_fcfe_inputs():
    empty = types.SimpleNamespace(intrinsic=types.SimpleNamespace(components={}, assumptions={}))
    assert build_value_grid(empty) is None
    assert build_value_grid(types.SimpleNamespace()) is None


def test_ti89_map_marks_base_and_market(report):
    lines = render_ti89_map(build_value_grid(report))
    text = "\n".join(lines)
    assert "[B]" in text and "[M]" in text
    assert len(lines) == 1 + len(build_value_grid(report).rates)


def test_ti89_figure_uses_grid(report):
    grid = build_value_grid(report)
    fig = ti89_figure(grid)
    if fig is None:
        pytest.skip("plotly not installed")
    assert list(fig.data[0].z[0]) == grid.values[0]


def test_dcf_surface_uses_latest_revenue_and_real_margin():
    sec = _security()
    surf = DCFValuationSurface(sec)
    assert surf.revenue_ttm == 5000  # most recent, not the oldest year
    assert surf.base_m == pytest.approx(1000 / 5000)


def test_dcf_surface_omits_marker_without_margin():
    sec = _security(net_income_ttm=None)
    surf = DCFValuationSurface(sec)
    surf.generate_z_grid()
    assert surf.base_m is None
    assert surf.get_markers() == []


def test_dcf_surface_takes_pipeline_assumptions(report):
    surf = DCFValuationSurface(_security(), report=report)
    a = report.intrinsic.assumptions
    assert surf.r == pytest.approx(a["discount_rate"])
    assert surf.roe == pytest.approx(a["roe"])


def test_no_grid_without_high_growth_years():
    """The horizon is an engine input like the others: no silent 10-year fallback (AGY A1)."""
    a = {"high_growth": 0.1, "discount_rate": 0.09, "terminal_growth": 0.025, "roe": 0.15}
    intrinsic = types.SimpleNamespace(components={"base_ni_per_share": 5.0}, assumptions=a)
    assert build_value_grid(types.SimpleNamespace(intrinsic=intrinsic)) is None
