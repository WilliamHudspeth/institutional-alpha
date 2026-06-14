# Institutional Alpha Terminal - System Guide

A production-grade quantitative research terminal combining individual security analysis, Bayesian thesis management, multi-security portfolio optimization, and institutional-grade risk analytics.

## Quick Start

### Run Examples

```bash
# Complete end-to-end workflow
python examples/complete_workflow_example.py

# Component demonstrations
python examples/modern_terminal_example.py      # Architecture overview
python examples/portfolio_example.py             # Portfolio analytics
python examples/bayesian_thesis_example.py       # Thesis updating
python examples/sparklines_example.py            # Data visualization
python examples/portfolio_integration_example.py # Integration patterns
```

### Integrate with Your Pipeline

```python
from iam.integration.async_bridge import AsyncPipelineAdapter
from iam.portfolio import Portfolio, Position, PortfolioVerdictEngine
from iam.ui.modern_terminal import ModernTerminal

# Run pipeline (async)
adapter = AsyncPipelineAdapter()
adapter.run_pipeline_async("MSFT", run_valuation_pipeline)

# Later, get results and create portfolio
result = adapter.get_pipeline_result("MSFT")

# Render
terminal = ModernTerminal()
terminal.load_security("MSFT", result)
print(terminal.render())
```

## System Architecture

### Layers (6 total)

```
Presentation     → Panels, state, events, visualization
Computation      → Async pipelines, factors, data
Analytics        → Attribution, regimes, risk decomposition
Intelligence     → Bayesian theorem, thesis management
Visualization    → Sparklines, heatmaps, inline charts
Infrastructure   → Config, logging, event bus
```

### Key Components

| Component | Purpose | Example |
|-----------|---------|---------|
| **State** | Immutable security/portfolio data | `SecurityState`, `Portfolio` |
| **Panels** | Modular UI components | `HeaderPanel`, `ScenarioMatrixPanel` |
| **Events** | Pub/sub for real-time updates | `SECURITY_LOADED`, `PRICE_TICK` |
| **Async** | Non-blocking data operations | `AsyncPipelineAdapter` |
| **Attribution** | Factor decomposition | `AttributionEngine.decompose()` |
| **Regime** | Macro classification | `RegimeDetector.detect()` |
| **Portfolio** | Multi-security composition | `PortfolioAnalyzer.compute_var()` |
| **Bayesian** | Probability updating | `BayesianUpdater.update()` |
| **Sparklines** | ANSI visualization | `Sparkline.line()`, `MiniChart` |
| **Config** | YAML-based settings | `TerminalSettings.from_file()` |

## Workflows

### Single Security Analysis

```python
from iam.ui.modern_terminal import ModernTerminal

# Load pipeline output
pipeline_result = run_valuation_pipeline("MSFT")

# Render with modular panels
terminal = ModernTerminal()
terminal.load_security("MSFT", pipeline_result)
print(terminal.render())

# Add visualizations
from iam.ui.sparklines import Sparkline
print(f"Price trend: {Sparkline.line(prices)}")
```

### Portfolio Construction

```python
from iam.portfolio import Position, Portfolio, PortfolioAnalyzer, PositionSizer

# Create positions from verdicts
positions = [
    Position(ticker="MSFT", conviction="HIGH", ...),
    Position(ticker="AAPL", conviction="MODERATE", ...),
]

portfolio = Portfolio(positions=positions)

# Analyze risk
exposures = PortfolioAnalyzer.compute_factor_exposures(portfolio, factor_scores)
print(f"Quality exposure: {exposures.quality_exposure:+.2f}σ")

# Check for crowding
if exposures.factor_crowding["quality"] > 0.75:
    print("⚠ Crowded in quality factor")

# Generate verdict
recommendation = PortfolioVerdictEngine.generate_verdict(portfolio, ...)
```

### Thesis Updating with Evidence

