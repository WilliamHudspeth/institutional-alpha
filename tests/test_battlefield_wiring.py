"""Stage 4b wiring: the pipeline's Battlefield must come from real engine outputs.

Regression cover for the old hand-built scenario distributions (fixed
20/60/20 weights, invented 8% growth / 15% ROE / 20% margin defaults, and a
market margin copied from the intrinsic one).
"""

from __future__ import annotations

import math
import types
from unittest.mock import patch

import pytest

from iam import Fundamentals, MarketData, Security, ValuationPipeline
from iam.pipeline.battlefield import (
    BattlefieldAttribution,
    DriverContribution,
    ParamVector,
    attribute_disagreement,
    fcfe_value_fn,
)
from iam.ui import research_panels as rp
from iam.valuation.reverse_dcf import _present_value_two_stage


def _security(**qual) -> Security:
    return Security(
        ticker="TEST",
        fundamentals=Fundamentals(
            fcf_ttm=1000,
            net_income_ttm=1000,
            shares_outstanding=100,
            revenue_history=[1200, 1100, 1000, 900, 800],
        ),
        market=MarketData(price=180),
        qualitative={"forecast_growth": 0.06, **qual},
    )


@pytest.fixture(scope="module")
def offline():
    """Keep these tests hermetic: no live rate or peer-regression fetches."""
    with (
        patch("iam.data.markets.fetch_live_quote", return_value=None),
        patch(
            "iam.data.providers.yfinance_adapter.build_regression_inputs",
            side_effect=RuntimeError("offline"),
        ),
    ):
        yield


@pytest.fixture(scope="module")
def report(offline):
    return ValuationPipeline().run(_security())


def test_pipeline_produces_attribution(report):
    bf = report.battlefield
    assert isinstance(bf, BattlefieldAttribution)
    assert bf.key_parameter == "growth"
    assert bf.contributions, "expected per-parameter contributions"


def test_market_implied_value_reproduces_price(report):
    # The reverse DCF solved for the growth that justifies the price, so
    # valuing the market's own assumption set must give back the price.
    assert report.battlefield.target_value == pytest.approx(180.0, rel=0.01)


def test_intrinsic_side_uses_supplied_assumptions(report):
    growth = report.battlefield.contribution("growth")
    assert growth is not None
    assert growth.value_intrinsic == pytest.approx(0.06)
    assert growth.value_market == pytest.approx(
        report.market_implied_engine.implied.implied_revenue_growth
    )


def test_mismatch_score_is_the_value_gap(report):
    bf = report.battlefield
    assert bf.value_gap_pct == pytest.approx(bf.total_gap / bf.base_value)
    assert bf.mismatch_score == pytest.approx(min(100.0, abs(bf.value_gap_pct) * 100))


def test_no_battlefield_without_fcfe_inputs(offline):
    sec = Security(ticker="THIN", market=MarketData(price=50))
    assert ValuationPipeline().run(sec).battlefield is None


def test_fcfe_value_fn_matches_engine_maths():
    defaults = ParamVector(growth=0.07, terminal_growth=0.025, discount_rate=0.09, roe=0.18)
    fn = fcfe_value_fn(5.0, 10, defaults)
    expected = _present_value_two_stage(
        base_ni=5.0, g_high=0.07, n=10, g_terminal=0.025, r=0.09, roe=0.18
    )
    assert fn(defaults) == pytest.approx(expected)
    # A missing parameter falls back to the intrinsic vector, not a constant.
    assert fn(ParamVector(growth=0.07)) == pytest.approx(expected)


def test_non_convergent_values_are_not_attributed():
    defaults = ParamVector(growth=0.05, terminal_growth=0.03, discount_rate=0.09, roe=0.15)
    fn = fcfe_value_fn(5.0, 10, defaults)
    market = ParamVector(growth=0.05, terminal_growth=0.03, discount_rate=0.02, roe=0.15)
    bf = attribute_disagreement(defaults, market, fn)
    assert bf.key_disagreement.startswith("UNDETERMINED")
    assert bf.mismatch_score is None


def test_summary_lists_each_contribution(report):
    text = report.battlefield.summary()
    assert "key disagreement" in text
    for c in report.battlefield.contributions:
        assert f"{c.value_intrinsic * 100:6.2f}%" in text


# --------------------------------------------------------------------------- #
# TUI panels: draw only engine numbers
# --------------------------------------------------------------------------- #
class _RecordingCanvas:
    def __init__(self) -> None:
        self.text: list[str] = []

    def put(self, r, c, text, style="") -> None:
        self.text.append(str(text))

    def hline(self, *a, **k) -> None:
        pass

    def joined(self) -> str:
        return "\n".join(self.text)


def _sec_with(report_ns):
    return types.SimpleNamespace(pipeline_result=report_ns)


def test_battlefield_panel_shows_real_contributions():
    bf = BattlefieldAttribution(
        key_disagreement="GROWTH expectations",
        key_parameter="growth",
        base_value=100.0,
        target_value=130.0,
        total_gap=30.0,
        contributions=[DriverContribution("growth", 0.05, 0.11, 128.0, 28.0, 1.0)],
    )
    cv = _RecordingCanvas()
    rp.ExpectationsBattlefieldPanel().render(
        cv, 0, 20, 0, 100, _sec_with(types.SimpleNamespace(battlefield=bf))
    )
    out = cv.joined()
    assert "GROWTH expectations" in out
    assert "5.00%" in out and "11.00%" in out
    assert "+30.0%" in out


@pytest.mark.parametrize(
    "mkt_g, expected",
    [(0.20, "MORE growth than our bull"), (0.01, "LESS growth than our bear"), (0.06, "inside")],
)
def test_growth_panel_places_market_against_our_scenarios(mkt_g, expected):
    rpt = types.SimpleNamespace(
        market_implied_engine=types.SimpleNamespace(
            implied=types.SimpleNamespace(implied_revenue_growth=mkt_g)
        ),
        intrinsic=types.SimpleNamespace(
            components={
                "scenarios": {
                    "Bear Case": {"prob": 0.2, "g": 0.03},
                    "Base Case": {"prob": 0.6, "g": 0.05},
                    "Bull Case": {"prob": 0.2, "g": 0.08},
                }
            }
        ),
    )
    cv = _RecordingCanvas()
    rp.ReverseDCFDistributionPanel().render(cv, 0, 20, 0, 100, _sec_with(rpt))
    assert expected in cv.joined()


def test_growth_panel_needs_real_inputs():
    cv = _RecordingCanvas()
    rp.ReverseDCFDistributionPanel().render(
        cv, 0, 20, 0, 100, _sec_with(types.SimpleNamespace(market_implied_engine=None))
    )
    assert "Needs reverse-DCF" in cv.joined()
    assert not any(ch.isdigit() for ch in cv.joined())


def test_value_gap_none_when_base_unusable():
    bf = BattlefieldAttribution("x", None, float("nan"), 10.0, 0.0)
    assert bf.value_gap_pct is None
    assert math.isnan(bf.base_value)
