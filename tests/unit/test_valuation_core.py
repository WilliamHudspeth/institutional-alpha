import pytest
import math
from iam.data.security import Security, Fundamentals, MarketData
from iam.valuation.fcfe_dcf import FCFEDCF, FCFEAssumptions
from iam.valuation.reverse_dcf import reverse_dcf_to_ratio
from iam.valuation.types import Method, ValuationResult, ImpliedExpectations

@pytest.fixture
def base_security():
    sec = Security(ticker="TEST")
    sec.market.price = 100.0
    sec.fundamentals.fcf_ttm = 10.0
    sec.fundamentals.shares_outstanding = 1.0
    return sec

def test_fcfe_dcf_basic(base_security):
    engine = FCFEDCF()
    result = engine.compute(base_security)
    assert result.method == Method.INTRINSIC
    assert result.fair_value_to_price is not None
    assert isinstance(result.fair_value_to_price, float)

def test_fcfe_dcf_insufficient_data():
    sec = Security(ticker="EMPTY")
    engine = FCFEDCF()
    result = engine.compute(sec)
    assert result.confidence == 0.0
    assert "Insufficient data" in result.verdict_text

def test_reverse_dcf_to_ratio_logic():
    # vs_max 1.0 -> 0.0
    implied = ImpliedExpectations(growth_vs_history_max=1.0)
    res = ValuationResult(method=Method.REVERSE_DCF, implied=implied)
    assert reverse_dcf_to_ratio(res) == 0.0

    # vs_max 0.5 -> +1.0
    implied.growth_vs_history_max = 0.5
    assert reverse_dcf_to_ratio(res) == 1.0

    # vs_max 2.0 -> -0.5
    implied.growth_vs_history_max = 2.0
    assert reverse_dcf_to_ratio(res) == -0.5

    # edge case: zero or negative vs_max
    implied.growth_vs_history_max = 0.0
    assert reverse_dcf_to_ratio(res) is None

def test_portfolio_volatility_calculation():
    # This tests the fix applied in Phase 4
    from iam.portfolio.analytics import PortfolioAnalyzer
    from iam.portfolio.types import Portfolio, Position
    
    p = Portfolio(ticker="P", positions=[
        Position(ticker="A", weight=0.5),
        Position(ticker="B", weight=0.5)
    ], total_value=1000)
    
    vol = {"A": 0.2, "B": 0.2}
    # 1. Zero correlation
    corr = {"A": {"B": 0.0}, "B": {"A": 0.0}}
    res = PortfolioAnalyzer.compute_diversification_ratio(p, vol, corr)
    assert math.isclose(res, 0.2 / math.sqrt(0.02), rel_tol=1e-5)

    # 2. Perfect correlation (rho=1.0)
    corr = {"A": {"B": 1.0}, "B": {"A": 1.0}}
    res = PortfolioAnalyzer.compute_diversification_ratio(p, vol, corr)
    assert math.isclose(res, 1.0, rel_tol=1e-5)
