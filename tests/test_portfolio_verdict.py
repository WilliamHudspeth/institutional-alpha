import pytest
from iam.portfolio.verdicts import PortfolioVerdictEngine, PortfolioVerdict
from iam.portfolio.types import Portfolio, Position

def test_portfolio_verdict_shadowing_bug():
    # Setup mock portfolio
    portfolio = Portfolio(
        positions=[
            Position(
                ticker="AAPL",
                name="Apple",
                quantity=10,
                entry_price=100.0,
                current_price=150.0,
                weight=0.6,
            ),
            Position(
                ticker="MSFT",
                name="Microsoft",
                quantity=10,
                entry_price=100.0,
                current_price=150.0,
                weight=0.4,
            ),
        ]
    )
    individual_verdicts = {
        "AAPL": "BUY",
        "MSFT": "BUY"
    }
    metrics = {"concentration": 0.3}
    exposures = {"quality": 0.8}
    
    # Generate verdict
    recommendation = PortfolioVerdictEngine.generate_verdict(
        portfolio=portfolio,
        individual_verdicts=individual_verdicts,
        portfolio_metrics=metrics,
        factor_exposures=exposures
    )
    
    # The shadowing bug causes recommendation.verdict to be the string "BUY" instead of PortfolioVerdict enum
    assert isinstance(recommendation.verdict, PortfolioVerdict)
    assert recommendation.verdict == PortfolioVerdict.OVERWEIGHT
