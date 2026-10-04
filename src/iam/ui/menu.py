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
import sys
import urllib.parse
import urllib.request

from iam.data.http import safe_urlopen
from iam.ui.term import clear_screen
from iam.validation import parse_growth_rate


def fmt_pct_or_na(value: float | None, digits: int = 2) -> str:
    """Format a fraction as a percentage, or ``n/a`` when it is missing."""
    if value is None:
        return "n/a"
    return f"{value * 100:.{digits}f}%"


def format_assumption_lines(
    qualitative: dict,
    forecast_growth: float,
    growth_from_user: bool,
) -> str:
    """Pre-run assumption summary with the source of every number.

    Defaults come from ``FCFEAssumptions`` (the engine's documented model
    defaults). The discount rate is not fixed here: the pipeline computes it
    (dynamic WACC / CAPM) unless the user supplied ``forecast_discount_rate``.
    """
    from iam.valuation.fcfe_dcf import FCFEDCF

    d = FCFEDCF().defaults
    terminal = qualitative.get("forecast_terminal_growth")
    rate = qualitative.get("forecast_discount_rate")
    g_src = "user input" if growth_from_user else "model default (FCFEAssumptions)"
    t_src = "supplied" if terminal is not None else "model default (FCFEAssumptions)"
    r_text = (
        f"{fmt_pct_or_na(rate)} (supplied)"
        if rate is not None
        else "computed by the pipeline (dynamic WACC / CAPM); shown in the results"
    )
    return "\n".join(
        [
            " [ CORE ASSUMPTIONS ]",
            f"   - Forecast Growth : {fmt_pct_or_na(forecast_growth, 1)} [{g_src}]",
            f"   - Terminal Growth : {fmt_pct_or_na(terminal if terminal is not None else d.terminal_growth, 1)} [{t_src}]",
            f"   - Discount Rate   : {r_text}",
            f"   - DCF Horizon     : {d.high_growth_years} years [model default (FCFEAssumptions)]",
        ]
    )


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
    from iam.version import VERSION

    # Clear console for immersive dedicated retro terminal experience
    clear_screen()

    print("┌" + "─" * 78 + "┐")
    print("│  ALPHA-TERMINAL // SYSTEM CONSOLE // COGNITIVE MULTI-FACTOR EQUITIES PLATFORM │")
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
    print("  6. Settings / System Administration")
    print("  7. Exit")
    print()


