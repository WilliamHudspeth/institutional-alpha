"""Tests for factor implementations and un-stubbing."""

from iam import Fundamentals, MarketData, Security, score


def test_expectations_difficulty_roic_signal_fires():
    """Verify that providing implied and peak ROIC un-stubs the ROIC difficulty score."""
    sec = Security(
        ticker="ROIC_TEST",
        fundamentals=Fundamentals(
            fcf_ttm=100.0,
            shares_outstanding=10.0,
            revenue_history=[110, 105, 100],
            operating_margin=0.10,
            operating_margin_history=[0.10, 0.09, 0.08],
        ),
        market=MarketData(price=50.0),
        qualitative={
            # The market demands 25% ROIC, but the industry has never broken 15%
            "implied_roic": 0.25,
            "industry_peak_roic": 0.15,
        },
    )

    result = score(sec)
    ex = result.factor_breakdown["expectations_difficulty"]

    # The stub should now be active
    assert "roic_difficulty" in ex.components

    # 25% implied vs 15% peak is heroic. The score should be highly negative.
    assert ex.components["roic_difficulty"] < 0


def test_working_capital_quality_signal_fires():
    """Verify that providing change_in_working_capital computes working capital quality score."""
    sec = Security(
        ticker="WC_TEST",
        fundamentals=Fundamentals(
            revenue_ttm=1000.0,
            change_in_working_capital=-100.0,  # Draining WC by 10% of revenue
        ),
    )
    result = score(sec)
    eq = result.factor_breakdown["earnings_quality"]
    assert "wc_quality" in eq.components
    assert eq.components["wc_quality"] == -1.0
