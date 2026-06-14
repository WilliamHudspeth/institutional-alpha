# Portfolio Layer Guide

The portfolio layer transforms the alpha terminal from single-security analysis into institutional multi-holding portfolio management. This guide covers composition, analytics, optimization, and verdicts.

## Overview

The portfolio layer provides:

1. **Portfolio Composition**: Multi-security positions with weighting and P&L tracking
2. **Risk Analytics**: Factor exposures, correlations, VaR, concentration metrics
3. **Position Sizing**: Conviction-based, risk-based, return-based sizing methods
4. **Rebalancing**: Drift detection and trade recommendations
5. **Portfolio Verdicts**: Synthesis of individual securities into portfolio-level guidance
6. **Factor Positioning**: Balance and rotate factor exposures dynamically

## Core Data Structures

### Position

A single holding in the portfolio:

```python
from iam.portfolio import Position

position = Position(
    ticker="MSFT",
    name="Microsoft",
    quantity=100,
    entry_price=350.0,
    current_price=450.0,
    weight=0.35,  # 35% of portfolio
    sector="Technology",
    conviction="HIGH"
)

# Properties
print(position.market_value)  # 45,000
print(position.pnl_dollar)    # 10,000
print(position.pnl_pct)       # 28.6%
```

### Portfolio

A collection of positions:

```python
from iam.portfolio import Portfolio

portfolio = Portfolio(positions=[position1, position2, ...])

# Properties
print(portfolio.total_value)      # Sum of all positions
print(portfolio.gross_exposure()) # 1.0 (100% long)
print(portfolio.net_exposure())   # 1.0 (fully invested)
print(portfolio.total_pnl_pct())  # Overall P&L %
print(portfolio.concentration_herfindahl())  # 0-1 concentration
```

### ExposureProfile

Net factor exposures and crowding metrics:

```python
from iam.portfolio import PortfolioAnalyzer

exposures = PortfolioAnalyzer.compute_factor_exposures(
    portfolio,
    position_factor_scores  # dict[ticker: dict[factor: z-score]]
)

print(exposures.quality_exposure)    # +1.2σ (long quality)
print(exposures.growth_exposure)     # +0.8σ (long growth)
print(exposures.factor_crowding)     # {quality: 0.8, growth: 0.6, ...}
```

## Analytics

### Factor Exposures

Compute net factor exposures across the portfolio:

```python
from iam.portfolio import PortfolioAnalyzer

# Factor scores for each position (z-scores)
factor_scores = {
    "MSFT": {"quality": 1.5, "growth": 1.2, "momentum": 0.8},
    "AAPL": {"quality": 1.4, "growth": 0.9, "momentum": 0.6},
    "JPM": {"quality": 0.8, "growth": 0.2, "momentum": 0.3},
}

exposures = PortfolioAnalyzer.compute_factor_exposures(portfolio, factor_scores)

print(f"Quality: {exposures.quality_exposure:+.2f}σ")  # Net quality exposure
print(f"Crowding: {exposures.factor_crowding['quality']:.0%}")  # % of positions long quality
```

**Interpretation:**
- `+1.2σ` = Portfolio is 1.2 standard deviations long quality (bullish quality)
- `0.8` crowding = 80% of positions are long quality (potential crowding risk)

### Correlation Analysis

Understand position diversification:

```python
# Historical returns for each position
position_returns = {
    "MSFT": [0.01, 0.02, -0.01, 0.03, ...],
    "AAPL": [0.012, 0.018, -0.008, ...],
}

correlation_matrix = PortfolioAnalyzer.compute_correlation_matrix(position_returns)

print(correlation_matrix["MSFT"]["AAPL"])  # 0.65 correlation
avg_corr = PortfolioAnalyzer.compute_average_correlation(correlation_matrix)
print(f"Average correlation: {avg_corr:.2f}")  # 0.55
```

**Interpretation:**
- Correlation `0.0` = uncorrelated (good diversification)
- Correlation `1.0` = perfectly correlated (no diversification benefit)
- Correlation `< 0.3` = low correlation (excellent diversification)

### Value at Risk

Estimate maximum potential loss at confidence level:

```python
position_volatilities = {
    "MSFT": 0.22,  # 22% annual volatility
    "AAPL": 0.24,
    "JPM": 0.18,
}

var_95 = PortfolioAnalyzer.compute_portfolio_var(
    portfolio,
    position_volatilities,
    correlation_matrix,
    confidence=0.95  # 95% confidence
)

print(f"95% VaR: ${var_95:,.0f}")  # Max loss at 95% confidence
print(f"Daily VaR: ${var_95 / math.sqrt(252):,.0f}")  # 1-day VaR
```

