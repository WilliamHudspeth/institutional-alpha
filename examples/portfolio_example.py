#!/usr/bin/env python3
"""Portfolio layer example: composition, analytics, optimization.

Demonstrates:
- Creating and analyzing a portfolio
- Computing factor exposures
- Detecting concentration and crowding
- Position sizing by conviction
- Rebalancing recommendations
"""

from iam.portfolio import (
    Portfolio,
    PortfolioAnalyzer,
    Position,
    PositionSizer,
    Rebalancer,
    format_concentration_warnings,
    format_factor_exposure_heatmap,
    format_holdings_table,
)

# Create sample portfolio with tech and financial holdings
positions = [
    Position(
        ticker="MSFT",
        name="Microsoft",
        quantity=100,
        entry_price=350.0,
        current_price=450.0,
        weight=0.35,
        sector="Technology",
        conviction="HIGH",
    ),
    Position(
        ticker="AAPL",
        name="Apple",
        quantity=50,
        entry_price=120.0,
        current_price=175.0,
        weight=0.25,
        sector="Technology",
        conviction="HIGH",
    ),
    Position(
        ticker="JPM",
        name="JPMorgan Chase",
        quantity=75,
        entry_price=160.0,
        current_price=190.0,
        weight=0.20,
        sector="Financials",
        conviction="MODERATE",
    ),
    Position(
        ticker="BRK.B",
        name="Berkshire Hathaway B",
        quantity=30,
        entry_price=350.0,
        current_price=385.0,
        weight=0.15,
        sector="Industrials",
        conviction="MODERATE",
    ),
    Position(
        ticker="GOOG",
        name="Alphabet",
        quantity=25,
        entry_price=140.0,
        current_price=160.0,
        weight=0.05,
        sector="Technology",
        conviction="LOW",
    ),
]

# Factor scores for each position (z-scores)
factor_scores = {
    "MSFT": {
        "quality": 1.5,
        "growth": 1.3,
        "value": -0.2,
        "momentum": 0.8,
        "sentiment": 0.9,
    },
    "AAPL": {
        "quality": 1.4,
        "growth": 0.9,
        "value": -0.5,
        "momentum": 0.6,
        "sentiment": 1.1,
    },
    "JPM": {
        "quality": 0.8,
        "growth": 0.2,
        "value": 0.7,
        "momentum": 0.3,
        "sentiment": 0.4,
    },
    "BRK.B": {
        "quality": 1.8,
        "growth": 0.3,
        "value": 0.6,
        "momentum": 0.2,
        "sentiment": 0.5,
    },
    "GOOG": {
        "quality": 1.3,
        "growth": 1.5,
        "value": -0.3,
        "momentum": 0.9,
        "sentiment": 0.8,
    },
}

# Historical returns for correlation analysis
position_returns = {
    "MSFT": [0.01, 0.02, -0.01, 0.03, 0.015, 0.02, -0.005, 0.025],
    "AAPL": [0.012, 0.018, -0.008, 0.025, 0.018, 0.022, 0.005, 0.02],
    "JPM": [0.005, 0.01, -0.005, 0.015, 0.008, 0.012, 0.002, 0.01],
    "BRK.B": [0.008, 0.012, 0.002, 0.018, 0.01, 0.015, 0.005, 0.014],
    "GOOG": [0.015, 0.02, -0.01, 0.035, 0.02, 0.025, -0.002, 0.03],
}

position_volatilities = {
    "MSFT": 0.22,
    "AAPL": 0.24,
    "JPM": 0.18,
    "BRK.B": 0.16,
    "GOOG": 0.25,
}


