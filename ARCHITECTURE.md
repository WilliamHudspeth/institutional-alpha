# Institutional Terminal Architecture

This document describes the modern architecture of the institutional alpha terminal, implemented in phases to transform from monolithic to modular, scalable system.

## Overview

The terminal is built on four foundational layers:

```
┌─────────────────────────────────────────────────────────────┐
│  Presentation Layer (Panels, Events, State)                │
│  ├─ ModernTerminal: Event-driven rendering                 │
│  ├─ PanelComposer: Layout management                       │
│  └─ SecurityState: Immutable state objects                 │
├─────────────────────────────────────────────────────────────┤
│  Computation Layer (Async, Pipelines, Factors)             │
│  ├─ AsyncDataLoader: Non-blocking execution                │
│  ├─ ValuationPipeline: DCF, multiples, scenarios           │
│  └─ FactorEngines: Quality, growth, sentiment, etc.        │
├─────────────────────────────────────────────────────────────┤
│  Analytics Layer (Attribution, Regime, Portfolio)          │
│  ├─ AttributionEngine: Factor contribution decomposition   │
│  ├─ RegimeDetector: Macro environment classification       │
│  └─ [Portfolio: future]                                    │
├─────────────────────────────────────────────────────────────┤
│  Infrastructure (Data, Config, Logging, Events)            │
│  ├─ Data providers: Yahoo, Stooq, custom adapters          │
│  ├─ TerminalSettings: YAML/JSON configuration              │
│  ├─ Structured logging: Component loggers, file rotation   │
│  └─ EventBus: Pub/sub for reactive architecture            │
└─────────────────────────────────────────────────────────────┘
```

## Phase 1: Foundation (Completed)

### 1.1 State Management (`ui/state.py`)

Immutable dataclass-based state:

```python
from iam.ui.state import SecurityState, TerminalUIState

# Create security state
security = SecurityState(
    ticker="MSFT",
    name="Microsoft",
    price=450.00,
    pwev=520.00,
    verdict="BUY"
)

# Terminal state tracks active security and UI mode
state = TerminalUIState(active_security=security)
state.is_loading = False
state.error_message = None
```

**Benefits:**
- Predictable state mutations
- Easy testing and mocking
- Enables time-travel debugging
- Clear data ownership

### 1.2 Event Bus Architecture (`ui/events.py`)

Decoupled, reactive event handling:

```python
from iam.ui.events import EventType, emit_event, subscribe_to_event

# Subscribe to events
def on_security_loaded(event):
    print(f"Loaded {event.payload['ticker']}")

unsubscribe = subscribe_to_event(EventType.SECURITY_LOADED, on_security_loaded)

# Emit events
emit_event(
    EventType.SECURITY_LOADED,
    {"ticker": "MSFT", "success": True},
    source="data_adapter"
)
```

**Event Types:**
- Security events: SECURITY_LOADED, SECURITY_UPDATED, SECURITY_STALE
- Pipeline events: PIPELINE_START, PROGRESS, COMPLETE, ERROR
- Factor events: FACTOR_COMPLETE, FACTOR_ERROR
- Data events: PRICE_TICK, DATA_REFRESH
- UI events: MODE_CHANGED, SELECTION_CHANGED
- Thesis events: BAYESIAN_UPDATE, SCENARIO_CHANGE

### 1.3 Modular Panel System (`ui/panels.py`)

Composable UI components:

```python
from iam.ui.panels import BasePanel, PanelComposer, create_default_composer

class CustomPanel(BasePanel):
    def render(self, state):
        if not state.active_security:
            return ""
        return f"Custom output for {state.active_security.ticker}"

# Create composer with default panels
composer = create_default_composer()

# Add custom panel
composer.register_panel("custom", CustomPanel())

# Render all
output = composer.render(state)
```

**Built-in Panels:**
- HeaderPanel: System identification
- DecisionSheetPanel: Executive summary
- ForecastMetricsPanel: Growth, WACC, terminal values
- ScenarioMatrixPanel: Probability-weighted scenarios
- DiagnosticSignalsPanel: Multi-lens signals
- StatusPanel: Loading states and messages

**Advantages:**
- Scales to 5000+ LOC without becoming unmaintainable
- Each panel <300 LOC with clear responsibility
- Easy to add, remove, reorder panels
- Progressive enhancement: show loaded data immediately

### 1.4 Async Data Layer (`data/async_loader.py`)

Non-blocking data operations:

