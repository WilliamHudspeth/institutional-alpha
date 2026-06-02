# Integration Guide: End-to-End Workflow

This guide shows how to combine all terminal layers into a cohesive workflow:

1. **Individual Security Analysis** (existing pipeline)
2. **Bayesian Thesis Management** (evidence → posterior probabilities)
3. **Portfolio Composition** (conviction-based position sizing)
4. **Data Visualization** (sparklines + metrics)
5. **Real-time Updates** (async data layer + event bus)

## Scenario: Morning Portfolio Review

### Step 1: Start with Existing Verdicts

Your existing pipeline produces individual security analysis:

```python
from iam.integration.orchestrator import run_full_pipeline

result = run_full_pipeline("MSFT")
# Returns: {
#     "verdict": "BUY",
#     "pwev": 520.0,
#     "scenarios": [{"name": "Bull", "prob": 0.20, ...}],
#     "signals": {...}
# }
```

### Step 2: Load into Thesis System

Convert individual verdicts into formal Bayesian theses:

```python
from iam.thesis.bayesian.thesis import ThesisBuilder
from iam.thesis.bayesian.evidence import Evidence, ScenarioLikelihood

# Create thesis from pipeline output
thesis = (ThesisBuilder("MSFT", "Microsoft", current_price=450.0)
    .add_scenario(
        name="Bull Case",
        description="AI monetization success",
        probability=0.20,
        target_price=550.0,
        expected_return=0.22,
        thesis_statement="Cloud + AI platform leverage"
    )
    .add_scenario(
        name="Base Case",
        description="Steady growth",
        probability=0.60,
        target_price=520.0,
        expected_return=0.15,
        thesis_statement="10% growth, multiple maintenance"
    )
    .add_scenario(
        name="Bear Case",
        description="Valuation pressure",
        probability=0.20,
        target_price=420.0,
        expected_return=-0.07,
        thesis_statement="Recession, margin compression"
    )
    .set_conviction("MODERATE")
    .build()
)
```

### Step 3: Incorporate Earnings Evidence

New data arrives (earnings beat). Update thesis using Bayesian theorem:

```python
from iam.thesis.bayesian.updater import BayesianUpdater

earnings_evidence = Evidence(
    type="EARNINGS_BEAT",
    description="EPS beat 8%, guidance up 5%",
    likelihoods={
        "Bear Case": ScenarioLikelihood(0.15),
        "Base Case": ScenarioLikelihood(0.60),
        "Bull Case": ScenarioLikelihood(0.95),
    },
    reliability=0.95  # High confidence in official earnings
)

priors = [ScenarioPrior(s.name, s.probability) for s in thesis.scenarios]
posteriors = BayesianUpdater.update(priors, earnings_evidence)

# Result: Bull probability increased from 20% → 35%
```

### Step 4: Create Portfolio Positions

Use updated conviction to size positions:

```python
from iam.portfolio import Position, Portfolio, PositionSizer

# Determine conviction from Bayesian update
conviction_level = "HIGH" if bull_prob > 0.35 else "MODERATE"

position = Position(
    ticker="MSFT",
    name="Microsoft",
    quantity=100,
    entry_price=450.0,
    current_price=475.0,  # Up on earnings
    weight=0.30,  # Will be set by portfolio
    conviction=conviction_level
)

portfolio = Portfolio(positions=[position, ...])
```

### Step 5: Analyze Portfolio Risk

Check factor exposures and concentration:

```python
from iam.portfolio import PortfolioAnalyzer

exposures = PortfolioAnalyzer.compute_factor_exposures(
    portfolio,
    factor_scores
)

# Check for crowding
if exposures.factor_crowding["quality"] > 0.75:
    print("⚠ Crowded in quality factor - diversify")

# Compute risk
var_95 = PortfolioAnalyzer.compute_portfolio_var(
    portfolio,
    position_volatilities,
    correlation_matrix,
    confidence=0.95
)

print(f"Daily VaR: ${var_95 / math.sqrt(252):,.0f}")
```

### Step 6: Render Terminal with Visualization

Display complete analysis with sparklines:

