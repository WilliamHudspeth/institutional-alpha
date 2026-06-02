#!/usr/bin/env python
"""First production backtest: S&P 100, 2018-01 to 2024-12, 63-day horizon.

This backtest measures empirical Information Coefficient (Spearman rank
correlation) between the cost_of_equity signal and forward returns over
84 months. The IC values are then calibrated to reliability weights
[0.5, 0.95] for use in the Bayesian arbitration layer.

Run time: ~5-10 minutes (depending on cache hits and network)
Output: results_df.csv, calibrated_reliabilities.json
"""

import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

from iam.api import Security
from iam.backtest import (
    print_backtest_summary,
    run_backtest,
    write_calibration,
)


def load_sp100_universe() -> list[Security]:
    """Load static S&P 100 universe (frozen Dec 31, 2024)."""
    universe_path = Path("data/universe/sp100.json")

    with open(universe_path) as f:
        config = json.load(f)

    tickers = config["tickers"]
    print(f"Loaded {len(tickers)} tickers from S&P 100 universe")
    print(f"Universe frozen: {config['date_frozen']}")

    # Create minimal Security objects (orchestrator fetches fundamentals)
    securities = [Security(ticker=t, sector="", industry="", country_iso="US") for t in tickers]

    return securities


def generate_evaluation_dates(start: str, end: str, freq: str = "ME") -> list[str]:
    """Generate month-end evaluation dates between start and end (inclusive)."""
    dates = pd.date_range(start, end, freq=freq)
    return dates.strftime("%Y-%m-%d").tolist()


def main():
    """Run production backtest and generate calibration."""

    print("\n" + "=" * 70)
    print("INSTITUTIONAL ALPHA v0.3.5 — PRODUCTION BACKTEST")
    print("=" * 70)
    print()

    # Configuration
    start_date = "2018-01-31"
    end_date = "2024-12-31"
    horizon_days = 63
    score_field = "cost_of_equity"

    print(f"Universe:        S&P 100 (static, frozen 2024-12-31)")
    print(f"Period:          {start_date} to {end_date}")
    print(f"Frequency:       Monthly (month-end)")
    print(f"Horizon:         {horizon_days} days forward return")
    print(f"Score Field:     {score_field}")
    print()

    # Load universe
    print("Step 1: Loading S&P 100 universe...")
    universe = load_sp100_universe()
    print(f"  ✓ Loaded {len(universe)} securities")
    print()

    # Generate evaluation dates
    print("Step 2: Generating evaluation dates...")
    dates = generate_evaluation_dates(start_date, end_date, freq="ME")
    print(f"  ✓ Generated {len(dates)} monthly evaluation dates")
    print(f"  First:  {dates[0]}")
    print(f"  Last:   {dates[-1]}")
    print()

    # Run backtest
    print("Step 3: Running backtest (this may take 5-10 minutes)...")
    print("  Downloading price block for all tickers...")
    print("  Evaluating each security on each date...")
    print("  Calculating Information Coefficient for each month...")
    print()

    try:
        results_df = run_backtest(
            universe=universe,
            dates=dates,
            horizon_days=horizon_days,
            score_field=score_field,
        )

        print(f"  ✓ Backtest completed")
        print(f"  Results shape: {results_df.shape}")
        print(f"  Date range: {results_df.index.min()} to {results_df.index.max()}")
        print()

    except Exception as e:
        print(f"  ✗ Backtest failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)

    # Print summary
    print("Step 4: Summarizing results...")
    summary = print_backtest_summary(results_df)
    print()

    # Save results
    print("Step 5: Saving backtest results...")
    results_path = Path("backtest_results_v0.3.5.csv")
    results_df.to_csv(results_path)
    print(f"  ✓ Saved to {results_path}")
    print()

    # Write calibration
    print("Step 6: Writing calibration file...")

    # Map IC values by signal type (for now, just cost_of_equity)
    ic_by_signal = {
        "cost_of_equity": summary["ic_mean"],
    }

    calibration_path = Path("src/iam/arbitration/calibrated_reliabilities.json")
    write_calibration(
        ic_by_lens=ic_by_signal,
        output_path=calibration_path,
    )
    print()

    # Summary statistics
    print("=" * 70)
    print("BACKTEST SUMMARY")
    print("=" * 70)
    print(f"IC Mean:                {summary['ic_mean']:+.4f}")
    print(f"IC Std Dev:             {summary['ic_std']:.4f}")
    print(f"IC Information Ratio:   {summary['icir']:.2f}")
    print(f"Hit Rate:               {summary['hit_rate']:.1%}")
    print(f"Avg Decile Spread:      {summary['spread_mean']:+.2%}")
    print(f"Avg Top Decile Return:  {summary['top_decile_mean']:+.2%}")
    print(f"Avg Bot Decile Return:  {summary['bottom_decile_mean']:+.2%}")
    print("=" * 70)
    print()

    # Interpretation
    print("INTERPRETATION")
    print("=" * 70)
    ic_mean = summary["ic_mean"]

    if ic_mean > 0.05:
        signal_quality = "Economically Meaningful"
        color = "✓"
    elif ic_mean > 0.02:
        signal_quality = "Statistically Significant"
        color = "~"
    else:
        signal_quality = "Weak/No Signal"
        color = "✗"

    print(f"{color} Signal Quality: {signal_quality}")
    print(f"  IC = {ic_mean:.4f} (Spearman rank correlation)")
    print()

    if summary["icir"] > 1.0:
        consistency = "Consistent"
        print(f"✓ Consistency: {consistency}")
        print(f"  ICIR = {summary['icir']:.2f} (mean IC / std IC)")
    else:
        consistency = "Volatile"
        print(f"~ Consistency: {consistency}")
        print(f"  ICIR = {summary['icir']:.2f} (ratio of mean to volatility)")
    print()

    if summary["hit_rate"] > 0.55:
        direction = "Good directional accuracy"
        print(f"✓ Directionality: {direction}")
    elif summary["hit_rate"] > 0.5:
        direction = "Slight edge"
        print(f"~ Directionality: {direction}")
    else:
        direction = "No directional edge"
        print(f"✗ Directionality: {direction}")
    print(f"  Hit Rate = {summary['hit_rate']:.1%}")
    print()

    print("=" * 70)
    print()

    # Next steps
    print("NEXT STEPS (v0.3.5)")
    print("=" * 70)
    print()
    print("1. Review empirical IC and calibration")
    print(f"   - File: {calibration_path}")
    print("   - Verify IC values are reasonable (>0.02 for meaningful signal)")
    print()
    print("2. Integrate with MasterArbitrator")
    print("   - Load calibrated_reliabilities.json at import time")
    print("   - Use empirical IC weights in ModelResult blending")
    print("   - Feed IC back to Bayesian layer as institutional priors")
    print()
    print("3. Monitor out-of-sample IC (v0.3.6+)")
    print("   - Run monthly backtests on new data")
    print("   - Track IC stability over time")
    print("   - Only promote to production after 36+ months validation")
    print()
    print("4. Detect Damodaran baseline drift")
    print("   - Compare current Damodaran with historical versions")
    print("   - Adjust calibration if material changes")
    print()
    print("=" * 70)
    print()
    print("Backtest completed successfully.")


if __name__ == "__main__":
    main()
