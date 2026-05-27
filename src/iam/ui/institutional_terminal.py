"""Institutional ASCII terminal UI using pure Python f-strings.

No external dependencies (no `rich`, `textual`, etc.).
Uses f-string padding (:<N} syntax) to maintain perfect alignment.
Production-ready for terminal output.
"""

from __future__ import annotations
from typing import Dict, List, Optional, Any


def print_institutional_ui(data: Dict[str, Any]) -> None:
    """Render institutional ASCII terminal UI.

    Args:
        data: Dictionary with keys:
            - ticker: Stock symbol (e.g., "BLK")
            - name: Company name (e.g., "BlackRock, Inc.")
            - price: Current price (float)
            - verdict: Final rating (e.g., "MIXED", "BUY", "SELL")
            - growth: Forecast growth rate (str, e.g., "8%")
            - wacc: Discount rate (str, e.g., "8.58%")
            - terminal: Terminal growth rate (str, e.g., "2.5%")
            - pwev: Probability-weighted expected value (float)
            - synthesis: Synthesis upside (str, e.g., "+11.5%")
            - confidence: Confidence regime (str, e.g., "MODERATE")
            - scenarios: List of scenario dicts with keys:
                - name: Scenario name (str, e.g., "Bear")
                - prob: Probability (str, e.g., "20%")
                - target: Target price (float)
                - upside: Implied upside (str, e.g., "-84%")
                - thesis: Brief thesis (str)
            - signals: Dict of signal names to verdicts (e.g., {"reverse_dcf": "BEARISH"})

    Example:
        data = {
            "ticker": "BLK",
            "name": "BlackRock, Inc.",
            "price": 1070.34,
            "verdict": "MIXED",
            "growth": "8%",
            "wacc": "8.58%",
            "terminal": "2.5%",
            "pwev": 219.00,
            "synthesis": "+11.5%",
            "confidence": "MODERATE",
            "scenarios": [
                {"name": "Bear", "prob": "20%", "target": 146, "upside": "-84%", "thesis": "stressed"},
                {"name": "Base", "prob": "60%", "target": 213, "upside": "-77%", "thesis": "normal"},
                {"name": "Bull", "prob": "20%", "target": 311, "upside": "-66%", "thesis": "platform"}
            ],
            "signals": {
                "reverse_dcf": "BEARISH",
                "compounder": "BULLISH",
                "relative": "NEUTRAL",
                "macro": "CAUTION"
            }
        }
        print_institutional_ui(data)
    """
    # Unpack data with fallbacks
    ticker = data.get("ticker", "TICK")
    name = data.get("name", "Unknown Company")
    price = data.get("price", 0.0)
    verdict = data.get("verdict", "HOLD")

    g = data.get("growth", "N/A")
    wacc = data.get("wacc", "N/A")
    term = data.get("terminal", "N/A")

    pwev = data.get("pwev", 0.0)
    synth = data.get("synthesis", "N/A")
    conf = data.get("confidence", "N/A")

    scenarios = data.get("scenarios", [])
    signals = data.get("signals", {})

    # 1. HEADER BOX
    print("\n┌────────────────────────────────────────────────────────────┐")
    print(f"│ INSTITUTIONAL ALPHA v0.2.1-alpha                           │")
    print(f"│ {ticker.upper():<4} — {name:<46} │")
    print(f"│ Price: ${price:<13.2f} Verdict: {verdict:<25} │")
    print("└────────────────────────────────────────────────────────────┘")

    # 2. ASSUMPTIONS & SUMMARY BOX
    print("┌───────────────┬────────────────────────────────────────────┐")
    print("│ ASSUMPTIONS   │ VALUATION SUMMARY                          │")
    print("├───────────────┼────────────────────────────────────────────┤")
    print(f"│ Growth: {g:<5} │ PWEV: ${pwev:<37.2f} │")
    print(f"│ WACC: {wacc:<7} │ Synthesis: {synth:<32} │")
    print(f"│ Terminal:{term:<4} │ Confidence: {conf:<31} │")
    print("└───────────────┴────────────────────────────────────────────┘")

    # 3. PROBABILISTIC MATRIX BOX
    if scenarios:
        print("┌────────────────────────────────────────────────────────────┐")
        print("│ PROBABILISTIC SCENARIO MATRIX                              │")
        print("├────────────┬──────────┬──────────┬─────────────────────────┤")
        for s in scenarios:
            case = f"{s.get('name', 'Unknown'):<10} {s.get('prob', 'N/A')}"
            target = f"${s.get('target', 0):<8.0f}"
            upside = f"{s.get('upside', 'N/A'):<8}"
            thesis = f"{s.get('thesis', 'N/A'):<23}"
            print(f"│ {case:<10} │ {target:<8} │ {upside:<8} │ {thesis:<23} │")
        print("└────────────┴──────────┴──────────┴─────────────────────────┘")

    # 4. MODEL SIGNALS
    if signals:
        print("\nMODEL SIGNALS & ARBITRATION")
        print("────────────────────────────────────")
        for signal_name, signal_verdict in signals.items():
            signal_label = signal_name.replace("_", " ").title()
            print(f"{signal_label:<30} {signal_verdict:>15}")
        print(f"{'Consensus (Arbitrated)':<30} {verdict:>15}")

    print()


