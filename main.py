#!/usr/bin/env python3
"""Interactive main menu for the IAM framework.

A user-friendly entry point that guides you through:
  - Factor scoring across multiple securities
  - Detailed valuation pipeline on a single name
  - Thesis engine with scenario analysis
  - Backtest harness for factor efficacy evaluation
"""

from __future__ import annotations

import json
import re
import sys
import urllib.parse
import urllib.request

from iam.validation import parse_growth_rate, validate_all_assumptions


def safe_input(prompt: str, default: str | None = None) -> str:
    """Return user input if interactive, otherwise return default.
    Strips whitespace and returns default when stdin is not a TTY.
    """
    if sys.stdin.isatty():
        return input(prompt).strip()
    else:
        return default if default is not None else ""



def print_header() -> None:
    """Print the main welcome banner."""
    from iam.version import header, metadata

    print(header())
    meta = metadata()
    print(f"Python {meta['python']} | Research Preview\n")


def print_menu() -> None:
    """Print the main menu options with persistent console header."""
    import os

    from iam.version import VERSION

    # Clear console for immersive dedicated retro terminal experience
    try:
        os.system("cls" if os.name == "nt" else "clear")
    except Exception:
        print("\n" * 3)

    print("┌" + "─" * 78 + "┐")
    print(f"│  ALPHA-TERMINAL // SYSTEM CONSOLE // COGNITIVE MULTI-FACTOR EQUITIES PLATFORM │")
    print(
        f"│  USER: wshb         SECURE TERMINAL: ACTIVE           SYSTEM VERSION: {VERSION:<14} │"
    )
    print("└" + "─" * 78 + "┘")
    print("What would you like to do?\n")
    print("  1. Quick recommendation (BUY/HOLD/SELL in 10 seconds)")
    print("  2. Deep dive valuation (7-stage pipeline with details)")
    print("  3. Factor scoring (10 factors + 3 penalties)")
    print("  4. Scenario analysis with thesis engine")
    print("  5. Backtest factor efficacy (historical analysis)")
    print("  6. Exit")
    print()


def resolve_ticker(query: str) -> tuple[str, str | None]:
    """Attempt to resolve a company name to a ticker using Yahoo Finance search."""
    try:
        safe_query = urllib.parse.quote(query)
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={safe_query}&quotesCount=1&newsCount=0"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
            quotes = data.get("quotes", [])
            if quotes and "symbol" in quotes[0]:
                return quotes[0]["symbol"].upper(), quotes[0].get(
                    "shortname", quotes[0].get("longname")
                )
    except Exception:
        pass
    return query.strip().upper(), None


def validate_ticker(ticker: str) -> bool:
    """Validate ticker format."""
    return bool(re.match(r"^[A-Z0-9\-\.]{1,15}$", ticker))


def get_security_input() -> str:
    """Prompt user for a security (ticker or company name)."""
    print("-" * 70)
    while True:
        query = safe_input("Enter a ticker symbol or company name: ", default="AAPL")
        if not query:
            print("  No input provided. Using default ticker AAPL.")
            query = "AAPL"


        # Try to resolve the ticker
        ticker, resolved_name = resolve_ticker(query)

        if not validate_ticker(ticker):
            print(f"  '{query}' could not be resolved to a valid ticker. Please try again.")
            continue

        print(f"  ✓ Ticker resolved: {ticker}", end="")
        if resolved_name and ticker != query.upper():
            print(f" ({resolved_name})")
        else:
            print()

        return ticker