**Interpretation:**
- VaR of $100k at 95% confidence = 95% probability of losing ≤ $100k
- 5% chance of losing > $100k in one period

### Concentration Metrics

Monitor portfolio concentration:

```python
print(f"Largest position: {portfolio.largest_position_weight():.1%}")
print(f"Herfindahl index: {portfolio.concentration_herfindahl():.2f}")
```

**Interpretation:**
- Herfindahl index:
  - 0.05 = perfectly diversified (20 equal positions)
  - 0.20 = moderate concentration (5 equal positions)
  - 1.00 = fully concentrated (one position)

## Position Sizing

### Size by Conviction

Allocate more to high-conviction positions:

```python
from iam.portfolio import PositionSizer, OptimizationConstraints

tickers = ["MSFT", "AAPL", "JPM", "GE"]
convictions = {
    "MSFT": "HIGH",
    "AAPL": "HIGH",
    "JPM": "MODERATE",
    "GE": "LOW",
}

constraints = OptimizationConstraints(
    min_position_size=0.01,   # 1% minimum
    max_position_size=0.25,   # 25% maximum
    target_gross_exposure=1.0,  # 100% invested
)

weights = PositionSizer.size_by_conviction(
    tickers, convictions, constraints
)

# Result: {"MSFT": 0.30, "AAPL": 0.28, "JPM": 0.20, "GE": 0.22}
```

### Size by Risk (Inverse Volatility)

Volatility-weighted portfolio (lower volatility = larger position):

```python
volatilities = {
    "MSFT": 0.22,
    "AAPL": 0.24,
    "JPM": 0.18,  # Lowest volatility
    "GE": 0.28,   # Highest volatility
}

weights = PositionSizer.size_by_risk(volatilities)

# Result: JPM gets largest allocation (lowest volatility)
#         GE gets smallest allocation (highest volatility)
```

### Size by Expected Return

Return-weighted portfolio (higher expected return = larger position):

```python
expected_returns = {
    "MSFT": 0.15,  # 15% expected return
    "AAPL": 0.12,
    "JPM": 0.08,
    "GE": 0.05,
}

weights = PositionSizer.size_by_return(expected_returns)

# Result: MSFT gets largest allocation (highest expected return)
```

## Rebalancing

### Detect Drift

Check if portfolio has drifted from targets:

```python
from iam.portfolio import Rebalancer

current_weights = {"MSFT": 0.35, "AAPL": 0.25, "JPM": 0.20}
target_weights = {"MSFT": 0.30, "AAPL": 0.30, "JPM": 0.20}

needs_rebalancing = Rebalancer.rebalancing_required(
    current_weights,
    target_weights,
    threshold=0.02  # Rebalance if drift > 2%
)
```

### Compute Trades

Calculate specific rebalancing trades:

```python
trades = Rebalancer.compute_trades(
    current_weights,
    target_weights,
    portfolio_value=1_000_000
)

# Result: {"MSFT": -50000, "AAPL": +50000, "JPM": 0}
# Sell $50k MSFT, buy $50k AAPL
```

## Portfolio Verdicts

Synthesize individual security analysis into portfolio-level guidance:

```python
from iam.portfolio import PortfolioVerdictEngine

individual_verdicts = {
    "MSFT": "BUY",
    "AAPL": "BUY",
    "JPM": "HOLD",
    "GE": "SELL",
}

recommendation = PortfolioVerdictEngine.generate_verdict(
    portfolio,
    individual_verdicts,
    portfolio_metrics={
        "concentration": 0.15,
        "largest_position": 0.35,
        "volatility": 0.18,
    },
    factor_exposures={
        "quality": 1.2,
        "growth": 0.8,
        "value": -0.2,
    },
    macro_environment="neutral"
)

print(recommendation.verdict)  # OVERWEIGHT, NEUTRAL, UNDERWEIGHT, RESTRUCTURE
print(recommendation.conviction)  # HIGH, MODERATE, LOW
print(recommendation.portfolio_target_return)  # Expected return %
print(recommendation.portfolio_risk)  # Expected volatility %
print(recommendation.actions)  # Specific recommendations
```

**Verdict Logic:**
- **OVERWEIGHT**: >60% BUY ratings and favorable macro
- **UNDERWEIGHT**: >50% SELL ratings
- **RESTRUCTURE**: High concentration (>25% Herfindahl)
- **NEUTRAL**: Balanced signal, no strong positioning
- **Conviction**: Based on conviction dispersion and risk metrics

## Usage Examples

### Example 1: Monitor Concentration

