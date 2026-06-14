#!/usr/bin/env python3
"""Fast BUY/HOLD/SELL recommendations (10 seconds) using adaptive valuation.

Usage:
    python quick_recommend.py
    → Enter ticker
    → Get instant BUY/HOLD/SELL recommendation without asking for growth
    → Optionally see detailed valuation metrics
"""

from __future__ import annotations

import re
import sys

from iam.data.providers.yfinance_adapter import fetch_security
from src.iam.valuation.adaptive import AdaptiveValuationEngine
from src.iam.valuation.profile_builder import (
    build_company_profile,
    triangulate_growth_for_security,
)
from src.iam.valuation.expectations_battlefield import (
    ExpectationsBattlefieldEngine,
    build_distributions,
)


def print_banner() -> None:
    """Print welcome banner."""
    print("\n" + "=" * 76)
    print("  INSTITUTIONAL ALPHA - 10-SECOND STOCK RECOMMENDATION")
    print("  Adaptive Valuation Engine (no growth forecasts required)")
    print("=" * 76)
    print()


def validate_ticker(ticker: str) -> bool:
    """Validate ticker format."""
    from src.iam.validation import validate_ticker as strict_validate
    try:
        strict_validate(ticker)
        return True
    except ValueError:
        return False


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


def rating_from_confidence(confidence: str) -> str:
    """Convert confidence grade to BUY/HOLD/SELL.

    Args:
        confidence: Grade from adaptive engine ("A", "B", or "C")

    Returns:
        Rating string: "BUY", "HOLD", or "SELL"
    """
    if confidence == "A":
        return "BUY"
    elif confidence == "B":
        return "HOLD"
    else:
        return "SELL"


def format_rating_box(
    rating: str,
    confidence: str,
    business_type: str,
    year1_growth: float,
    year10_growth: float,
) -> str:
    """Format recommendation as a clean box."""
    lines = []
    lines.append("  " + "╔" + "═" * 72 + "╗")
    lines.append(f"  ║  {rating:20} │ Confidence: {confidence:2} │ Type: {business_type:15} ║")
    lines.append("  " + "║" + "─" * 72 + "║")
    lines.append(
        f"  ║  Year 1 Growth:     {year1_growth:6.1%}                                    ║"
    )
    lines.append(
        f"  ║  Year 10 Growth:    {year10_growth:6.1%}                                    ║"
    )
    lines.append("  " + "╚" + "═" * 72 + "╝")
    return "\n".join(lines)


