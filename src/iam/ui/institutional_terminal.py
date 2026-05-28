"""Minimalist typographic terminal UI for institutional reports.

Whitespace, alignment, and section headers — no ASCII box-drawing characters.
Modeled after professional CLIs (Stripe terminal, quant trading logs) where
readability comes from indentation and column alignment, not borders.

No external dependencies. All rendering is pure f-string padding.
"""

from __future__ import annotations

from typing import Any

from iam.version import VERSION

WIDTH = 65
RULE = "=" * WIDTH
THIN_RULE = "-" * WIDTH


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


def print_institutional_ui(data: dict[str, Any]) -> None:
    """Render a minimalist, whitespace-driven institutional report.

    Args:
        data: Dictionary with the following keys (all optional, sensible
            defaults applied):
                ticker, name, price, verdict
                growth, wacc, terminal           — core assumption strings
                pwev, synthesis, confidence      — valuation summary
                scenarios: list of dicts with name/prob/target/upside/thesis
                signals: dict mapping signal name → verdict string
    """
    ticker = str(data.get("ticker", "TICK")).upper()
    name = data.get("name", "Unknown Company")
    price = float(data.get("price", 0.0) or 0.0)
    verdict = str(data.get("verdict", "HOLD")).upper()
    pwev = float(data.get("pwev", 0.0) or 0.0)
    confidence = str(data.get("confidence", "—")).upper()

    upside_str = _fmt_pct_signed((pwev / price) - 1) if price > 0 else "—"

    # Header
    print()
    print(RULE)
    print(f" INSTITUTIONAL ALPHA v{VERSION}".ljust(40) + f"{ticker} : {name}")
    print(RULE)

    # Executive summary — colons aligned at a single column
    print(f" Current Price    : {_fmt_currency(price)}")
    print(f" Fair Value (PWEV): {_fmt_currency(pwev)}  ({upside_str})")
    print(f" Final Consensus  : {verdict}")
    print(f" System Confidence: [ {confidence} ]")
    print(THIN_RULE)

    # Core assumptions
    growth = data.get("growth", "—")
    wacc = data.get("wacc", "—")
    terminal = data.get("terminal", "—")
    synthesis = data.get("synthesis")

    print()
    print(" [ CORE ASSUMPTIONS ]")
    print(f"   • Forecast Growth : {growth}")
    print(f"   • Terminal Growth : {terminal}")
    print(f"   • Discount Rate   : {wacc}")
    if synthesis is not None:
        print(f"   • Synthesis       : {synthesis}")

    # Scenario matrix — whitespace-aligned columns, no vertical bars
    scenarios = data.get("scenarios", [])
    if scenarios:
        print()
        print(" [ PROBABILISTIC SCENARIO MATRIX ]")
        print(f"   {'SCENARIO':<12} {'PROB':<6} {'TARGET':<12} {'IMPLIED':<10} THESIS")
        for s in scenarios:
            s_name = str(s.get("name", "—"))
            s_prob = str(s.get("prob", "—"))
            try:
                s_target = _fmt_currency(float(s.get("target", 0)))
            except (TypeError, ValueError):
                s_target = "—"
            s_upside = str(s.get("upside", "—"))
            s_thesis = str(s.get("thesis", ""))
            print(f"   {s_name:<12} {s_prob:<6} {s_target:<12} {s_upside:<10} {s_thesis}")

    # Component signals — colons aligned at column 25
    signals = data.get("signals", {})
    if signals:
        print()
        print(" [ COMPONENT SIGNALS ]")
        for engine, signal in signals.items():
            label = str(engine).replace("_", " ").title()
            print(f"   {label:<22} : {str(signal).upper()}")
        print(f"   {'Consensus (Arbitrated)':<22} : {verdict}")

    print()
    print(RULE)
    print()


def print_pipeline_summary(
    ticker: str,
    current_price: float,
    pwev: float,
    verdict: str,
    confidence: str,
) -> None:
    """Quick summary used for rapid feedback during pipeline run."""
    upside_str = _fmt_pct_signed((pwev / current_price) - 1) if current_price > 0 else "—"

    print()
    print(RULE)
    print(f" {ticker.upper()} — PIPELINE COMPLETE")
    print(RULE)
    print(f" Current Price    : {_fmt_currency(current_price)}")
    print(f" PWEV             : {_fmt_currency(pwev)}")
    print(f" Implied Upside   : {upside_str}")
    print(f" Verdict          : {verdict.upper()}")
    print(f" Confidence Band  : [ {confidence.upper()} ]")
    print(RULE)
    print()


def print_bayesian_update_summary(
    ticker: str,
    prior: dict[str, float],
    posterior: dict[str, float],
    evidence_type: str,
    evidence_reliability: float,
) -> None:
    """Render a Bayesian update report with aligned posterior columns."""
    print()
    print(RULE)
    print(f" BAYESIAN UPDATE — {ticker.upper()} ({evidence_type})")
    print(RULE)
    print(f" Evidence Reliability : {evidence_reliability * 100:.0f}%")
    print()
    print(f"   {'SCENARIO':<18} {'PRIOR':>8} {'POSTERIOR':>12} {'CHANGE':>10}")
    for scenario_name in prior.keys():
        p_prior = prior.get(scenario_name, 0.0)
        p_posterior = posterior.get(scenario_name, 0.0)
        change = p_posterior - p_prior
        print(
            f"   {scenario_name:<18} "
            f"{p_prior * 100:>7.1f}% "
            f"{p_posterior * 100:>11.1f}% "
            f"{change * 100:>+9.1f}%"
        )
    print()
    print(RULE)
    print()


if __name__ == "__main__":
    sample_data = {
        "ticker": "BLK",
        "name": "BlackRock, Inc.",
        "price": 1070.34,
        "verdict": "MIXED (REDUCED EXPECTED RETURN)",
        "growth": "8.0%",
        "wacc": "8.58%",
        "terminal": "2.5%",
        "pwev": 219.00,
        "synthesis": "+11.5%",
        "confidence": "MODERATE",
        "scenarios": [
            {
                "name": "Bear Case",
                "prob": "20%",
                "target": 146.13,
                "upside": "-84.0%",
                "thesis": "Stressed execution",
            },
            {
                "name": "Base Case",
                "prob": "60%",
                "target": 213.04,
                "upside": "-77.0%",
                "thesis": "Normal execution",
            },
            {
                "name": "Bull Case",
                "prob": "20%",
                "target": 311.33,
                "upside": "-66.0%",
                "thesis": "Platform leverage",
            },
        ],
        "signals": {
            "reverse_dcf": "BEARISH (-38.2%)",
            "platform_compounder": "BULLISH (+11.5%)",
            "relative_valuation": "NEUTRAL",
            "macro_overlay": "CAUTION (+50bps)",
        },
    }

    print_institutional_ui(sample_data)
    print_pipeline_summary("BLK", 1070.34, 219.00, "MIXED", "MODERATE")

    prior = {"Bear Case": 0.20, "Base Case": 0.60, "Bull Case": 0.20}
    posterior = {"Bear Case": 0.08, "Base Case": 0.58, "Bull Case": 0.34}
    print_bayesian_update_summary("BLK", prior, posterior, "EARNINGS_BEAT", 0.85)
