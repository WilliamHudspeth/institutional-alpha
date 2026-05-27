"""Backtest runner: Monthly loop that evaluates value_ticker on historical snapshots.

This is the read-only consumer of the institutional alpha stack. It treats
value_ticker() as a black box and never touches data or valuation internals.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import pandas as pd

from iam.api import value_security, Security
from iam.backtest.calibration import summarize_backtest, write_calibration
from iam.backtest.metrics import information_coefficient, hit_rate, information_ratio
from iam.backtest.prices import get_price_block
from iam.backtest.quantiles import decile_spread, quantile_spread_by_date
from iam.backtest.snapshots import build_snapshot, load_snapshot


def run_backtest(
    universe: list[Security],
    dates: list[str],  # YYYY-MM-DD format, month-ends preferred
    horizon_days: int = 63,
    score_field: str = "cost_of_equity",  # or "blended_upside"
) -> pd.DataFrame:
    """Run historical backtest on value_ticker.

    Evaluates each security in the universe on each date, scores them,
    and calculates Information Coefficient vs forward returns.

    Args:
        universe: List of base Security objects (with fundamentals, sector, etc.)
        dates: List of evaluation dates (YYYY-MM-DD)
        horizon_days: Forward return horizon
        score_field: Which output to use as the signal

    Returns:
        DataFrame with columns:
        - date: Evaluation date
        - ic: Information Coefficient (Spearman rank)
        - hit_rate: Fraction of positive returns where score > median
        - spread: Decile spread (top 10% - bottom 10% average return)
        - coverage: Fraction of tickers with decile assignments
    """
    tickers = [s.ticker for s in universe]

    # Download price block once (read-only)
    print(f"Downloading prices for {len(tickers)} tickers from {dates[0]} to {dates[-1]}...")
    price_block = get_price_block(
        tickers,
        dates[0],
        dates[-1],
        horizon_days=horizon_days,
    )

    results = []

    for date_idx, date in enumerate(dates, 1):
        print(f"[{date_idx}/{len(dates)}] Evaluating {date}...")

        scores = {}

        for base in universe:
            try:
                # Build PIT snapshot (cached)
                snapshot = load_snapshot(base.ticker, date)
                if snapshot is None:
                    snapshot = build_snapshot(base, date)

                # Evaluate using the full stack (black box)
                result = value_security(snapshot)

                # Extract score (could be cost_of_equity, blended_upside, etc.)
                if score_field in result:
                    score = result[score_field]
                else:
                    # Fallback: use the primary model result value
                    score = result.get("model_result", {}).get("value", 0.0)

                scores[base.ticker] = score

            except Exception as e:
                print(f"  Warning: {base.ticker} failed - {e}")
                continue

        # Get forward returns for this date
        try:
            fwd = price_block.xs(date, level="date")["fwd_ret"]
        except KeyError:
            print(f"  No price data for {date}")
            continue

        # Build score/return dataframe
        common_tickers = set(scores.keys()) & set(fwd.index)
        if len(common_tickers) < 10:
            print(f"  Insufficient overlap: {len(common_tickers)} tickers")
            continue

        df = pd.DataFrame({
            "score": [scores[t] for t in sorted(common_tickers)],
            "fwd": [fwd[t] for t in sorted(common_tickers)],
        })

        # Calculate metrics
        ic = information_coefficient(df)
        hr = hit_rate(df)
        spreads = decile_spread(df)

        results.append({
            "date": date,
            "ic": ic,
            "hit_rate": hr,
            "spread": spreads["spread"],
            "top": spreads["top"],
            "bottom": spreads["bottom"],
            "coverage": spreads["coverage"],
            "n_securities": len(common_tickers),
        })

    if not results:
        raise ValueError("No valid backtest results generated")

    results_df = pd.DataFrame(results)
    results_df["date"] = pd.to_datetime(results_df["date"])
    results_df = results_df.set_index("date")

    return results_df


def print_backtest_summary(results_df: pd.DataFrame) -> None:
    """Print institutional backtest summary."""
    summary = summarize_backtest(results_df)

    print("\n" + "=" * 70)
    print("BACKTEST SUMMARY")
    print("=" * 70)
    print(f"IC Mean:           {summary['ic_mean']:+.4f}")
    print(f"IC Std:            {summary['ic_std']:.4f}")
    print(f"IC IR:             {summary['icir']:.2f}")
    print(f"Hit Rate:          {summary['hit_rate']:.1%}")
    print(f"Decile Spread:     {summary['spread_mean']:+.2%}")
    print(f"Top Decile Return: {summary['top_decile_mean']:+.2%}")
    print(f"Bot Decile Return: {summary['bottom_decile_mean']:+.2%}")
    print("=" * 70)

    return summary
