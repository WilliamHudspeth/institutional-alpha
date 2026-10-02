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
def test_wacc_provenance_dynamic_wacc_defaults(mock_yfinance, mock_fetch):
    pipeline = ValuationPipeline()
    sec = Security(
        ticker="TEST",
        fundamentals=Fundamentals(
            revenue_ttm=100.0, operating_margin=0.1, interest_expense_ttm=5.0
        ),
        market=MarketData(price=10.0, shares_outstanding=1.0, beta=1.2),
    )
    # Default tax rate used when effective_tax_rate is None
    wacc_info = pipeline._calculate_dynamic_wacc(sec)
    assert wacc_info is not None
    assert wacc_info["defaults_used"] == ["tax: US federal statutory 21% (no effective rate)"]

    # No defaults when effective_tax_rate is provided
    from unittest.mock import MagicMock

    mock_fund = MagicMock()
    mock_fund.revenue_ttm = 100.0
    mock_fund.operating_margin = 0.1
    mock_fund.interest_expense_ttm = 5.0
    mock_fund.effective_tax_rate = 0.25
    mock_fund.total_debt = 0.0
    mock_fund.ebitda_ttm = None
    sec.fundamentals = mock_fund

    wacc_info_explicit = pipeline._calculate_dynamic_wacc(sec)
    assert wacc_info_explicit is not None
    assert wacc_info_explicit["defaults_used"] == []


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

    # Stage 3 (Intrinsic) notes:
    # 1. Never contain "Dynamic WACC applied"
    # 2. Contain "reference only"
    # 3. Contain rf_source and defaults_used
    intrinsic_notes = report.intrinsic.notes
    assert not any("Dynamic WACC applied" in note for note in intrinsic_notes)
    assert any(
        "WACC (reference only; FCFE stages discount at cost of equity):" in note
        for note in intrinsic_notes
    )
    assert any("reference only" in note for note in intrinsic_notes)
    assert any("rating" in note and "rf:" in note for note in intrinsic_notes)
    assert any(
        "tax: US federal statutory 21% (no effective rate)" in note for note in intrinsic_notes
    )

    # Qualitative dict checks:
    # wacc_override removed; wacc_info kept
    assert sec.qualitative is not None
    assert "wacc_override" not in sec.qualitative
    assert "wacc_info" in sec.qualitative
    assert sec.qualitative["wacc_info"]["defaults_used"] == [
        "tax: US federal statutory 21% (no effective rate)"
    ]


@patch("iam.data.markets.fetch_live_quote", return_value=None)
@patch(
    "iam.data.providers.yfinance_adapter.build_regression_inputs",
    side_effect=Exception("No network"),
)
def test_wacc_provenance_run_caller_supplied_macro(mock_yfinance, mock_fetch):
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
        qualitative={
            "risk_free_rate": 0.045,
            "equity_risk_premium": 0.055,
        },
    )

    pipeline.run(sec)

    assert sec.qualitative is not None
    assert sec.qualitative["risk_free_rate"] == 0.045
    assert sec.qualitative["equity_risk_premium"] == 0.055
    assert sec.qualitative["rf_source"] == "caller-supplied"
    assert sec.qualitative["erp_source"] == "caller-supplied"


@patch("iam.data.markets.fetch_live_quote", return_value=None)
@patch(
    "iam.data.providers.yfinance_adapter.build_regression_inputs",
    side_effect=Exception("No network"),
)
def test_wacc_provenance_run_caller_supplied_with_custom_sources(mock_yfinance, mock_fetch):
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
        qualitative={
            "risk_free_rate": 0.045,
            "rf_source": "custom Treasury 10Y",
            "equity_risk_premium": 0.055,
            "erp_source": "custom survey",
        },
    )

    pipeline.run(sec)

    assert sec.qualitative is not None
    assert sec.qualitative["risk_free_rate"] == 0.045
    assert sec.qualitative["equity_risk_premium"] == 0.055
    assert sec.qualitative["rf_source"] == "custom Treasury 10Y"
    assert sec.qualitative["erp_source"] == "custom survey"


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