def show_recommendation(ticker: str, force_details: bool = False) -> None:
    """Fetch security, run adaptive valuation, show recommendation."""
    print("\n  ⏳ Fetching data and running adaptive valuation...\n")

    try:
        # Fetch security
        security = fetch_security(ticker)
        print(f"  ✓ {security.name} loaded")
        print(f"  ✓ Sector: {security.sector}\n")

        # Run growth triangulation (5 independent estimators)
        triangulation = triangulate_growth_for_security(security)

        # Build company profile (uses triangulation internally)
        profile = build_company_profile(security)

        # Run adaptive valuation engine
        engine = AdaptiveValuationEngine()
        result = engine.run(profile)

        # Attach triangulation audit trail
        result["triangulation"] = triangulation.to_dict()

        # Extract results
        rating = rating_from_confidence(result["confidence"])
        confidence = result["confidence"]
        business_type = result["type"]
        fade_path = result["fade_path"]

        # Display recommendation
        print(
            format_rating_box(
                rating,
                confidence,
                business_type,
                fade_path[0],
                fade_path[-1],
            )
        )

        # Show interpretation
        print()
        if rating == "BUY":
            print("  🟢 BUY: Valuation appears attractive. Historical growth exceeds implied.")
        elif rating == "HOLD":
            print("  🟡 HOLD: Valuation in fair range. Growth assumptions appear reasonable.")
        else:
            print("  🔴 SELL: Valuation appears stretched. Implied growth exceeds sustainability.")

        print()

        # Show confidence explanation
        if confidence == "A":
            print("  ✓ HIGH confidence: Growth estimates align well. Business type well-defined.")
        elif confidence == "B":
            print("  ⚠ MEDIUM confidence: Some divergence in growth estimates. Use with judgment.")
        else:
            print("  ⚠ LOW confidence: High divergence or uncertain business type.")

        print()

        # Run Expectations Battlefield
        intrinsic_dist, market_dist = build_distributions(profile, triangulation)
        battlefield_engine = ExpectationsBattlefieldEngine(intrinsic_dist, market_dist)
        battlefield_result = battlefield_engine.compute()

        # Print Battlefield Summary unconditionally
        print(battlefield_result.summary().replace("\n", "\n  "))
        print()

        # Ask if user wants details
        if force_details:
            show_details = True
        elif not sys.stdin.isatty():
            show_details = False
        else:
            show_details = None

        if show_details is not None:
            if show_details:
                print("\n" + "=" * 76)
                print("  ADAPTIVE VALUATION ANALYSIS")
                print("=" * 76 + "\n")
                print(f"  Ticker:              {result['ticker']}")
                print(f"  Business Type:       {result['type']}")
                print(f"  Confidence:          {result['confidence']}\n")

                # Triangulation audit trail
                tri = result["triangulation"]
                print("  GROWTH TRIANGULATION (5 estimators):")
                print(f"    Blended Growth:    {tri['blended_growth']:>+7.1%}")
                print(f"    Raw Growth:        {tri['raw_growth']:>+7.1%}")
                print(f"    Margin Adjustment: {tri['margin_adjustment']:>+7.2%}pp")
                print(f"    Disagreement σ:    {tri['method_disagreement']:>7.1%}")
                print(f"    Dominant Method:   {tri['dominant_method']}\n")
                print(f"    {'Method':<14} {'Growth':>8} {'Conf':>6} {'Weight':>8}")
                for e in tri["estimates"]:
                    print(
                        f"    {e['method']:<14} {e['value']:>+8.1%} {e['confidence']:>6.2f} {e['weight']:>8.1f}"
                    )
                print()

                print("  Phase 2 (Divergence):")
                p2 = result["phase2"]
                print(
                    f"    Condition:         {p2['condition']} (threshold: {p2['threshold']:.1%})"
                )
                print(f"    Divergence:        {p2['divergence']:.1%}")
                print(f"    Base Growth:       {p2['base_growth']:.1%}\n")
                print("  Phase 3 (10-Year Fade Path):")
                for i, g in enumerate(fade_path, 1):
                    print(f"    Year {i:2d}:  {g:.1%}")
                print()
            else:
                print("\n  ✓ Done!\n")
        else:
            while True:
                details = input("  See detailed metrics? (y/n): ").strip().lower()
                if details == "y":
                    print("\n" + "=" * 76)
                    print("  ADAPTIVE VALUATION ANALYSIS")
                    print("=" * 76 + "\n")
                    print(f"  Ticker:              {result['ticker']}")
                    print(f"  Business Type:       {result['type']}")
                    print(f"  Confidence:          {result['confidence']}\n")

                    # Triangulation audit trail
                    tri = result["triangulation"]
                    print("  GROWTH TRIANGULATION (5 estimators):")
                    print(f"    Blended Growth:    {tri['blended_growth']:>+7.1%}")
                    print(f"    Raw Growth:        {tri['raw_growth']:>+7.1%}")
                    print(f"    Margin Adjustment: {tri['margin_adjustment']:>+7.2%}pp")
                    print(f"    Disagreement σ:    {tri['method_disagreement']:>7.1%}")
                    print(f"    Dominant Method:   {tri['dominant_method']}\n")
                    print(f"    {'Method':<14} {'Growth':>8} {'Conf':>6} {'Weight':>8}")
                    for e in tri["estimates"]:
                        print(
                            f"    {e['method']:<14} {e['value']:>+8.1%} {e['confidence']:>6.2f} {e['weight']:>8.1f}"
                        )
                    print()

                    print("  Phase 2 (Divergence):")
                    p2 = result["phase2"]
                    print(
                        f"    Condition:         {p2['condition']} (threshold: {p2['threshold']:.1%})"
                    )
                    print(f"    Divergence:        {p2['divergence']:.1%}")
                    print(f"    Base Growth:       {p2['base_growth']:.1%}\n")
                    print("  Phase 3 (10-Year Fade Path):")
                    for i, g in enumerate(fade_path, 1):
                        print(f"    Year {i:2d}:  {g:.1%}")
                    print()
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
    import argparse
    parser = argparse.ArgumentParser(description="Quick Recommendation Tool")
    parser.add_argument("ticker", nargs="?", help="Ticker symbol")
    parser.add_argument("--details", action="store_true", help="Show detailed metrics automatically")
    args = parser.parse_args()

    print_banner()

    if args.ticker:
        show_recommendation(args.ticker, force_details=args.details)
        return

    if not sys.stdin.isatty():
        print("Non-interactive session: running default analysis on AAPL")
        show_recommendation("AAPL", force_details=True)
        return

    while True:
        ticker = get_ticker()
        print()

        show_recommendation(ticker)

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