```python
from iam.data.async_loader import get_async_loader

loader = get_async_loader(max_workers=4)

def load_security(ticker):
    # Blocking function - runs in thread pool
    return fetch_from_api(ticker)

# Submit async task
loader.load_security_async(
    "MSFT",
    load_security,
    on_complete=lambda ticker, data: print(f"Loaded {ticker}"),
    on_error=lambda ticker, err: print(f"Error: {err}")
)

# UI remains responsive - can show loading spinner
```

**Features:**
- ThreadPoolExecutor-based concurrent execution
- Event emission on completion/error
- Timeout and cancellation support
- Parallel pipeline, factor, and data operations

### 1.5 Institutional Analytics (`analytics/`)

#### Attribution Engine (`attribution.py`)

Decompose composite alpha into factor contributions:

```python
from iam.analytics.attribution import AttributionEngine

# Factor scores (z-scores)
scores = {"quality": 1.5, "growth": 1.2, "momentum": 0.8}

# Factor weights
weights = {"quality": 0.20, "growth": 0.25, "momentum": 0.15}

# Decompose
analysis = AttributionEngine.decompose(
    ticker="MSFT",
    factor_scores=scores,
    factor_weights=weights,
    composite_score=1.1  # +1.1% overall alpha
)

print(analysis.format_summary())
# Output:
# Composite Alpha: +1.10%
#   ↑ Quality             +0.30% (+27% of total)
#   ↑ Growth              +0.30% (+27% of total)
#   ↑ Momentum            +0.12% (+11% of total)
```

#### Regime Detection (`regime.py`)

Detect macro environment and reweight factors dynamically:

```python
from iam.analytics.regime import RegimeDetector, RegimeIndicators

indicators = RegimeIndicators(
    inflation_rate=3.2,
    inflation_trend="rising",
    real_rates=1.5,
    rate_trend="rising",
    unemployment=4.0,
    gdp_growth=2.0,
    credit_spreads=350,
    equity_vix=20.0,
    earnings_revisions=1.5,
    earnings_trend="stable"
)

# Detect regime
regime = RegimeDetector.detect(indicators)  # MacroRegime.INFLATIONARY

# Get dynamic weights
regime_weights = RegimeDetector.get_regime_weights(regime)
adjusted_weights = regime_weights.apply_to_weights(base_weights)

# In inflationary regime:
# - quality: 1.4x (defensive)
# - growth: 0.5x (hurt by rates)
# - value: 1.2x (relative beneficiary)
```

## Phase 2: Integration & Examples (Completed)

### 2.1 Modern Terminal (`ui/modern_terminal.py`)

Event-driven rendering using panels and state:

```python
from iam.ui.modern_terminal import ModernTerminal

terminal = ModernTerminal(width=80)

# Load security data
terminal.load_security("MSFT", security_data_dict)

# Render to string
output = terminal.render()
print(output)

# Or use convenience function
from iam.ui.modern_terminal import print_security_report
print_security_report("MSFT", data_dict)
```

### 2.2 Async Integration Bridge (`integration/async_bridge.py`)

Bridges existing blocking code with async layer:

```python
from iam.integration.async_bridge import AsyncPipelineAdapter

adapter = AsyncPipelineAdapter()

def my_pipeline(ticker):
    # Existing blocking pipeline code
    return run_valuation_pipeline(ticker)

# Run async - returns immediately
task_id = adapter.run_pipeline_async(
    "MSFT",
    my_pipeline,
    on_complete=lambda ticker, result: display_results(ticker, result)
)

# UI shows loading state while pipeline runs...

# Later, get result
result = adapter.get_pipeline_result("MSFT", timeout=60)
```

### 2.3 Parallel Workflows

Execute multiple operations in parallel:

```python
from iam.integration.async_bridge import ParallelWorkflow

workflow = ParallelWorkflow()

# Queue multiple tasks
workflow.add_security_data("MSFT", fetch_security)
workflow.add_pipeline("MSFT", run_pipeline)
workflow.add_factors("MSFT", score_factors)

# Execute and wait
results = workflow.execute_and_wait(timeout=60)
# Returns: {
#     "security_MSFT": {...},
#     "pipeline_MSFT": {...},
#     "factors_MSFT": {...}
# }
```

## Phase 3: Configuration & Observability (Completed)

### 3.1 Configuration System (`config/settings.py`)

Pydantic-based configuration with multiple load methods:

```yaml
# config.yml or ~/.iam/settings.yml
factor_weights:
  quality: 0.20
  growth: 0.25
  value: 0.10
  momentum: 0.15

pipeline:
  forecast_periods: 10
  terminal_growth_rate: 0.025

async:
  max_workers: 4
  task_timeout_seconds: 60.0
```

