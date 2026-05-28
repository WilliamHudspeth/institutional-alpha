#!/usr/bin/env python3
"""Example demonstrating the modern terminal architecture.

Shows:
- State management with SecurityState
- Event-driven architecture
- Panel composition
- Async data loading
- Factor attribution
- Macro regime detection

This represents the future terminal that supports:
- Streaming price updates
- Non-blocking computations
- Real-time factor analysis
- Regime-aware portfolio construction
"""

from iam.analytics.attribution import AttributionEngine
from iam.analytics.regime import RegimeDetector, RegimeIndicators
from iam.ui.events import EventType, get_event_bus
from iam.ui.modern_terminal import ModernTerminal
from iam.ui.state import SecurityState

# Sample security data
sample_security_data = {
    "ticker": "MSFT",
    "name": "Microsoft Corporation",
    "price": 450.25,
    "pwev": 520.00,
    "verdict": "BUY",
    "confidence": "HIGH",
    "growth": "12.5%",
    "wacc": "8.2%",
    "terminal": "3.0%",
    "synthesis": "+15.5%",
    "scenarios": [
        {
            "name": "Bear Case",
            "prob": "25%",
            "target": 380.00,
            "upside": "-15.6%",
            "thesis": "Cloud slowdown, regulatory pressure",
        },
        {
            "name": "Base Case",
            "prob": "50%",
            "target": 520.00,
            "upside": "+15.5%",
            "thesis": "Steady cloud growth, AI expansion",
        },
        {
            "name": "Bull Case",
            "prob": "25%",
            "target": 680.00,
            "upside": "+51.0%",
            "thesis": "AI monetization success, margin expansion",
        },
    ],
    "signals": {
        "reverse_dcf": "BULLISH (+20.5%)",
        "platform_compounder": "BULLISH (+15.5%)",
        "relative_valuation": "NEUTRAL (15x vs peer avg 16x)",
        "macro_overlay": "PASS (deflationary environment)",
    },
}

# Sample factor scores (z-scores)
factor_scores = {
    "quality": 1.5,  # Excellent quality
    "growth": 1.2,  # Strong growth
    "value": 0.3,  # Slightly cheap
    "momentum": 0.8,  # Positive momentum
    "sentiment": 1.0,  # Positive sentiment
    "capital_allocation": 1.4,  # Excellent capital allocation
    "earnings_quality": 1.3,  # High earnings quality
}

# Factor weights (base case)
factor_weights = {
    "quality": 0.20,
    "growth": 0.25,
    "value": 0.10,
    "momentum": 0.15,
    "sentiment": 0.10,
    "capital_allocation": 0.12,
    "earnings_quality": 0.08,
}

# Current macro environment
macro_indicators = RegimeIndicators(
    inflation_rate=2.8,
    inflation_trend="falling",
    real_rates=1.5,
    rate_trend="falling",
    unemployment=4.0,
    gdp_growth=2.5,
    credit_spreads=280,  # High-yield OAS
    equity_vix=18.0,
    earnings_revisions=2.5,
    earnings_trend="stable",
)


def main() -> None:
    """Run the modern terminal example."""

    print("\n" + "=" * 80)
    print("MODERN TERMINAL ARCHITECTURE EXAMPLE")
    print("=" * 80 + "\n")

    # 1. Create and render terminal with security data
    print("1. SECURITY REPORT (Panel-Based Rendering)")
    print("-" * 80)

    terminal = ModernTerminal(width=80)
    terminal.load_security("MSFT", sample_security_data)
    print(terminal.render())

    # 2. Demonstrate attribution analysis
    print("\n2. FACTOR ATTRIBUTION ANALYSIS")
    print("-" * 80)

    attribution = AttributionEngine.decompose(
        ticker="MSFT",
        factor_scores=factor_scores,
        factor_weights=factor_weights,
        composite_score=1.1,  # Overall +1.1% alpha
    )

    for line in AttributionEngine.format_for_display(attribution):
        print(line)

    # 3. Demonstrate regime detection and dynamic weighting
    print("\n3. MACROECONOMIC REGIME ANALYSIS")
    print("-" * 80)

    regime = RegimeDetector.detect(macro_indicators)
    regime_weights = RegimeDetector.get_regime_weights(regime)
    adjusted_weights = regime_weights.apply_to_weights(factor_weights)

    print(f"Detected Regime: {regime.value.upper()}")
    print(f"Inflation: {macro_indicators.inflation_rate}% ({macro_indicators.inflation_trend})")
    print(f"Real Rates: {macro_indicators.real_rates}%")
    print(f"Credit Spreads: {macro_indicators.credit_spreads}bp")
    print(f"VIX: {macro_indicators.equity_vix}")
    print("")

    print("Factor Weight Adjustments:")
    print(f"{'Factor':<30} {'Base':<10} {'Adjusted':<10} {'Change':<10}")
    print("-" * 60)

    for factor_name in sorted(factor_weights.keys()):
        base = factor_weights[factor_name]
        adjusted = adjusted_weights[factor_name]
        change = adjusted - base
        print(f"{factor_name:<30} {base:.2%} {adjusted:.2%} {change:+.2%}")

    # 4. Demonstrate event bus
    print("\n4. EVENT BUS INTEGRATION")
    print("-" * 80)

    event_bus = get_event_bus()

    def on_event(event):
        print(f"  Event: {event.event_type.value} @ {event.timestamp.strftime('%H:%M:%S')}")
        print(f"    Payload: {event.payload}")

    event_bus.subscribe(EventType.SECURITY_LOADED, on_event)
    event_bus.subscribe(EventType.PIPELINE_COMPLETE, on_event)

    # Emit sample events
    event_bus.emit(
        EventType.SECURITY_LOADED,
        {"ticker": "MSFT", "success": True, "source": "yfinance"},
        source="data_adapter",
    )

    event_bus.emit(
        EventType.PIPELINE_COMPLETE,
        {"ticker": "MSFT", "success": True, "elapsed_ms": 1450},
        source="pipeline",
    )

    # 5. State management demonstration
    print("\n5. STATE MANAGEMENT")
    print("-" * 80)

    security_state = SecurityState(
        ticker="MSFT",
        name="Microsoft Corporation",
        price=450.25,
        pwev=520.00,
        verdict="BUY",
        confidence="HIGH",
    )

    print(f"Security: {security_state.ticker} - {security_state.name}")
    print(f"Current Price: ${security_state.price:.2f}")
    print(f"Fair Value (PWEV): ${security_state.pwev:.2f}")
    print(f"Implied Move: {security_state.implied_move:+.1%}")
    print(f"Verdict: {security_state.verdict}")

    print("\n" + "=" * 80)
    print("Modern terminal architecture enables:")
    print("  ✓ Composable, modular panels (scales to 5k+ LOC)")
    print("  ✓ Event-driven reactivity (streaming updates, async integration)")
    print("  ✓ Immutable state management (predictable, testable)")
    print("  ✓ Non-blocking async data (UI remains responsive)")
    print("  ✓ Institutional analytics (attribution, regime detection)")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
