from unittest.mock import patch

from iam.data.damodaran import DamodaranProvider
from iam.data.security import Fundamentals, MarketData, Security
from iam.pipeline.orchestrator import ValuationPipeline


@patch("iam.data.markets.fetch_live_quote", return_value=None)
@patch(
    "iam.data.providers.yfinance_adapter.build_regression_inputs",
    side_effect=Exception("No network"),
)
def test_wacc_provenance_offline_rf(mock_yfinance, mock_fetch):
    macro = DamodaranProvider.get_macro_state()
    assert "baseline" in macro.rf_source
    assert "Damodaran implied ERP baseline" in macro.erp_source


@patch("iam.data.markets.fetch_live_quote", return_value=None)
@patch(
    "iam.data.providers.yfinance_adapter.build_regression_inputs",
    side_effect=Exception("No network"),
)
def test_wacc_provenance_dynamic_wacc(mock_yfinance, mock_fetch):
    pipeline = ValuationPipeline()
    sec = Security(
        ticker="TEST",
        fundamentals=Fundamentals(
            revenue_ttm=100.0, operating_margin=0.1, interest_expense_ttm=5.0
        ),
        market=MarketData(price=10.0, shares_outstanding=1.0),
    )
    # Missing beta
    wacc_info = pipeline._calculate_dynamic_wacc(sec)
    assert wacc_info is None

    sec.market.beta = 1.5
    # Missing EBIT (remove revenue_ttm)
    sec.fundamentals.revenue_ttm = None
    wacc_info = pipeline._calculate_dynamic_wacc(sec)
    assert wacc_info is None

    sec.fundamentals.revenue_ttm = 100.0
    # Missing interest expense
    sec.fundamentals.interest_expense_ttm = None
    wacc_info = pipeline._calculate_dynamic_wacc(sec)
    assert wacc_info is None

    sec.fundamentals.interest_expense_ttm = 5.0
    wacc_info = pipeline._calculate_dynamic_wacc(sec)
    assert wacc_info is not None
    assert "baseline" in wacc_info["rf_source"]

    macro = DamodaranProvider.get_macro_state()
    expected_ke = macro.risk_free_rate + 1.5 * macro.implied_erp
    assert wacc_info["cost_of_equity"] == expected_ke
    assert expected_ke != 0.09  # never yields a 9% ke for a beta of 1.5


@patch("iam.data.markets.fetch_live_quote", return_value=None)
@patch(
    "iam.data.providers.yfinance_adapter.build_regression_inputs",
    side_effect=Exception("No network"),
)
def test_wacc_provenance_run(mock_yfinance, mock_fetch):
    pipeline = ValuationPipeline()
    sec = Security(
        ticker="TEST",
        fundamentals=Fundamentals(
            revenue_ttm=100.0,
            operating_margin=0.1,
            interest_expense_ttm=5.0,
            net_income_ttm=10.0,
            shares_outstanding=1.0,
        ),
        market=MarketData(price=10.0, shares_outstanding=1.0, market_cap=10.0, beta=1.5),
    )
    original_r = pipeline.market_implied_engine.r

    report = pipeline.run(sec)

    # run() does not set market_implied_engine.r to the WACC
    assert pipeline.market_implied_engine.r == original_r

    # Stage 1 notes show the CAPM line when beta is present
    stage_1_notes = report.market_implied_engine.notes
    assert any("CAPM discount rate" in note for note in stage_1_notes)


@patch("iam.data.markets.fetch_live_quote", return_value=None)
@patch(
    "iam.data.providers.yfinance_adapter.build_regression_inputs",
    side_effect=Exception("No network"),
)
def test_wacc_provenance_run_no_beta(mock_yfinance, mock_fetch):
    pipeline = ValuationPipeline()
    sec = Security(
        ticker="TEST",
        fundamentals=Fundamentals(
            revenue_ttm=100.0,
            operating_margin=0.1,
            interest_expense_ttm=5.0,
            net_income_ttm=10.0,
            shares_outstanding=1.0,
        ),
        market=MarketData(price=10.0, shares_outstanding=1.0, market_cap=10.0, beta=None),
    )

    report = pipeline.run(sec)
    stage_1_notes = report.market_implied_engine.notes
    assert any("CAPM skipped for lack of beta." in note for note in stage_1_notes)