def print_pipeline_summary(ticker: str, current_price: float, pwev: float, verdict: str, confidence: str) -> None:
    """Quick summary print (useful for rapid feedback during pipeline run).

    Args:
        ticker: Stock symbol
        current_price: Current market price
        pwev: Probability-weighted expected value
        verdict: Final rating
        confidence: Confidence band
    """
    upside = ((pwev / current_price) - 1.0) * 100 if current_price > 0 else 0.0
    width = 60

    print("\n" + "=" * width)
    print(f" {ticker} — PIPELINE COMPLETE".center(width))
    print("=" * width)
    print(f"  Current Price:        ${current_price:>10.2f}")
    print(f"  PWEV:                 ${pwev:>10.2f}")
    print(f"  Implied Upside:       {upside:>10.1f}%")
    print(f"  Verdict:              {verdict:>10}")
    print(f"  Confidence Band:      {confidence:>10}")
    print("=" * width + "\n")


def print_bayesian_update_summary(
    ticker: str,
    prior: Dict[str, float],
    posterior: Dict[str, float],
    evidence_type: str,
    evidence_reliability: float
) -> None:
    """Print Bayesian update summary.

    Args:
        ticker: Stock symbol
        prior: Prior probabilities {scenario_name: probability}
        posterior: Posterior probabilities {scenario_name: probability}
        evidence_type: Type of evidence (e.g., "EARNINGS_BEAT")
        evidence_reliability: Reliability (0-1)
    """
    print("\n" + "─" * 60)
    print(f" BAYESIAN UPDATE: {ticker} — {evidence_type}".center(60))
    print("─" * 60)
    print(f"  Evidence Reliability: {evidence_reliability*100:.0f}%\n")

    print("  Scenario            Prior      Posterior    Change")
    print("  " + "─" * 54)
    for scenario_name in prior.keys():
        p_prior = prior.get(scenario_name, 0.0)
        p_posterior = posterior.get(scenario_name, 0.0)
        change = p_posterior - p_prior
        change_str = f"{change:+.1%}"
        print(f"  {scenario_name:<18} {p_prior:>6.1%}      {p_posterior:>6.1%}       {change_str:>6}")

    print()


if __name__ == "__main__":
    # Test with sample data
    sample_data = {
        "ticker": "BLK",
        "name": "BlackRock, Inc.",
        "price": 1070.34,
        "verdict": "MIXED",
        "growth": "8%",
        "wacc": "8.58%",
        "terminal": "2.5%",
        "pwev": 219.00,
        "synthesis": "+11.5%",
        "confidence": "MODERATE",
        "scenarios": [
            {
                "name": "Bear",
                "prob": "20%",
                "target": 146.13,
                "upside": "-84%",
                "thesis": "Stressed execution"
            },
            {
                "name": "Base",
                "prob": "60%",
                "target": 213.04,
                "upside": "-77%",
                "thesis": "Normal execution"
            },
            {
                "name": "Bull",
                "prob": "20%",
                "target": 311.33,
                "upside": "-66%",
                "thesis": "Platform leverage"
            },
        ],
        "signals": {
            "reverse_dcf": "BEARISH (-38.2%)",
            "compounder": "BULLISH (+11.5%)",
            "relative": "NEUTRAL",
            "macro": "CAUTION (+50bps)"
        }
    }

    print_institutional_ui(sample_data)
    print_pipeline_summary("BLK", 1070.34, 219.00, "MIXED", "MODERATE")

    # Test Bayesian update summary
    prior = {"Bear Case": 0.20, "Base Case": 0.60, "Bull Case": 0.20}
    posterior = {"Bear Case": 0.08, "Base Case": 0.58, "Bull Case": 0.34}
    print_bayesian_update_summary("BLK", prior, posterior, "EARNINGS_BEAT", 0.85)