```python
from iam.portfolio import format_concentration_warnings

metrics = {
    "largest_position": portfolio.largest_position_weight(),
    "concentration": portfolio.concentration_herfindahl(),
    "num_positions": len(portfolio.positions),
}

warnings = format_concentration_warnings(metrics)
for warning in warnings:
    print(warning)
```

### Example 2: Rebalance by Conviction

```python
# Get new conviction-based weights
new_convictions = {"MSFT": "MODERATE", "AAPL": "HIGH", ...}  # Updated from research

new_weights = PositionSizer.size_by_conviction(
    tickers=[p.ticker for p in portfolio.positions],
    convictions=new_convictions,
)

# Check drift and compute trades
current_weights = {p.ticker: p.weight for p in portfolio.positions}

if Rebalancer.rebalancing_required(current_weights, new_weights, threshold=0.02):
    trades = Rebalancer.compute_trades(current_weights, new_weights, portfolio.total_value)
    
    for ticker, trade in trades.items():
        direction = "BUY" if trade > 0 else "SELL"
        print(f"{direction} ${abs(trade):,.0f} of {ticker}")
```

### Example 3: Analyze Factor Crowding

```python
# Detect if portfolio is crowded in any factor
crowded_factors = []
for factor, crowding_pct in exposures.factor_crowding.items():
    if crowding_pct > 0.75:  # >75% of positions exposed
        crowded_factors.append(factor)

if crowded_factors:
    print(f"Portfolio is crowded in: {crowded_factors}")
    print("Consider diversifying or rebalancing to other factors")
```

### Example 4: Portfolio Verdict to Actions

```python
recommendation = PortfolioVerdictEngine.generate_verdict(...)

print(f"Verdict: {recommendation.verdict.value}")
print(f"Conviction: {recommendation.conviction}")
print(f"Expected Return: {recommendation.portfolio_target_return:+.1f}%")

print("\nRecommended Actions:")
for action in recommendation.actions:
    print(f"  • {action}")

print("\nFactor Positioning:")
for factor, positioning in recommendation.factor_recommendations.items():
    print(f"  {factor}: {positioning}")
```

## Integration with Security Analysis

The portfolio layer connects individual security verdicts to portfolio construction:

```
Individual Securities:
  MSFT: verdict=BUY, conviction=HIGH
  AAPL: verdict=BUY, conviction=HIGH
  JPM: verdict=HOLD, conviction=MODERATE
  GE: verdict=SELL, conviction=MODERATE

        ↓ (Conviction-based sizing)

Position Weights:
  MSFT: 30% (HIGH conviction → larger)
  AAPL: 28% (HIGH conviction → larger)
  JPM: 20% (MODERATE conviction → medium)
  GE: 22% (constraint floor, would be lower if allowed)

        ↓ (Factor analysis)

Portfolio Exposures:
  Quality: +1.2σ (all long quality)
  Growth: +0.8σ (bullish growth)
  Momentum: +0.5σ (slightly bullish)

        ↓ (Risk assessment)

Portfolio Risk:
  VaR 95%: $150k
  Concentration: 0.15 (moderate)
  Largest position: 30% (acceptable)
  Avg correlation: 0.35 (good diversification)

        ↓ (Verdict synthesis)

Portfolio Recommendation:
  Verdict: OVERWEIGHT
  Conviction: HIGH
  Target Return: +12.5%
  Risk: 18% volatility
  
  Actions:
  - Increase gross exposure from 100% to 110%
  - Shift toward BUY-rated positions
  - Monitor for crowding in quality factor
```

## Best Practices

1. **Regular Rebalancing**: Check drift monthly, rebalance quarterly
2. **Factor Monitoring**: Watch for crowding in factors >75% exposure
3. **Concentration Limits**: Keep largest position <20%, Herfindahl <0.20
4. **Diversification**: Target 8+ positions with avg correlation <0.4
5. **Conviction Alignment**: Position sizes should reflect conviction levels
6. **Risk Budgeting**: VaR should not exceed risk tolerance
7. **Macro Overlay**: Adjust positioning based on macro environment

## Examples

Complete working examples are in:
- `examples/portfolio_example.py` - Portfolio analytics deep dive
- `examples/portfolio_integration_example.py` - End-to-end workflow

Run them:
```bash
python examples/portfolio_example.py
python examples/portfolio_integration_example.py
```

## Next Steps

Future enhancements:
- **Portfolio Optimization**: Mean-variance efficient frontier
- **Options Analytics**: Volatility surface and Greeks
- **Smart Rebalancing**: Tax-aware rebalancing logic
- **Scenario Analysis**: Stress test portfolio under market conditions
- **Trade Execution**: Integration with order management systems
