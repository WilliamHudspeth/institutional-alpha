from iam.data.providers.yfinance_adapter import YFinanceAdapter
from iam.valuation.adaptive import CompanyProfile
from iam.valuation.expectations_battlefield import build_distributions
from iam.valuation.growth_triangulator import TriangulatedGrowth


def test_yfinance_adapter_empty_payload(monkeypatch):
    adapter = YFinanceAdapter()

    # Mock yfinance to return empty info
    class MockTicker:
        def __init__(self, ticker):
            import pandas as pd
            self.info = {"currentPrice": 100.0}
            self.financials = pd.DataFrame()
            self.cashflow = pd.DataFrame()

    import yfinance as yf

    monkeypatch.setattr(yf, "Ticker", MockTicker)

    security = adapter.fetch("DUMMY")
    assert security.qualitative.get("roe") is None
    assert security.qualitative.get("roic") is None
    assert security.qualitative.get("tax_rate") == 0.21


def test_company_profile_defaults():
    profile = CompanyProfile(
        ticker="DUMMY",
        implied_growth=0.1,
        hist_eps_growth=0.1,
        hist_volatility=0.1,
        sector_growth=0.1,
        adjacent_growth=0.1,
        op_margin=0.1,
        sector_margin=0.1,
    )
    assert profile.roe is None
    assert profile.roic is None


def test_expectations_battlefield_handles_none():
    profile = CompanyProfile(
        ticker="DUMMY",
        implied_growth=0.1,
        hist_eps_growth=0.1,
        hist_volatility=0.1,
        sector_growth=0.1,
        adjacent_growth=0.1,
        op_margin=0.1,
        sector_margin=0.1,
    )
    triangulation = TriangulatedGrowth(
        blended_growth=0.1, confidence=0.8, margin_adjustment=0.0
    )
    int_dist, mkt_dist = build_distributions(profile, triangulation)
    # the fallback in the consumer should set roic to 0.10 (or whatever default is used)
    assert mkt_dist.scenarios[1].roic == 0.10
