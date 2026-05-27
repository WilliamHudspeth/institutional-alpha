#!/usr/bin/env python3
"""Interactive main menu for the IAM framework.

A user-friendly entry point that guides you through:
  - Factor scoring across multiple securities
  - Detailed valuation pipeline on a single name
  - Thesis engine with scenario analysis
  - Backtest harness for factor efficacy evaluation
"""

from __future__ import annotations

import sys
import re
import json
import urllib.parse
import urllib.request

from iam.validation import parse_growth_rate, validate_all_assumptions


def print_header() -> None:
    """Print the main welcome banner."""
    from iam.version import header, metadata
    print(header())
    meta = metadata()
    print(f"Python {meta['python']} | Research Preview\n")


def print_menu() -> None:
    """Print the main menu options."""
    print("What would you like to do?\n")
    print("  1. Value a single security (7-stage pipeline)")
    print("  2. Score a security (10 factors + 3 penalties)")
    print("  3. Scenario analysis with thesis engine")
    print("  4. Backtest factor efficacy (historical analysis)")
    print("  5. Exit")
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
        query = input("Enter a ticker symbol or company name: ").strip()

        if not query:
            print("  No input provided. Please try again.")
            continue

        # Try to resolve the ticker
        ticker, resolved_name = resolve_ticker(query)

        if not validate_ticker(ticker):
            print(
                f"  '{query}' could not be resolved to a valid ticker. "
                "Please try again."
            )
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
        from iam.pipeline.orchestrator import ValuationPipeline, print_assumption_table
        from iam.lenses.rate_sensitive import RateSensitiveLens
        from iam.lenses.platform_compounder import PlatformCompounderLens
        from iam.lenses.expectations_difficulty import ExpectationsDifficultyLens
        from iam.lenses.damodaran_base import DamodaranBaseLens
        from iam.lenses.synthesis import synthesize_lenses

        security = fetch_security(ticker)
        print(f"  ✓ {security.name or ticker} loaded")
        print()

        # Optional growth override
        g_input = input(
            "  Forecast growth (e.g. 13 or 0.13 for 13%) [Enter for model default 8%]: "
        ).strip()
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
                DamodaranBaseLens().compute(security),
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
        from iam.data.yahoo import fetch_security
        from iam import score

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
        from iam.data.yahoo import fetch_security
        from iam.data.security import Assumption, Thesis
        from iam.thesis.engine import ThesisEngine
        from iam.thesis.bayesian.priors import ScenarioPrior

        security = fetch_security(ticker)
        print(f"  ✓ {security.name or ticker} loaded")
        print()

        # Prompt for bull/base/bear case prices
        print("  Define your investment thesis:")
        print()

        bull_low = float(input("    Bull case fair value low: $"))
        bull_high = float(input("    Bull case fair value high: $"))
        bear_low = float(input("    Bear case fair value low: $"))
        bear_high = float(input("    Bear case fair value high: $"))
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


def main() -> None:
    """Main interactive loop."""
    print_header()
    print("  Welcome! This tool helps you analyze equities using the")
    print("  Institutional Alpha Model (IAM) framework.")
    print()

    while True:
        print_menu()
        choice = input("Enter your choice (1-5): ").strip()

        if choice == "1":
            ticker = get_security_input()
            run_valuation_pipeline(ticker)
        elif choice == "2":
            ticker = get_security_input()
            run_factor_scoring(ticker)
        elif choice == "3":
            ticker = get_security_input()
            run_thesis_engine(ticker)
        elif choice == "4":
            run_backtest_harness()
        elif choice == "5":
            print("  Thank you for using IAM. Goodbye!")
            sys.exit(0)
        else:
            print("  Invalid choice. Please enter 1-5.\n")
            continue

        # Ask if user wants to analyze another security
        print()
        again = input("Analyze another security? (y/n): ").strip().lower()
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
