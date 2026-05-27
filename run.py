#!/usr/bin/env python3
"""Interactive CLI for the multi-lens valuation engine.

Run from the repo root:
    python run.py
"""

from __future__ import annotations

import sys

from iam.validation import parse_growth_rate, validate_all_assumptions


def _print_security_header(security) -> None:
    print(f"  {security.name or security.ticker}")
    if security.sector:
        print(f"  Sector: {security.sector}  |  Industry: {security.industry or 'n/a'}")
    if security.market.price is not None:
        print(f"  Current price: {security.market.price:.2f}")
    missing = []
    if security.fundamentals.fcf_ttm is None:
        missing.append("FCF TTM")
    if security.fundamentals.shares_outstanding is None:
        missing.append("shares outstanding")
    if missing:
        print(f"  WARNING: missing data — {', '.join(missing)}. DCF lenses will be skipped.")


def main() -> None:
    from iam.version import header, metadata
    print(header())
    meta = metadata()
    print(f"Multi-Lens Valuation Engine | Python {meta['python']}\n")

    ticker = input("Ticker symbol: ").strip().upper()
    if not ticker:
        print("No ticker entered. Exiting.")
        sys.exit(0)

    # -------------------------------------------------------------------------
    # Fetch live data
    # -------------------------------------------------------------------------
    print(f"\nFetching {ticker} from Yahoo Finance...")
    try:
        from iam.data.yahoo import fetch_security
        security = fetch_security(ticker)
    except ImportError as exc:
        print(f"\nERROR: {exc}")
        sys.exit(1)
    except RuntimeError as exc:
        print(f"\nERROR: {exc}")
        sys.exit(1)
    except Exception as exc:
        print(f"\nUnexpected error: {exc}")
        sys.exit(1)

    print()
    _print_security_header(security)
    print()

    # Optional growth override
    g_input = input(
        "Forecast growth for DCF lenses (e.g. 13 or 0.13 for 13%) [Enter for model default 8%]: "
    ).strip()
    if g_input:
        try:
            growth = parse_growth_rate(g_input, default=0.08)
            security.qualitative["forecast_growth"] = growth
            print(f"  Using forecast growth: {growth:.1%}")
        except ValueError as e:
            print(f"  Invalid input: {e} — using model default.")
    print()

    # -------------------------------------------------------------------------
    # Valuation pipeline (Stages 1-7)
    # -------------------------------------------------------------------------
    print("-" * 60)
    print("  VALUATION PIPELINE (Stages 1-7)")
    print("-" * 60)
    try:
        from iam.pipeline.orchestrator import ValuationPipeline
        report = ValuationPipeline().run(security)
        print(report.explain())
    except Exception as exc:
        print(f"  Pipeline error: {exc}")
    print()

    # -------------------------------------------------------------------------
    # Multi-lens analysis
    # -------------------------------------------------------------------------
    print("-" * 60)
    print("  MULTI-LENS ANALYSIS")
    print("-" * 60)
    try:
        from iam.lenses.rate_sensitive import RateSensitiveLens
        from iam.lenses.platform_compounder import PlatformCompounderLens
        from iam.lenses.expectations_difficulty import ExpectationsDifficultyLens
        from iam.lenses.damodaran_base import DamodaranBaseLens
        from iam.lenses.synthesis import synthesize_lenses

        lens_results = [
            RateSensitiveLens().compute(security),
            PlatformCompounderLens().compute(security),
            ExpectationsDifficultyLens().compute(security),
            DamodaranBaseLens().compute(security),
        ]

        for lr in lens_results:
            lo = f"{lr.fair_value_low:.2f}" if lr.fair_value_low is not None else "—"
            hi = f"{lr.fair_value_high:.2f}" if lr.fair_value_high is not None else "—"
            move = f"{lr.implied_move_pct:+.1%}" if lr.implied_move_pct is not None else "diagnostic only"
            print(f"\n  [{lr.lens_name}]  conf: {lr.confidence:.2f}")
            print(f"    Range: {lo} – {hi}   Implied move: {move}")
            print(f"    {lr.narrative}")

        synthesis = synthesize_lenses(lens_results)
        print()
        print("-" * 40)
        print("  WEIGHTED SYNTHESIS (pricing lenses only)")
        if synthesis.weighted_fair_value_low is not None:
            print(f"    Low:  {synthesis.weighted_fair_value_low:.2f}")
            print(f"    High: {synthesis.weighted_fair_value_high:.2f}")
        if synthesis.weighted_implied_move_pct is not None:
            direction = "upside" if synthesis.weighted_implied_move_pct >= 0 else "downside"
            print(f"    Implied move: {synthesis.weighted_implied_move_pct:+.1%} ({direction})")
        else:
            print("    No pricing lenses produced a result.")

    except Exception as exc:
        print(f"  Lens analysis error: {exc}")

    print()
    print("Done.")


if __name__ == "__main__":
    main()
