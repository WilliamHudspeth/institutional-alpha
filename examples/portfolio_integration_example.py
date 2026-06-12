#!/usr/bin/env python3
"""Integration example: Individual securities → Portfolio verdict.

Shows complete workflow:
1. Score individual securities
2. Create portfolio from positions
3. Analyze factor exposures and risk
4. Generate portfolio-level recommendation
5. Display actions and factor positioning
"""

from iam.portfolio import (
    Portfolio,
    PortfolioAnalyzer,
    Position,
    PositionSizer,
    format_concentration_warnings,
)
from iam.portfolio.verdicts import PortfolioVerdictEngine

# Sample securities with verdicts
securities = {
    "MSFT": {"name": "Microsoft", "price": 450, "verdict": "BUY", "conviction": "HIGH"},
    "AAPL": {"name": "Apple", "price": 175, "verdict": "BUY", "conviction": "HIGH"},
    "JPM": {"name": "JPMorgan", "price": 190, "verdict": "HOLD", "conviction": "MODERATE"},
    "BRK.B": {"name": "Berkshire Hathaway", "price": 385, "verdict": "HOLD", "conviction": "MODERATE"},
    "GE": {"name": "General Electric", "price": 105, "verdict": "SELL", "conviction": "MODERATE"},
}

# Factor scores for each security
factor_scores = {
    "MSFT": {"quality": 1.5, "growth": 1.3, "value": -0.2, "momentum": 0.8, "sentiment": 0.9},
    "AAPL": {"quality": 1.4, "growth": 0.9, "value": -0.5, "momentum": 0.6, "sentiment": 1.1},
    "JPM": {"quality": 0.8, "growth": 0.2, "value": 0.7, "momentum": 0.3, "sentiment": 0.4},
    "BRK.B": {"quality": 1.8, "growth": 0.3, "value": 0.6, "momentum": 0.2, "sentiment": 0.5},
    "GE": {"quality": 0.2, "growth": -0.5, "value": 0.4, "momentum": -0.8, "sentiment": -0.3},
}


def main() -> None:
    """Run integration example."""

    print("\n" + "=" * 80)
    print("PORTFOLIO INTEGRATION EXAMPLE")
    print("=" * 80 + "\n")

    # 1. Create positions with conviction-based sizing
    print("1. INDIVIDUAL SECURITIES ANALYSIS")
    print("-" * 80)

    convictions = {ticker: data["verdict"] for ticker, data in securities.items()}

    positions = [
        Position(
            ticker=ticker,
            name=data["name"],
            quantity=100,
            entry_price=data["price"] * 0.95,
            current_price=data["price"],
            weight=0.0,  # Will be calculated
            conviction=data["verdict"],
        )
        for ticker, data in securities.items()
    ]

    # Size positions by conviction
    sized_weights = PositionSizer.size_by_conviction(
        tickers=[p.ticker for p in positions],
        convictions=convictions,
    )

    # Apply weights to positions
    for position in positions:
        position.weight = sized_weights[position.ticker]

    # Create portfolio
    portfolio = Portfolio(positions=positions)

    print(f"Portfolio Value: ${portfolio.total_value:,.0f}")
    print(f"Positions: {len(portfolio.positions)}")
    print("")

    print(f"{'Ticker':<10} {'Verdict':<12} {'Weight':<10} {'Price':<10}")
    print("-" * 50)
    for position in portfolio.sorted_by_weight:
        verdict = securities[position.ticker]["verdict"]
        print(f"{position.ticker:<10} {verdict:<12} {position.weight:>8.1%}  ${position.current_price:>8.2f}")
    print("")

    # 2. Portfolio analytics
    print("\n2. PORTFOLIO RISK ANALYSIS")
    print("-" * 80)

    exposures = PortfolioAnalyzer.compute_factor_exposures(portfolio, factor_scores)

    print(f"Quality Exposure: {exposures.quality_exposure:+.2f}σ")
    print(f"Growth Exposure: {exposures.growth_exposure:+.2f}σ")
    print(f"Value Exposure: {exposures.value_exposure:+.2f}σ")
    print(f"Momentum Exposure: {exposures.momentum_exposure:+.2f}σ")
    print(f"Sentiment Exposure: {exposures.sentiment_exposure:+.2f}σ")
    print("")

    print("Factor Crowding (% of positions exposed):")
    for factor, crowding in sorted(exposures.factor_crowding.items(), key=lambda x: x[1], reverse=True):
        pct = crowding * 100
        level = "HIGH" if pct > 75 else "MODERATE" if pct > 50 else "LOW"
        print(f"  {factor:<15} {pct:>5.0f}%  [{level}]")
    print("")

    # 3. Concentration analysis
    print("\n3. CONCENTRATION & DIVERSIFICATION")
    print("-" * 80)

    metrics_dict = {
        "largest_position": portfolio.largest_position_weight(),
        "concentration": portfolio.concentration_herfindahl(),
        "num_positions": len(portfolio.positions),
        "avg_correlation": 0.35,  # Placeholder
    }

    for line in PortfolioAnalyzer.format_concentration_summary(portfolio):
        print(line)

    print("")

    warnings = format_concentration_warnings(metrics_dict)
    if warnings:
        print("WARNINGS:")
        for warning in warnings:
            print(f"  {warning}")
    else:
        print("✓ No concentration warnings")
    print("")

    # 4. Portfolio-level verdict
    print("\n4. PORTFOLIO-LEVEL RECOMMENDATION")
    print("-" * 80)

    individual_verdicts = {ticker: data["verdict"] for ticker, data in securities.items()}

    portfolio_metrics = {
        "concentration": portfolio.concentration_herfindahl(),
        "largest_position": portfolio.largest_position_weight(),
        "volatility": 0.18,  # Placeholder
        "var": 50000,  # Placeholder
        "avg_correlation": 0.35,
        "drift": 0.01,
    }

    recommendation = PortfolioVerdictEngine.generate_verdict(
        portfolio,
        individual_verdicts,
        portfolio_metrics,
        exposures.net_factor_exposure,
        macro_environment="neutral",
    )

    for line in PortfolioVerdictEngine.format_recommendation(recommendation):
        print(line)

    # 5. Summary
    print("\n5. SUMMARY")
    print("-" * 80)

    print(f"Portfolio Value: ${portfolio.total_value:,.0f}")
    print(f"Expected Return: {recommendation.portfolio_target_return:+.1f}%")
    print(f"Expected Volatility: {recommendation.portfolio_risk:.1f}%")
    print(f"Recommendation: {recommendation.verdict.value}")
    print(f"Conviction: {recommendation.conviction}")

    print("\n" + "=" * 80)
    print("Portfolio integration enables:")
    print("  ✓ Conviction-based position sizing from individual verdicts")
    print("  ✓ Multi-security factor exposure analysis")
    print("  ✓ Risk-aware portfolio construction")
    print("  ✓ Portfolio-level verdicts from individual security analysis")
    print("  ✓ Factor rotation recommendations")
    print("  ✓ Rebalancing and diversification guidance")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