def main() -> None:
    """Run portfolio example."""

    print("\n" + "=" * 80)
    print("PORTFOLIO LAYER EXAMPLE")
    print("=" * 80 + "\n")

    # 1. Create portfolio
    print("1. PORTFOLIO COMPOSITION")
    print("-" * 80)

    portfolio = Portfolio(positions=positions)

    print(f"Total Value: ${portfolio.total_value:,.0f}")
    print(f"Positions: {len(portfolio.positions)}")
    print(f"Gross Exposure: {portfolio.gross_exposure():.1%}")
    print(f"Net Exposure: {portfolio.net_exposure():.1%}")
    print(f"Total P&L: ${portfolio.total_pnl_dollar():,.0f} ({portfolio.total_pnl_pct():+.2f}%)")
    print("")

    # Holdings table
    holdings_data = [p.to_dict() for p in portfolio.sorted_by_weight]
    print(format_holdings_table(holdings_data, width=80))
    print("")

    # 2. Factor exposures
    print("\n2. FACTOR EXPOSURE ANALYSIS")
    print("-" * 80)

    exposures = PortfolioAnalyzer.compute_factor_exposures(portfolio, factor_scores)

    for line in PortfolioAnalyzer.format_exposure_summary(exposures):
        print(line)
    print("")

    # 3. Sector concentration
    print("\n3. SECTOR CONCENTRATION")
    print("-" * 80)

    sector_weights = PortfolioAnalyzer.compute_sector_concentration(portfolio)
    for sector, weight in sorted(sector_weights.items(), key=lambda x: x[1], reverse=True):
        print(f"  {sector:<20} {weight:>6.1%}")
    print("")

    # 4. Concentration metrics
    print("\n4. CONCENTRATION ANALYSIS")
    print("-" * 80)

    for line in PortfolioAnalyzer.format_concentration_summary(portfolio):
        print(line)
    print("")

    # 5. Correlation analysis
    print("\n5. CORRELATION MATRIX")
    print("-" * 80)

    correlation_matrix = PortfolioAnalyzer.compute_correlation_matrix(position_returns)

    # Display correlation matrix
    tickers = [p.ticker for p in portfolio.positions]
    print("  " + "".join(f"{t:>7}" for t in tickers))

    for ticker_i in tickers:
        row = f"{ticker_i:<3}"
        for ticker_j in tickers:
            corr = correlation_matrix.get(ticker_i, {}).get(ticker_j, 0.0)
            row += f"{corr:>7.2f}"
        print(row)

    avg_corr = PortfolioAnalyzer.compute_average_correlation(correlation_matrix)
    print(f"\nAverage Correlation: {avg_corr:.3f}")
    print("")

    # 6. Risk metrics
    print("\n6. RISK ANALYSIS (VaR)")
    print("-" * 80)

    var_95 = PortfolioAnalyzer.compute_portfolio_var(
        portfolio,
        position_volatilities,
        correlation_matrix,
        confidence=0.95,
    )

    print(f"Portfolio Value-at-Risk (95% confidence): ${var_95:,.0f}")
    print(f"Daily VaR (1-day): ${var_95 / math.sqrt(252):,.0f}")
    print("")

    # 7. Position sizing
    print("\n7. POSITION SIZING BY CONVICTION")
    print("-" * 80)

    convictions = {p.ticker: p.conviction for p in portfolio.positions}

    sized_weights = PositionSizer.size_by_conviction(
        tickers=[p.ticker for p in portfolio.positions],
        convictions=convictions,
    )

    print(f"{'Ticker':<8} {'Current':<12} {'Sized':<12} {'Recommendation':<15}")
    print("-" * 50)

    for ticker in sorted(sized_weights.keys()):
        current_weight = (
            portfolio.by_ticker[ticker].weight if ticker in portfolio.by_ticker else 0.0
        )
        sized_weight = sized_weights[ticker]

        if sized_weight > current_weight + 0.02:
            recommendation = "→ INCREASE"
        elif sized_weight < current_weight - 0.02:
            recommendation = "← DECREASE"
        else:
            recommendation = "= HOLD"

        print(f"{ticker:<8} {current_weight:>10.1%}  {sized_weight:>10.1%}  {recommendation:<15}")
    print("")

    # 8. Rebalancing
    print("\n8. REBALANCING ANALYSIS")
    print("-" * 80)

    current_weights = {p.ticker: p.weight for p in portfolio.positions}
    target_weights = PositionSizer.size_by_conviction(
        tickers=[p.ticker for p in portfolio.positions],
        convictions=convictions,
    )

    rebalancing_needed = Rebalancer.rebalancing_required(
        current_weights, target_weights, threshold=0.02
    )

    if rebalancing_needed:
        trades = Rebalancer.compute_trades(current_weights, target_weights, portfolio.total_value)

        for line in Rebalancer.format_rebalancing_summary(
            current_weights, target_weights, trades, portfolio.total_value
        ):
            print(line)
    else:
        print("   Portfolio is well-balanced. No rebalancing required.")
    print("")

    # 9. Concentration warnings
    print("\n9. RISK WARNINGS")
    print("-" * 80)

    metrics_dict = {
        "largest_position": portfolio.largest_position_weight(),
        "concentration": portfolio.concentration_herfindahl(),
        "num_positions": len(portfolio.positions),
    }

    warnings = format_concentration_warnings(metrics_dict)
    if warnings:
        for warning in warnings:
            print(f"  {warning}")
    else:
        print("  ✓ No concentration warnings")
    print("")

    # 10. Factor exposure heatmap
    print("\n10. FACTOR EXPOSURE HEATMAP")
    print("-" * 80)

    print(format_factor_exposure_heatmap(exposures.net_factor_exposure, exposures.factor_crowding))
    print("")

    print("=" * 80)
    print("Portfolio layer enables:")
    print("  ✓ Multi-security composition and weighting")
    print("  ✓ Factor crowding detection")
    print("  ✓ Correlation and diversification analysis")
    print("  ✓ VaR and concentration risk metrics")
    print("  ✓ Intelligent rebalancing")
    print("  ✓ Position sizing by conviction and risk")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    import math

    main()
