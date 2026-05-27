#!/usr/bin/env python3
"""Simple CLI for quick BUY/HOLD/SELL recommendations on any stock.

Usage:
    python quick_recommend.py
    → Enter ticker
    → Get instant BUY/HOLD/SELL recommendation
    → Optionally see detailed analysis
"""

from __future__ import annotations

import sys
import re

from src.iam.data.yahoo import fetch_security
from src.iam.pipeline.orchestrator import ValuationPipeline


def print_banner() -> None:
    """Print welcome banner."""
    print("\n" + "=" * 76)
    print("  INSTITUTIONAL ALPHA - QUICK STOCK RECOMMENDATION")
    print("=" * 76)
    print()


def validate_ticker(ticker: str) -> bool:
    """Validate ticker format."""
    return bool(re.match(r"^[A-Z0-9\-\.]{1,15}$", ticker))


def get_ticker() -> str:
    """Prompt user for ticker."""
    while True:
        ticker = input("  Enter stock ticker (e.g., AAPL, BLK, JNJ): ").strip().upper()
        if not ticker:
            print("  ❌ Please enter a ticker\n")
            continue
        if not validate_ticker(ticker):
            print("  ❌ Invalid ticker format\n")
            continue
        return ticker


def get_forecast_growth() -> float:
    """Prompt for optional forecast growth override."""
    growth_input = input(
        "  Forecast growth [press Enter for 8%]: "
    ).strip()

    if not growth_input:
        return 0.08

    try:
        # Handle both 8 and 0.08 formats
        g = float(growth_input)
        if g > 1:  # Assuming user entered percentage
            return g / 100
        return g
    except ValueError:
        print("  ⚠️  Invalid input, using default 8%")
        return 0.08


def format_rating_box(rating: str, confidence: str, upside: float, price: float, fair_value: float) -> str:
    """Format recommendation as a clean box."""
    lines = []
    lines.append("  " + "╔" + "═" * 72 + "╗")
    lines.append(f"  ║  RECOMMENDATION: {rating:20} CONFIDENCE: {confidence:15} ║")
    lines.append("  " + "║" + "─" * 72 + "║")
    lines.append(f"  ║  Current Price:     ${price:10.2f}                                    ║")
    lines.append(f"  ║  Fair Value:        ${fair_value:10.2f}                                    ║")
    lines.append(f"  ║  Upside/Downside:   {upside:10.1%}                                    ║")
    lines.append("  " + "╚" + "═" * 72 + "╝")
    return "\n".join(lines)


def show_recommendation(ticker: str, forecast_growth: float) -> None:
    """Fetch security and show recommendation."""
    print("\n  ⏳ Fetching data and running analysis...\n")

    try:
        # Fetch security
        security = fetch_security(ticker)
        print(f"  ✓ {security.name} loaded\n")

        # Set forecast growth
        security.qualitative["forecast_growth"] = forecast_growth

        # Run pipeline
        pipeline = ValuationPipeline()
        report = pipeline.run(security)

        # Extract key values
        if report.final_verdict:
            rating = report.final_verdict.rating
            confidence = report.final_verdict.confidence_band
            blended_upside = report.final_verdict.blended_upside or report.implied_move_pct or 0
        else:
            rating = "INCONCLUSIVE"
            confidence = "LOW"
            blended_upside = 0

        fair_value = (security.market.price or 0) * (1 + blended_upside)

        # Display recommendation
        print(format_rating_box(
            rating,
            confidence,
            blended_upside,
            security.market.price or 0,
            fair_value
        ))

        # Show color-coded interpretation
        print()
        if rating == "BUY":
            print("  🟢 BUY: Stock appears undervalued. Potential upside exceeds 15%.")
        elif rating == "SELL":
            print("  🔴 SELL: Stock appears overvalued. Potential downside exceeds 10%.")
        else:
            print("  🟡 HOLD: Stock fairly valued. Return potential between -10% and +15%.")

        print()

        # Confidence explanation
        if confidence == "HIGH":
            print("  ✓ HIGH confidence: Multiple valuation methods agree on this recommendation.")
        elif confidence == "MEDIUM":
            print("  ⚠ MEDIUM confidence: Some divergence between methods; use with judgment.")
        else:
            print("  ⚠ LOW confidence: Limited data or high disagreement between methods.")

        print()

        # Ask if user wants details
        while True:
            details = input("  See detailed analysis? (y/n): ").strip().lower()
            if details == "y":
                print("\n" + "=" * 76)
                print("  DETAILED VALUATION PIPELINE")
                print("=" * 76 + "\n")
                print(report.explain(verbose=False))
                break
            elif details == "n":
                print("\n  ✓ Done!\n")
                break
            else:
                print("  Please enter 'y' or 'n'\n")

    except RuntimeError as e:
        print(f"  ❌ Could not fetch data for '{ticker}'")
        print(f"  Details: {e}\n")
    except Exception as e:
        print(f"  ❌ Error: {e}\n")


def main() -> None:
    """Main entry point."""
    print_banner()

    while True:
        ticker = get_ticker()
        print()
        forecast_growth = get_forecast_growth()
        print()

        show_recommendation(ticker, forecast_growth)

        # Ask if user wants another
        print()
        again = input("  Analyze another stock? (y/n): ").strip().lower()
        if again != "y":
            print("\n  👋 Goodbye!\n")
            break
        print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  👋 Goodbye!\n")
        sys.exit(0)