def run_valuation_pipeline(ticker: str) -> None:
    """Run the 7-stage valuation pipeline with Master Arbitration Layer."""
    print("\n" + "-" * 70)
    print(f"  Fetching {ticker} from Yahoo Finance...")
    try:
        from iam.data.yahoo import fetch_security
        from iam.engine.damodaran import DamodaranEngine
        from iam.lenses.expectations_difficulty import ExpectationsDifficultyLens
        from iam.lenses.platform_compounder import PlatformCompounderLens
        from iam.lenses.rate_sensitive import RateSensitiveLens
        from iam.lenses.synthesis import synthesize_lenses
        from iam.pipeline.orchestrator import ValuationPipeline, print_assumption_table

        security = fetch_security(ticker)
        print(f"  ✓ {security.name or ticker} loaded")
        print()

        # Optional growth override
        g_input = safe_input(
            "  Forecast growth (e.g. 13 or 0.13 for 13%) [Enter for model default 8%]: ",
            default=""
        )
        forecast_growth = 0.08
        if g_input:

            try:
                forecast_growth = parse_growth_rate(g_input, default=0.08)
                security.qualitative["forecast_growth"] = forecast_growth
                print(f"  Using forecast growth: {forecast_growth:.1%}\n")
            except ValueError as e:
                print(f"  Invalid input: {e} — using model default.\n")

        # Print Assumption Table
        wacc = security.qualitative.get("wacc_override", 0.09)
        terminal_growth = security.qualitative.get("forecast_terminal_growth", 0.025)
        print_assumption_table(forecast_growth, wacc, terminal_growth)

        print("-" * 70)
        print("  RUNNING 7-STAGE VALUATION PIPELINE")
        print("-" * 70)

        # Compute multi-lens synthesis for Master Arbitration Layer
        synthesis_upside = None
        try:
            lens_results = [
                RateSensitiveLens().compute(security),
                PlatformCompounderLens().compute(security),
                ExpectationsDifficultyLens().compute(security),
                DamodaranEngine().compute(security),
            ]
            synthesis = synthesize_lenses(lens_results)
            synthesis_upside = synthesis.weighted_implied_move_pct
        except Exception:
            # If synthesis fails, pipeline still works with traditional signals only
            pass

        # Run pipeline with arbitration layer
        pipeline = ValuationPipeline()
        report = pipeline.run(security, synthesis_upside=synthesis_upside)
        print(report.explain())

    except ImportError:
        print("  ERROR: yfinance is not installed.")
        print("  Install with: pip install -e '.[live]'")
    except RuntimeError as e:
        print(f"  ERROR: Could not fetch data for '{ticker}'.")
        print(f"  Details: {e}")
    except Exception as e:
        print(f"  ERROR: {e}")


def run_factor_scoring(ticker: str) -> None:
    """Run factor scoring on a single security."""
    print("\n" + "-" * 70)
    print(f"  Fetching {ticker} from Yahoo Finance...")
    try:
        from iam import score
        from iam.data.yahoo import fetch_security

        security = fetch_security(ticker)
        print(f"  ✓ {security.name or ticker} loaded")
        print()

        print("-" * 70)
        print("  FACTOR SCORING RESULTS")
        print("-" * 70)
        result = score(security)
        print(result.explain())

    except ImportError:
        print("  ERROR: yfinance is not installed.")
        print("  Install with: pip install -e '.[live]'")
    except RuntimeError as e:
        print(f"  ERROR: Could not fetch data for '{ticker}'.")
        print(f"  Details: {e}")
    except Exception as e:
        print(f"  ERROR: {e}")


def run_thesis_engine(ticker: str) -> None:
    """Run thesis engine with Bayesian updating."""
    print("\n" + "-" * 70)
    print(f"  Fetching {ticker} from Yahoo Finance...")
    try:
        from iam.data.security import Assumption, Thesis
        from iam.data.yahoo import fetch_security
        from iam.thesis.bayesian.priors import ScenarioPrior
        from iam.thesis.engine import ThesisEngine

        security = fetch_security(ticker)
        print(f"  ✓ {security.name or ticker} loaded")
        print()

        # Prompt for bull/base/bear case prices
        print("  Define your investment thesis:")
        print()

        bull_low = float(safe_input("    Bull case fair value low: $", default="100"))
        bull_high = float(safe_input("    Bull case fair value high: $", default="150"))
        bear_low = float(safe_input("    Bear case fair value low: $", default="50"))
        bear_high = float(safe_input("    Bear case fair value high: $", default="80"))
        print()

        security.theses = [
            Thesis(
                label="Bull",
                fair_value_low=bull_low,
                fair_value_high=bull_high,
                narrative="Optimistic scenario",
                assumptions=[
                    Assumption("bull_case", bull_high, source="user"),
                ],
            ),
            Thesis(
                label="Bear",
                fair_value_low=bear_low,
                fair_value_high=bear_high,
                narrative="Pessimistic scenario",
                assumptions=[
                    Assumption("bear_case", bear_low, source="user"),
                ],
            ),
        ]

        engine = ThesisEngine()
        evaluation = engine.evaluate(security)

        print("-" * 70)
        print("  THESIS ANALYSIS")
        print("-" * 70)
        print(f"  Fair value range: ${evaluation.worst_case:.2f} – ${evaluation.best_case:.2f}")
        print(f"  Expected value: ${evaluation.expected_value:.2f}")
        print()

    except ValueError:
        print("  ERROR: Invalid input. Please enter numeric values.")
    except ImportError:
        print("  ERROR: yfinance is not installed.")
        print("  Install with: pip install -e '.[live]'")
    except RuntimeError as e:
        print(f"  ERROR: Could not fetch data for '{ticker}'.")
        print(f"  Details: {e}")
    except Exception as e:
        print(f"  ERROR: {e}")


