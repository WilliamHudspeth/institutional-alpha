import pandas as pd
import yfinance as yf

from iam.data.providers.yfinance_adapter import YFinanceAdapter
from iam.valuation.adaptive import CompanyProfile
from iam.valuation.expectations_battlefield import build_distributions
from iam.valuation.growth_triangulator import TriangulatedGrowth
from iam.valuation.multiples_regression import predict_multiple


def test_predict_multiple_none_when_input_missing():
    # US PBV requires Beta, gEPS, Payout, ROE
    inputs_without_roe = {
        "Beta": 1.0,
        "gEPS": 0.10,
        "Payout": 0.0,
    }
    assert predict_multiple("US", "PBV", inputs_without_roe) is None

    inputs_with_none_roe = {
        "Beta": 1.0,
        "gEPS": 0.10,
        "Payout": 0.0,
        "ROE": None,
    }
    assert predict_multiple("US", "PBV", inputs_with_none_roe) is None

    inputs_with_roe = {
        "Beta": 1.0,
        "gEPS": 0.10,
        "Payout": 0.0,
        "ROE": 0.15,
    }
    assert predict_multiple("US", "PBV", inputs_with_roe) is not None


def test_yfinance_adapter_empty_payload(monkeypatch):
    adapter = YFinanceAdapter()

    class MockTicker:
        def __init__(self, ticker):
            self.info = {"currentPrice": 100.0}
            self.financials = pd.DataFrame()
            self.cashflow = pd.DataFrame()

    monkeypatch.setattr(yf, "Ticker", MockTicker)

    security = adapter.fetch("DUMMY")
    assert security.qualitative.get("roe") is None
    assert security.qualitative.get("roa") is None
    assert security.qualitative.get("roic") is None
    assert security.qualitative.get("tax_rate") == 0.21
    assert security.qualitative.get("defaulted_inputs") == ["tax_rate"]

    reg_inputs = adapter.build_regression_inputs("DUMMY")
    assert reg_inputs.beta is None
    assert reg_inputs.oper_margin is None
    assert reg_inputs.g_eps is None
    assert reg_inputs.g is None
    assert reg_inputs.dfr is None
    assert reg_inputs.roe is None
    assert reg_inputs.roic is None


def test_yfinance_adapter_roa_not_roic(monkeypatch):
    adapter = YFinanceAdapter()

    class MockTicker:
        def __init__(self, ticker):
            self.info = {
                "currentPrice": 100.0,
                "returnOnAssets": 0.08,
            }
            self.financials = pd.DataFrame()
            self.cashflow = pd.DataFrame()

    monkeypatch.setattr(yf, "Ticker", MockTicker)

    security = adapter.fetch("DUMMY_ROA")
    assert security.qualitative.get("roa") == 0.08
    assert security.qualitative.get("roic") is None

    reg_inputs = adapter.build_regression_inputs("DUMMY_ROA")
    assert reg_inputs.roic is None


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


def test_expectations_battlefield_handles_none_roic():
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
    triangulation = TriangulatedGrowth(blended_growth=0.1, confidence=0.8, margin_adjustment=0.0)
    dist = build_distributions(profile, triangulation)
    assert dist is None