def resolve_ticker(query: str) -> tuple[str, str | None]:
    """Attempt to resolve a company name to a ticker using Yahoo Finance search."""
    try:
        safe_query = urllib.parse.quote(query)
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={safe_query}&quotesCount=1&newsCount=0"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with safe_urlopen(req, timeout=5) as response:
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
    """Validate ticker format using strict centralized guards."""
    from iam.validation import validate_ticker as strict_validate

    try:
        strict_validate(ticker)
        return True
    except ValueError:
        return False


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
        from iam.arbitration.reliability_loader import get_reliabilities, is_empirical_calibration
        from iam.data.providers.yfinance_adapter import fetch_security
        from iam.engine.damodaran import DamodaranEngine
        from iam.lenses.expectations_difficulty import ExpectationsDifficultyLens
        from iam.lenses.platform_compounder import PlatformCompounderLens
        from iam.lenses.rate_sensitive import RateSensitiveLens
        from iam.lenses.synthesis import synthesize_lenses
        from iam.pipeline.orchestrator import ValuationPipeline

        security = fetch_security(ticker)
        print(f"  ✓ {security.name or ticker} loaded")
        print()

        # Optional growth override
        from iam.valuation.fcfe_dcf import FCFEDCF

        default_growth = FCFEDCF().defaults.high_growth
        g_input = safe_input(
            "  Forecast growth (e.g. 13 or 0.13 for 13%) "
            f"[Enter for model default {default_growth:.0%}]: ",
            default="",
        )
        forecast_growth = default_growth
        growth_from_user = False
        if g_input:
            try:
                forecast_growth = parse_growth_rate(g_input, default=default_growth)
                from iam.validation import validate_growth_rate

                validate_growth_rate(forecast_growth, growth_type="forecast")
                security.qualitative["forecast_growth"] = forecast_growth
                growth_from_user = True
                print(f"  Using forecast growth: {forecast_growth:.1%}\n")
            except ValueError as e:
                forecast_growth = default_growth
                print(f"  Invalid input: {e} — using model default.\n")

        # Print Assumption Table
        print(format_assumption_lines(security.qualitative, forecast_growth, growth_from_user))

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
            reliabilities = get_reliabilities() if is_empirical_calibration() else None
            synthesis = synthesize_lenses(lens_results, reliabilities=reliabilities)
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
        from iam.data.providers.yfinance_adapter import fetch_security

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
        from iam.data.providers.yfinance_adapter import fetch_security
        from iam.data.security import Assumption, Thesis
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
                    Assumption(name="bull_case", value=bull_high, source="user"),
                ],
            ),
            Thesis(
                label="Bear",
                fair_value_low=bear_low,
                fair_value_high=bear_high,
                narrative="Pessimistic scenario",
                assumptions=[
                    Assumption(name="bear_case", value=bear_low, source="user"),
                ],
            ),
        ]

        engine = ThesisEngine()
        evaluation = engine.evaluate(security)

        print("-" * 70)
        print("  THESIS ANALYSIS")
        print("-" * 70)
        print(f"  Fair value range: ${evaluation.worst_case:.2f} – ${evaluation.best_case:.2f}")
        expected = (
            f"${evaluation.expected_value:.2f}" if evaluation.expected_value is not None else "N/A"
        )
        print(f"  Expected value: {expected}")
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
        from iam.data.providers.yfinance_adapter import fetch_security
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
        if rating == "STRONG_BUY":
            print("  🔥 High conviction! Stock is deeply undervalued with strong fundamentals.\n")
        elif rating == "BUY":
            print("  🟢 Stock appears undervalued with >15% potential upside\n")
        elif rating == "SPECULATIVE_BUY":
            print(
                "  🟣 Speculative Buy: Intrinsic value is high, but market expectations are also very rich.\n"
            )
        elif rating == "SELL":
            print("  🔴 Stock appears overvalued with >10% potential downside\n")
        else:
            print("  🟡 Stock appears fairly valued within -10% to +15% range\n")

        if report.battlefield:
            # Shift the summary slightly right for alignment if needed, or just print
            for line in report.battlefield.summary().split("\n"):
                print(f"  {line}")
            print()

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


def run_settings_menu() -> None:
    """Run the Settings / System Administration submenu."""
    from iam.config.credentials import configure_interactive, status

    while True:
        clear_screen()

        print("┌" + "─" * 78 + "┐")
        print("│  ALPHA-TERMINAL // SETTINGS & SYSTEM ADMINISTRATION                         │")
        print("└" + "─" * 78 + "┘")
        print("What would you like to configure?\n")

        # Check credentials status for suggestions
        st = status()
        missing_premium = not st["fmp"]["configured"] or not st["tiingo"]["configured"]
        if missing_premium:
            print("  * Suggestion: Set up free data API keys (FMP/Tiingo) for premium data. *")
            print()

        print("  1. Generate Desktop Shortcut / Launcher")
        print("  2. Manage Data API Keys (Credentials Wizard)")
        print("  3. Run GroundTruth Calibration (Link IC to Reliability)")
        print("  4. Back to Main Menu")
        print()

        choice = safe_input("Enter choice (1-4): ", default="4").strip()
        if choice == "1":
            from scripts.create_shortcut import create_shortcut

            print()
            success, msg = create_shortcut()
            if success:
                print(f"  ✅ {msg}")
            else:
                print(f"  ❌ Failed: {msg}")
            safe_input("\nPress Enter to return to Settings...")
        elif choice == "2":
            configure_interactive()
            safe_input("\nPress Enter to return to Settings...")
        elif choice == "3":
            from iam.validation.ground_truth import run_calibration

            run_calibration()
            safe_input("\nPress Enter to return to Settings...")
        elif choice == "4":
            break


def main() -> None:
    """Main interactive loop."""
    print_header()
    print("  Welcome! This tool helps you analyze equities using the")
    print("  Institutional Alpha Model (IAM) framework.")
    print()

    while True:
        print_menu()
        choice = safe_input("Enter your choice (1-7): ", default="7").strip()

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
            run_settings_menu()
        elif choice == "7":
            print("  Thank you for using IAM. Goodbye!")
            sys.exit(0)
        else:
            print("  Invalid choice. Please enter 1-7.\n")
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