```python
from iam.config import get_settings

settings = get_settings()  # Auto-loads from config.yml or env

# Access configuration
print(settings.terminal.width)  # 80
print(settings.async_config.max_workers)  # 4
print(settings.factor_weights.quality)  # 0.20

# Or load specific file
settings = TerminalSettings.from_file("custom_config.yml")

# Save configuration
settings.to_file("output.yml")
```

### 3.2 Structured Logging (`config/logging_config.py`)

Component-specific loggers with structured output:

```python
from iam.config import configure_logging, LOGGER_PIPELINE

configure_logging(structured=False)  # Plain text, or True for JSON

logger = LOGGER_PIPELINE
logger.info("Pipeline started", extra={"ticker": "MSFT", "duration_ms": 1234})

# Output:
# 2024-01-15 10:30:45 - iam.pipeline - INFO - Pipeline started | ticker=MSFT duration_ms=1234ms
```

## Usage Examples

### Example 1: Load and Render a Security

```python
from iam.ui.modern_terminal import ModernTerminal
from iam.data.providers.yfinance_adapter import fetch_security

terminal = ModernTerminal()

# Fetch data
data = fetch_security("MSFT")

# Load into state
terminal.load_security("MSFT", data)

# Render
print(terminal.render())
```

### Example 2: Run Pipeline Asynchronously

```python
from iam.integration.async_bridge import AsyncPipelineAdapter
from iam.integration.orchestrator import run_full_pipeline

adapter = AsyncPipelineAdapter()

def show_loading():
    print("⟳ Computing valuation...")

def show_results(ticker, results):
    print(f"\n{results['verdict']} | Fair value: ${results['pwev']}")

# Run async
task_id = adapter.run_pipeline_async(
    "MSFT",
    lambda ticker: run_full_pipeline(ticker),
    on_complete=show_results
)

show_loading()
```

### Example 3: Analyze Factor Attribution

```python
from iam.analytics.attribution import AttributionEngine
from iam.analytics.regime import RegimeDetector, RegimeIndicators

# Get factor scores from engine
scores = score_all_factors("MSFT")

# Decompose attribution
analysis = AttributionEngine.decompose(
    ticker="MSFT",
    factor_scores=scores,
    factor_weights=settings.factor_weights.as_dict(),
    composite_score=compute_composite(scores)
)

# Display
for line in AttributionEngine.format_for_display(analysis):
    print(line)

# Detect regime and adjust weights
indicators = get_current_macro_indicators()
regime = RegimeDetector.detect(indicators)
adjusted_weights = regime.apply_to_weights(base_weights)
```

## Architecture Benefits

### Scalability
- **Monolithic → Modular**: Panels keep UI <300 LOC per component
- **Blocking → Non-blocking**: Async layer enables background processing
- **Coupled → Event-driven**: Panels react to events without tight coupling

### Maintainability
- **Immutable state**: Changes are traceable and testable
- **Structured logging**: Debug issues faster with contextual logs
- **Configuration**: No hardcoded values, easy deployment

### Extensibility
- **Panel system**: Add new views without modifying existing ones
- **Event bus**: New components can subscribe to existing events
- **Analytics layer**: Attribution and regime engines are pluggable

## Future Enhancements

### Phase 4: Portfolio Layer
- Multi-security composition
- Factor crowding analysis
- Correlation matrix
- VaR calculation
- Expected return optimization

### Phase 5: Advanced Analytics
- Bayesian thesis formalization
- Options implied volatility surface
- Market microstructure analysis
- Smart order execution

### Phase 6: Rich Rendering
- Migrate to Textual framework
- Real-time price tickers
- Keyboard-driven navigation
- Streaming data visualization

### Phase 7: Research Synthesis
- Investment memo generation
- Risk summary synthesis
- Expectation gap analysis
- Variant perception identification

## Deployment

### Development
```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run example
python examples/modern_terminal_example.py

# Run tests
pytest tests/
```

### Production
```bash
# Copy config to ~/.iam/settings.yml
cp config.example.yml ~/.iam/settings.yml

# Configure
export IAM_CONFIG=~/.iam/settings.yml

# Run terminal
python main.py
```

## References

- **Event patterns**: Observer pattern, pub/sub
- **State management**: Redux/Elm-like immutable state
- **Panel architecture**: Inspired by Bloomberg terminal, Textual framework
- **Async patterns**: Actor model, thread pool executor
- **Configuration**: 12-factor app methodology