```python
from iam.ui.modern_terminal import ModernTerminal
from iam.ui.sparklines import Sparkline, format_price_movement
from iam.portfolio.verdicts import PortfolioVerdictEngine

terminal = ModernTerminal()

# Load security state from thesis
terminal.load_security("MSFT", {
    "verdict": "BUY",
    "pwev": 520.0,
    "scenarios": [s.to_dict() for s in thesis.scenarios],
    ...
})

# Render with sparklines
print(terminal.render())

# Add market data visualization
prices = [450, 452, 455, 453, 458, 465, 472, 475]
print(f"\nPrice Movement: {Sparkline.line(prices)}")
print(f"Intraday: {MiniChart.intraday(450, 476, 448, 475)}")

# Portfolio verdict
recommendation = PortfolioVerdictEngine.generate_verdict(
    portfolio,
    individual_verdicts={"MSFT": "BUY", ...},
    portfolio_metrics={...},
    factor_exposures=exposures.net_factor_exposure,
)

for line in PortfolioVerdictEngine.format_recommendation(recommendation):
    print(line)
```

### Step 7: Set Up Real-time Monitoring

Use event bus for live updates:

```python
from iam.ui.events import EventType, subscribe_to_event
from iam.data.async_loader import get_async_loader

loader = get_async_loader()

def on_price_update(event):
    new_price = event.payload["price"]
    # Recompute implied move
    # Update sparkline
    # Emit to UI

subscribe_to_event(EventType.PRICE_TICK, on_price_update)

# Load data asynchronously
loader.load_security_async(
    "MSFT",
    lambda ticker: fetch_market_data(ticker),
    on_complete=lambda ticker, data: update_terminal(ticker, data)
)

# Terminal stays responsive while data loads
```

## Complete Workflow Diagram

```
┌─────────────────────────────────────────────────────┐
│ Individual Security Analysis (Existing Pipeline)    │
│ DCF, Multiples, Scenarios, Factor Scoring           │
│ Output: verdict, pwev, signals                      │
└──────────────────┬──────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────────────────┐
│ Bayesian Thesis Formation                          │
│ Create formal thesis with bear/base/bull scenarios  │
│ Set initial convictions (20%, 60%, 20%)             │
└──────────────────┬──────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────────────────┐
│ Evidence Incorporation (Real-time Updates)          │
│ • Earnings beat → Bull +15%, Base -10%              │
│ • Macro shock → Bear +20%, Bull -15%                │
│ • Analyst upgrade → Bull +10%, Bear -5%             │
│ Bayesian: P(H|E) = P(E|H) * P(H) / P(E)            │
└──────────────────┬──────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────────────────┐
│ Portfolio Position Sizing                           │
│ Updated conviction (Bull now 45%) → larger position │
│ Size by: conviction, risk, expected return          │
└──────────────────┬──────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────────────────┐
│ Multi-Security Risk Analysis                        │
│ • Factor exposures (quality, growth, momentum)      │
│ • Correlations & diversification                    │
│ • VaR, concentration, crowding                      │
└──────────────────┬──────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────────────────┐
│ Portfolio-Level Verdict                             │
│ Synthesize individual verdicts → OVERWEIGHT/HOLD    │
│ Generate actionable recommendations                 │
└──────────────────┬──────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────────────────┐
│ Terminal Rendering + Visualization                  │
│ • Panel composition (header, decision, scenarios)   │
│ • Sparklines (price, volatility, trends)            │
│ • Heatmaps (factors, concentration)                 │
│ • Real-time updates via event bus                   │
└──────────────────┬──────────────────────────────────┘
                   ↓
         ┌─────────────────┐
         │  Display to User │
         │  Institutional   │
         │  Terminal UI     │
         └─────────────────┘
```

## Code Example: Complete Workflow