```python
from iam.thesis.bayesian.thesis import ThesisBuilder
from iam.thesis.bayesian.evidence import Evidence, ScenarioLikelihood
from iam.thesis.bayesian.updater import BayesianUpdater

# Create initial thesis
thesis = (ThesisBuilder("MSFT", "Microsoft", price=450)
    .add_scenario("Bear", prob=0.20, target=380, ...)
    .add_scenario("Base", prob=0.60, target=495, ...)
    .add_scenario("Bull", prob=0.20, target=585, ...)
    .build()
)

# Incorporate evidence
earnings = Evidence(
    type="EARNINGS_BEAT",
    description="EPS beat 8%",
    likelihoods={
        "Bear": ScenarioLikelihood(0.2),
        "Base": ScenarioLikelihood(0.6),
        "Bull": ScenarioLikelihood(0.95),
    },
    reliability=0.95
)

priors = [ScenarioPrior(s.name, s.probability) for s in thesis.scenarios]
posteriors = BayesianUpdater.update(priors, earnings)
# Bull probability increased from 20% to 35%
```

### Macro Regime Detection

```python
from iam.analytics.regime import RegimeDetector, RegimeIndicators

indicators = RegimeIndicators(
    inflation_rate=2.8,
    inflation_trend="falling",
    real_rates=1.5,
    gdp_growth=2.5,
    credit_spreads=280,
    equity_vix=18.0,
    earnings_trend="stable"
)

regime = RegimeDetector.detect(indicators)  # DISINFLATIONARY
weights = RegimeDetector.get_regime_weights(regime)

# Apply to base factors
adjusted = weights.apply_to_weights(base_weights)
# Quality: 1.0x → 1.0x, Growth: 0.8x → 1.5x
```

## Configuration

### Create Config File

```yaml
# ~/.iam/settings.yml or ./config.yml
factor_weights:
  quality: 0.20
  growth: 0.25
  value: 0.10
  momentum: 0.15
  sentiment: 0.10
  capital_allocation: 0.12
  earnings_quality: 0.08

terminal:
  width: 80
  unicode_enabled: true

async:
  max_workers: 4
  task_timeout_seconds: 60

logging:
  level: INFO
  log_dir: ./logs
```

### Load Settings

```python
from iam.config import get_settings

settings = get_settings()  # Auto-discovers config.yml
print(settings.terminal.width)  # 80
print(settings.factor_weights.quality)  # 0.20

# Or load specific file
from iam.config import TerminalSettings
settings = TerminalSettings.from_file("custom.yml")
```

## Data Visualization

### Sparklines

```python
from iam.ui.sparklines import Sparkline, MiniChart

prices = [100, 102, 101, 105, 103, 108, 110, 107, 111]

# Price movement
print(Sparkline.line(prices))        # ▁▂▁▄▂▅▆▅█

# Trend direction
print(Sparkline.trend(prices))       # ↑ (up)

# Intraday OHLC
print(MiniChart.intraday(100, 111, 100, 107))  # ▆
```

### Progress Bars

```python
from iam.ui.sparklines import ProgressBar

# Portfolio allocation
print(ProgressBar.bar_with_label(0.70, 1.0, width=20))
# ██████████████      70.0%
```

### Heatmaps

```python
from iam.ui.sparklines import HeatmapColor

metrics = {
    "Return": 0.15,
    "Sharpe": 0.72,
    "Volatility": 0.28,
}

for metric, value in metrics.items():
    indicator = HeatmapColor.indicator(value)
    print(f"{metric}: {indicator}")
    # Return: 🟢
    # Sharpe: 🟢
    # Volatility: 🟡
```

## Real-Time Integration

### Event Bus

```python
from iam.ui.events import EventType, subscribe_to_event, emit_event

# Subscribe to price updates
def on_price_tick(event):
    print(f"New price: {event.payload['price']}")

subscribe_to_event(EventType.PRICE_TICK, on_price_tick)

# Emit price update (would come from market data feed)
emit_event(EventType.PRICE_TICK, {"ticker": "MSFT", "price": 455.0})
```

### Async Data Loading

```python
from iam.data.async_loader import get_async_loader

loader = get_async_loader(max_workers=4)

# Load security data in background
loader.load_security_async(
    "MSFT",
    lambda ticker: fetch_from_api(ticker),
    on_complete=lambda ticker, data: update_ui(ticker, data),
    on_error=lambda ticker, err: show_error(ticker, err)
)

# UI shows loading spinner while data loads...
```

## Performance Metrics

### Logging

```python
from iam.config import LOGGER_PIPELINE, PerformanceLogger

logger = LOGGER_PIPELINE

# Track operation timing
with PerformanceLogger(logger, "Pipeline execution"):
    result = run_valuation_pipeline("MSFT")
    
# Logs: "Pipeline execution completed 1234ms"
```

