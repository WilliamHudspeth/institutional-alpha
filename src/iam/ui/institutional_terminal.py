"""Retro-futuristic 90s Bloomberg Terminal and Aladdin console UI for institutional reports.

Presents a highly immersive, retro military-grade quant console layout featuring
custom double-line ASCII borders, a structured system HUD, dynamic horizontal valuation sliders,
and an interactive implied move gauge.

No external dependencies. All rendering is pure, robust f-string padding.
"""

from __future__ import annotations

from typing import Any

from iam.version import VERSION

WIDTH = 80
RULE = "═" * WIDTH
THIN_RULE = "─" * WIDTH


def _fmt_currency(value: float) -> str:
    """Format a dollar amount with thousands separator and 2 decimals."""
    try:
        return f"${value:,.2f}"
    except (TypeError, ValueError):
        return "$—"


def _fmt_pct_signed(value: float) -> str:
    """Format a unit decimal (e.g., 0.085) as a signed percentage."""
    try:
        return f"{value * 100:+.1f}%"
    except (TypeError, ValueError):
        return "—"


def _draw_valuation_graph(price: float, bear: float, base: float, bull: float, pwev: float) -> str:
    """Draw a horizontal ASCII bar graph showing current price relative to scenario targets."""
    if price <= 0 or bear >= bull or bear <= 0 or bull <= 0:
        return "   [VALUATION RANGE GRAPH UNAVAILABLE: INVALID DATA]"

    graph_width = 46
    span = bull - bear
    if span <= 0:
        return "   [VALUATION RANGE GRAPH UNAVAILABLE: SPAN ZERO]"

    # Map prices to positions on our horizontal track
    price_pos = int(((price - bear) / span) * graph_width)
    price_pos = max(0, min(graph_width - 1, price_pos))

    pwev_pos = int(((pwev - bear) / span) * graph_width)
    pwev_pos = max(0, min(graph_width - 1, pwev_pos))

    # Construct the track using block characters
    track = ["─"] * graph_width
    track[pwev_pos] = "█"  # Probability-Weighted Target

    if price_pos == pwev_pos:
        track[price_pos] = "╬"  # Current overlaps Target
    else:
        track[price_pos] = "║"  # Current Stock Price position

    track_str = "".join(track)

    lines = [
        f"   Bear {_fmt_currency(bear):<9} ╠{track_str}╣ Bull {_fmt_currency(bull):>9}",
        f"   {' ' * 14}║{' ' * price_pos}▲ (Current: {_fmt_currency(price)})"
        if price_pos <= pwev_pos
        else f"   {' ' * 14}║{' ' * pwev_pos}▲ (Base PWEV: {_fmt_currency(pwev)})",
        f"   {' ' * 14}║{' ' * pwev_pos}▲ (Base PWEV: {_fmt_currency(pwev)})"
        if price_pos <= pwev_pos
        else f"   {' ' * 14}║{' ' * price_pos}▲ (Current: {_fmt_currency(price)})",
    ]
    return "\n".join(lines)