def run_backtest_harness() -> None:
    """Run the backtest harness for factor analysis."""
    print("\n" + "-" * 70)
    print("  BACKTEST HARNESS")
    print("-" * 70)
    print()
    print("  The backtest harness evaluates factor performance against")
    print("  historical forward returns. You'll need to provide:")
    print("    - Point-in-time security data (fundamentals + market)")
    print("    - Forward returns (1M, 3M, etc.)")
    print()
    print("  Example usage:")
    print()
    print("    from tests.harness import BacktestHarness")
    print("    from iam.data.security import Security")
    print()
    print("    # Load your historical data")
    print("    data = [(Security(...), fwd_return), ...]")
    print()
    print("    harness = BacktestHarness(data)")
    print("    results = harness.run()")
    print("    ics = harness.calculate_ic()")
    print("    spread = harness.quantile_spread(q=5)")
    print()
    print("  For detailed documentation, see: docs/")
    print()


def run_quick_recommendation(ticker: str) -> None:
    """Run quick BUY/HOLD/SELL recommendation."""
    print("\n" + "-" * 70)
    print(f"  Quick Recommendation for {ticker}")
    print("-" * 70)
    print()

    try:
        from iam.data.yahoo import fetch_security
        from iam.pipeline.orchestrator import ValuationPipeline

        security = fetch_security(ticker)
        print(f"  ✓ {security.name or ticker} loaded\n")

        # Get forecast growth
        growth_input = safe_input("  Forecast growth [press Enter for 8%]: ", default="")
        forecast_growth = 0.08
        if growth_input:
            try:
                g = float(growth_input)
                forecast_growth = g / 100 if g > 1 else g
            except ValueError:
                print("  ⚠ Invalid input, using 8%\n")

        security.qualitative["forecast_growth"] = forecast_growth

        # Run pipeline
        print("  ⏳ Analyzing...\n")
        pipeline = ValuationPipeline()
        report = pipeline.run(security)

        # Show recommendation box
        if report.final_verdict:
            rating = report.final_verdict.rating
            confidence = report.final_verdict.confidence_band
            upside = report.final_verdict.blended_upside or report.implied_move_pct or 0
        else:
            rating = "INCONCLUSIVE"
            confidence = "LOW"
            upside = 0

        fair_value = (security.market.price or 0) * (1 + upside)

        # Print recommendation
        print("  " + "╔" + "═" * 68 + "╗")
        print(f"  ║  {rating:20} │ Confidence: {confidence:15} ║")
        print("  " + "║" + "─" * 68 + "║")
        print(
            f"  ║  Current: ${security.market.price:>8.2f}  │  Fair Value: ${fair_value:>8.2f}  │  Upside: {upside:>6.1%}  ║"
        )
        print("  " + "╚" + "═" * 68 + "╝")
        print()

        # Interpretation
        if rating == "BUY":
            print("  🟢 Stock appears undervalued with >15% potential upside\n")
        elif rating == "SELL":
            print("  🔴 Stock appears overvalued with >10% potential downside\n")
        else:
            print("  🟡 Stock appears fairly valued within -10% to +15% range\n")

        # Ask for details
        print()
        details = safe_input("  View detailed analysis? (y/n): ", default="n").lower()
        if details == "y":
            print("\n" + "-" * 70)
            print("  DETAILED VALUATION PIPELINE")
            print("-" * 70 + "\n")
            print(report.explain(verbose=False))

    except ImportError:
        print("  ERROR: yfinance is not installed.")
        print("  Install with: pip install -e '.[live]'")
    except RuntimeError as e:
        print(f"  ERROR: Could not fetch data for '{ticker}'.")
        print(f"  Details: {e}")
    except Exception as e:
        print(f"  ERROR: {e}")


def main() -> None:
    """Main interactive loop."""
    print_header()
    print("  Welcome! This tool helps you analyze equities using the")
    print("  Institutional Alpha Model (IAM) framework.")
    print()

    while True:
        print_menu()
        choice = safe_input("Enter your choice (1-6): ", default="6").strip()

        if choice == "1":
            ticker = get_security_input()
            run_quick_recommendation(ticker)
        elif choice == "2":
            ticker = get_security_input()
            run_valuation_pipeline(ticker)
        elif choice == "3":
            ticker = get_security_input()
            run_factor_scoring(ticker)
        elif choice == "4":
            ticker = get_security_input()
            run_thesis_engine(ticker)
        elif choice == "5":
            run_backtest_harness()
        elif choice == "6":
            print("  Thank you for using IAM. Goodbye!")
            sys.exit(0)
        else:
            print("  Invalid choice. Please enter 1-6.\n")
            continue

        # Ask if user wants to analyze another security
        print()
        again = safe_input("Analyze another security? (y/n): ", default="n").lower()
        if again != "y":
            print("  Thank you for using IAM. Goodbye!")
            sys.exit(0)
        print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  Interrupted. Goodbye!")
        sys.exit(0)
    except Exception as e:
        print(f"\n  Unexpected error: {e}")
        sys.exit(1)