```python
#!/usr/bin/env python3
"""Complete institutional terminal workflow."""

from datetime import datetime
from iam.integration.orchestrator import run_full_pipeline
from iam.thesis.bayesian.thesis import ThesisBuilder
from iam.thesis.bayesian.evidence import Evidence, ScenarioLikelihood
from iam.thesis.bayesian.updater import BayesianUpdater
from iam.thesis.bayesian.priors import ScenarioPrior
from iam.portfolio import Position, Portfolio, PortfolioAnalyzer
from iam.ui.modern_terminal import ModernTerminal
from iam.ui.sparklines import Sparkline, MiniChart
from iam.portfolio.verdicts import PortfolioVerdictEngine

def main():
    ticker = "MSFT"
    
    # 1. Get individual security analysis
    analysis = run_full_pipeline(ticker)
    
    # 2. Create thesis from analysis
    thesis = ThesisBuilder(ticker, "Microsoft", analysis["price"]).build()
    
    # 3. Update with earnings evidence
    earnings_evidence = Evidence(
        type="EARNINGS_BEAT",
        description=f"EPS beat by {analysis.get('eps_beat_pct', 5)}%",
        likelihoods={
            "Bear Case": ScenarioLikelihood(0.2),
            "Base Case": ScenarioLikelihood(0.6),
            "Bull Case": ScenarioLikelihood(0.95),
        },
        reliability=0.95
    )
    
    priors = [ScenarioPrior(s.name, s.probability) for s in thesis.scenarios]
    posteriors = BayesianUpdater.update(priors, earnings_evidence)
    
    # 4. Create position with updated conviction
    new_bull_prob = max(p.probability for p in posteriors if "Bull" in p.label)
    conviction = "HIGH" if new_bull_prob > 0.40 else "MODERATE"
    
    position = Position(
        ticker=ticker,
        name="Microsoft",
        quantity=100,
        entry_price=analysis["price"] * 0.95,
        current_price=analysis["price"],
        weight=0.30,
        conviction=conviction
    )
    
    portfolio = Portfolio(positions=[position])
    
    # 5. Analyze portfolio
    exposures = PortfolioAnalyzer.compute_factor_exposures(
        portfolio, {"MSFT": analysis["factors"]}
    )
    
    # 6. Generate portfolio verdict
    recommendation = PortfolioVerdictEngine.generate_verdict(
        portfolio,
        {"MSFT": analysis["verdict"]},
        {"concentration": 0.30, "volatility": 0.18},
        exposures.net_factor_exposure
    )
    
    # 7. Render terminal
    terminal = ModernTerminal()
    terminal.load_security(ticker, analysis)
    print(terminal.render())
    
    # 8. Add visualizations
    prices = analysis.get("price_history", [])
    if prices:
        print(f"\nPrice Trend: {Sparkline.line(prices)}")
        print(f"Direction: {Sparkline.trend(prices)}")
    
    # 9. Display recommendation
    for line in PortfolioVerdictEngine.format_recommendation(recommendation):
        print(line)

if __name__ == "__main__":
    main()
```

## Running the Full Stack

```bash
# Individual components
python examples/modern_terminal_example.py      # Panel architecture
python examples/portfolio_example.py             # Portfolio analytics
python examples/bayesian_thesis_example.py       # Thesis updating
python examples/sparklines_example.py            # Data visualization
python examples/portfolio_integration_example.py # Integration

# Main terminal (to be implemented)
python main.py
```

## Key Integration Points

### 1. State Management
- `TerminalUIState`: Holds active security, UI mode, errors
- `SecurityState`: Immutable security data
- `Portfolio`: Multi-security composition
- `InvestmentThesis`: Bayesian scenario tracking

### 2. Event Bus
- Subscribe to `SECURITY_LOADED`, `PIPELINE_COMPLETE`, `PRICE_TICK`
- Panels react to events without tight coupling
- Async tasks emit completion events

### 3. Async Layer
- Load data in background via `AsyncDataLoader`
- Render immediately, update progressively
- Events trigger UI updates

### 4. Configuration
- Factor weights, pipeline params, async settings
- Load from YAML or environment
- No hardcoded values

### 5. Logging
- Component-specific loggers for debugging
- Performance metrics for optimization
- Structured logs for analysis

## Next Steps

1. **Integrate with Main.py**
   - Replace monolithic terminal with panel-based rendering
   - Add async data loading from market sources
   - Wire event bus for live updates

2. **Add Market Data Integration**
   - Real-time price feeds
   - Earnings calendar events
   - News sentiment feeds

3. **Enhance Bayesian Engine**
   - Track evidence history
   - Compute confidence evolution
   - Generate thesis evolution report

4. **Portfolio Optimization**
   - Mean-variance efficient frontier
   - Risk budgeting
   - Constraint satisfaction

5. **Research Synthesis**
   - Generate investment memos
   - Summarize thesis and risks
   - Quantified scenarios to narrative

## Architecture Benefits

- **Modularity**: Each layer can be developed/tested independently
- **Scalability**: Async + event-driven design prevents bottlenecks
- **Clarity**: Clear separation of concerns
- **Testability**: Immutable state + pure functions
- **Extensibility**: Easy to add new panels, evidence types, visualizations
- **Observability**: Structured logging + event history

This integration enables an institutional-grade research platform with:
- Formal Bayesian reasoning
- Multi-security portfolio management
- Real-time responsive UI
- Professional data visualization
- Audit trail of decisions