def _draw_move_meter(move_pct: float) -> str:
    """Draw a professional retro horizontal gauge for implied upside/downside."""
    meter_width = 40
    # Map -100% to +100% to track positions
    pos = int(((move_pct + 1.0) / 2.0) * meter_width)
    pos = max(0, min(meter_width - 1, pos))

    track = ["═"] * meter_width
    track[meter_width // 2] = "║"  # Center baseline

    if pos < meter_width // 2:
        # Downside (fill left side with block/arrow)
        for i in range(pos, meter_width // 2):
            track[i] = "░"
        track[pos] = "◄"
    elif pos > meter_width // 2:
        # Upside (fill right side with block/arrow)
        for i in range(meter_width // 2 + 1, pos + 1):
            track[i] = "░"
        track[pos] = "►"
    else:
        track[pos] = "╬"

    track_str = "".join(track)
    return f"   [-100%] ╠{track_str}╣ [+100%]  Implied Move: {move_pct * 100:+.1f}%"


def print_institutional_ui(data: dict[str, Any]) -> None:
    """Render a high-fidelity retro 90s Bloomberg / Aladdin style report card."""
    ticker = str(data.get("ticker", "TICK")).upper()
    name = data.get("name", "Unknown Company")
    price = float(data.get("price", 0.0) or 0.0)
    verdict = str(data.get("verdict", "HOLD")).upper()
    pwev = float(data.get("pwev", 0.0) or 0.0)
    confidence = str(data.get("confidence", "—")).upper()

    move_pct = (pwev / price) - 1.0 if price > 0 else 0.0
    upside_str = _fmt_pct_signed(move_pct)

    # 1. Structured retro system HUD header
    print()
    print("┌" + "─" * 78 + "┐")
    print(f"│  ALADDIN-IA // SYSTEM ACTIVE // COGNITIVE QUANTITATIVE MULTI-FACTOR ENGINE   │")
    print(f"│  SECURITY: {ticker:<10} NAME: {name:<26} STATUS: ONLINE         │")
    print("└" + "─" * 78 + "┘")
    print(RULE)
    print(f"║  [ EXECUTIVE DECISION SHEET ]".ljust(WIDTH - 1) + "║")
    print(RULE)
    print(f"   • Current Spot Price : {_fmt_currency(price):<18} • consensus rating   : {verdict}")
    print(
        f"   • Fair Value (PWEV)  : {_fmt_currency(pwev):<18} • Arb Engine Weight : 70% Synthesis / 30% Trad"
    )
    print(f"   • Arb Implied Move   : {upside_str:<18} • System Confidence  : [ {confidence} ]")
    print(RULE)

    # 2. Assumptions section
    growth = data.get("growth", "—")
    wacc = data.get("wacc", "—")
    terminal = data.get("terminal", "—")
    synthesis = data.get("synthesis")

    print(f"║  [ CORE FORECAST METRIC PROFILE ]".ljust(WIDTH - 1) + "║")
    print(THIN_RULE)
    print(f"   Forecast Growth : {growth:<15} Discount Rate (WACC)   : {wacc}")
    print(f"   Terminal Growth : {terminal:<15} Consensus Synthesis     : {synthesis or 'N/A'}")
    print(THIN_RULE)

    # 3. Implied Move Gauge
    print(f"║  [ consensus IMPLIED DIRECTION GAUGE ]".ljust(WIDTH - 1) + "║")
    print(THIN_RULE)
    print(_draw_move_meter(move_pct))
    print(THIN_RULE)

    # 4. Scenario Matrix
    scenarios = data.get("scenarios", [])
    bear_val = 0.0
    base_val = 0.0
    bull_val = 0.0

    if scenarios:
        print(f"║  [ PROBABILISTIC SCENARIO WEIGHT MATRIX ]".ljust(WIDTH - 1) + "║")
        print(THIN_RULE)
        print(
            f"   {'SCENARIO CASE':<16} {'WEIGHT':<8} {'TARGET VALUE':<16} {'IMPLIED RETURN':<16} THESIS"
        )
        for s in scenarios:
            s_name = str(s.get("name", "—"))
            s_prob = str(s.get("prob", "—"))
            try:
                target_f = float(s.get("target", 0.0) or 0.0)
                s_target = _fmt_currency(target_f)
            except (TypeError, ValueError):
                target_f = 0.0
                s_target = "—"
            s_upside = str(s.get("upside", "—"))
            s_thesis = str(s.get("thesis", ""))

            # Capture bounds for the range graph
            name_lower = s_name.lower()
            if "bear" in name_lower:
                bear_val = target_f
            elif "base" in name_lower:
                base_val = target_f
            elif "bull" in name_lower:
                bull_val = target_f

            print(f"   {s_name:<16} {s_prob:<8} {s_target:<16} {s_upside:<16} {s_thesis}")
        print(THIN_RULE)

    # 5. Dynamic Valuation ASCII Range Slider
    if bear_val > 0 and bull_val > 0:
        print(f"║  [ SCENARIO VALUATION BOUNDARY GAUGE ]".ljust(WIDTH - 1) + "║")
        print(THIN_RULE)
        print(_draw_valuation_graph(price, bear_val, base_val, bull_val, pwev))
        print(THIN_RULE)

    # 6. Component Diagnostic Signals
    signals = data.get("signals", {})
    if signals:
        print(f"║  [ MULTI-LENS DIAGNOSTIC INTERMEDIARY SIGNALS ]".ljust(WIDTH - 1) + "║")
        print(THIN_RULE)
        for engine, signal in signals.items():
            label = str(engine).replace("_", " ").title()
            print(f"   • {label:<35} : {str(signal).upper()}")
        print(RULE)


def print_pipeline_summary(
    ticker: str,
    current_price: float,
    pwev: float,
    verdict: str,
    confidence: str,
) -> None:
    """Compact retro summary for quick diagnostic logs."""
    upside_str = _fmt_pct_signed((pwev / current_price) - 1.0) if current_price > 0 else "—"

    print()
    print("┌" + "─" * 78 + "┐")
    print(f"│  ALADDIN-IA // SYSTEM DIAGNOSTIC COMPILATION PROCESS COMPLETE                │")
    print("└" + "─" * 78 + "┘")
    print(RULE)
    print(f"║  [ {ticker.upper()} VALUATION PIPELINE COMPLETE STATS ]".ljust(WIDTH - 1) + "║")
    print(RULE)
    print(
        f"   • Spot Market Price : {_fmt_currency(current_price):<18} • Consensus Rating  : {verdict.upper()}"
    )
    print(
        f"   • Target PWEV Value : {_fmt_currency(pwev):<18} • Confidence Level  : [ {confidence.upper()} ]"
    )
    print(f"   • Arb Implied Move  : {upside_str:<18} • Diagnostic Code   : 0x90 (SYS_OK)")
    print(RULE)
    print()


def print_bayesian_update_summary(
    ticker: str,
    prior: dict[str, float],
    posterior: dict[str, float],
    evidence_type: str,
    evidence_reliability: float,
) -> None:
    """Render an immersive retro Bayesian inference update log."""
    print()
    print("┌" + "─" * 78 + "┐")
    print(f"│  ALADDIN-IA // BAYESIAN PROBABILISTIC INTERPRETATION MATRIX MODULE           │")
    print(
        f"│  TICKER: {ticker.upper():<10} EVENT TYPE: {evidence_type:<20} RELIABILITY: {evidence_reliability * 100:.0f}%      │"
    )
    print("└" + "─" * 78 + "┘")
    print(RULE)
    print(f"║  [ COGNITIVE PROBABILITY DISTRIBUTION SHIFT DIAGNOSTIC ]".ljust(WIDTH - 1) + "║")
    print(RULE)
    print(
        f"   {'SCENARIO CASE':<20} {'PRIOR WEIGHT':>15} {'POSTERIOR WEIGHT':>20} {'NET DEVIATION':>15}"
    )
    print(THIN_RULE)

    for scenario_name in prior.keys():
        p_prior = prior.get(scenario_name, 0.0)
        p_posterior = posterior.get(scenario_name, 0.0)
        change = p_posterior - p_prior

        # Generate a mini retro indicator bar showing the direction of weight shift
        bar = "════"
        if change > 0.02:
            bar_indicator = "   ═►"
        elif change < -0.02:
            bar_indicator = "   ◄═"
        else:
            bar_indicator = "    ■"

        print(
            f"   {scenario_name:<20} "
            f"{p_prior * 100:>13.1f}% "
            f"{bar_indicator} "
            f"{p_posterior * 100:>14.1f}% "
            f"{change * 100:>+14.1f}%"
        )
    print(RULE)
    print()


if __name__ == "__main__":
    sample_data = {
        "ticker": "BLK",
        "name": "BlackRock, Inc.",
        "price": 1070.34,
        "verdict": "STRONG BUY",
        "growth": "14.0%",
        "wacc": "7.16%",
        "terminal": "2.5%",
        "pwev": 1600.48,
        "synthesis": "+57.0%",
        "confidence": "MODERATE",
        "scenarios": [
            {
                "name": "Bear Case",
                "prob": "20%",
                "target": 697.15,
                "upside": "-34.9%",
                "thesis": "Stressed execution",
            },
            {
                "name": "Base Case",
                "prob": "60%",
                "target": 1409.61,
                "upside": "+31.7%",
                "thesis": "Anchor assumptions",
            },
            {
                "name": "Bull Case",
                "prob": "20%",
                "target": 3076.42,
                "upside": "+187.4%",
                "thesis": "Platform leverage",
            },
        ],
        "signals": {
            "reverse_dcf": "BEARISH (-38.2%)",
            "platform_compounder": "BULLISH (+57.0%)",
            "relative_valuation": "N/A",
            "macro_overlay": "PASS",
        },
    }

    print_institutional_ui(sample_data)
    print_pipeline_summary("BLK", 1070.34, 1600.48, "STRONG BUY", "MODERATE")

    prior_weights = {"Bear Case": 0.20, "Base Case": 0.60, "Bull Case": 0.20}
    posterior_weights = {"Bear Case": 0.08, "Base Case": 0.58, "Bull Case": 0.34}
    print_bayesian_update_summary("BLK", prior_weights, posterior_weights, "EARNINGS_BEAT", 0.85)