### Observability

- Component-specific loggers: `LOGGER_PIPELINE`, `LOGGER_FACTORS`, `LOGGER_DATA`
- Structured logging: JSON or plaintext output
- Performance metrics: Automatic bottleneck detection
- Event history: Track all state changes via event bus

## Testing Components

Each component can be tested independently:

```python
# Test state management
from iam.ui.state import SecurityState
state = SecurityState(ticker="MSFT", price=450, pwev=520)
assert state.implied_move == pytest.approx(0.1556, abs=0.001)

# Test Bayesian update
from iam.thesis.bayesian.updater import BayesianUpdater
posteriors = BayesianUpdater.update(priors, evidence)
assert sum(p.probability for p in posteriors) == pytest.approx(1.0)

# Test portfolio analytics
from iam.portfolio import PortfolioAnalyzer
var = PortfolioAnalyzer.compute_portfolio_var(portfolio, vols, corr_matrix)
assert var > 0
```

## Common Tasks

### Load and Analyze a Security

```python
from iam.integration.orchestrator import run_full_pipeline
from iam.ui.modern_terminal import print_security_report

result = run_full_pipeline("MSFT")
print_security_report("MSFT", result)
```

### Build a Portfolio

```python
from iam.portfolio import Position, Portfolio

positions = [
    Position(ticker="MSFT", ..., conviction="HIGH"),
    Position(ticker="AAPL", ..., conviction="MODERATE"),
    Position(ticker="JPM", ..., conviction="MODERATE"),
]

portfolio = Portfolio(positions=positions)
```

### Update Thesis with News

```python
from iam.thesis.bayesian.evidence import Evidence
from iam.thesis.bayesian.updater import BayesianUpdater

guidance_evidence = Evidence(
    type="GUIDANCE_RAISE",
    description="Management raised FY guidance by 5%",
    likelihoods={...},
    reliability=0.90
)

updated_thesis = BayesianUpdater.update(current_thesis, guidance_evidence)
```

### Export Results

```python
# Portfolio to dict
portfolio_dict = portfolio.to_dict()

# Settings to YAML
settings.to_file("output.yml")

# State snapshot
state_snapshot = terminal.state.to_dict()
```

## Debugging

### Enable Debug Logging

```python
from iam.config import configure_logging
configure_logging(structured=True)  # JSON format

# Or set environment: LOG_LEVEL=DEBUG
```

### Check Event History

```python
from iam.ui.events import get_event_bus, EventType

bus = get_event_bus()
history = bus.get_history(EventType.SECURITY_LOADED, limit=10)
for event in history:
    print(f"{event.timestamp} | {event.payload}")
```

### Performance Profiling

```python
from iam.config import PerformanceLogger, LOGGER_PIPELINE

with PerformanceLogger(LOGGER_PIPELINE, "Analysis"):
    # Your code here
    pass
# Logs timing metrics
```

## Architecture Benefits

1. **Modular** - Each component is independently testable
2. **Scalable** - Async design prevents blocking UI
3. **Cognitive** - Bayesian reasoning, not subjective narratives
4. **Observable** - Structured logging and event trails
5. **Configurable** - YAML settings, no hardcoding
6. **Extensible** - Easy to add new panels, evidence types, visualizations
7. **Professional** - Institutional-grade analytics and risk management

## Next Steps

1. **Integrate with main.py** - Replace monolithic terminal with panel composition
2. **Add market data feeds** - Wire real-time price and news integration
3. **Portfolio optimization** - Mean-variance efficient frontier
4. **Research synthesis** - Generate investment memos from analysis
5. **Advanced analytics** - Options pricing, smart execution, macro modeling

## Documentation

- **ARCHITECTURE.md** - System design and layer breakdown
- **PORTFOLIO_GUIDE.md** - Portfolio layer usage guide
- **INTEGRATION_GUIDE.md** - End-to-end workflow integration
- **config.example.yml** - Configuration reference

## Examples

All examples are runnable and self-contained:

```bash
python examples/complete_workflow_example.py
```

## Support

For questions or issues:
1. Check the examples (they demonstrate all major features)
2. Read the documentation guides
3. Check component docstrings and type hints
4. Enable debug logging to trace execution

---

**Status**: Production-ready architecture, ready for integration with existing pipeline and real-time data sources.
