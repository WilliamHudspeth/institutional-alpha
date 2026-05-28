"""Backtest runner: Monthly loop with parallel scoring via ProcessPoolExecutor.

This is the read-only consumer of the institutional alpha stack. It treats
value_security() as a black box and never touches data or valuation internals.
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd
from tqdm import tqdm

from iam.api import Security, value_security
from iam.backtest.calibration import summarize_backtest
from iam.backtest.metrics import hit_rate, information_coefficient
from iam.backtest.quantiles import decile_spread
from iam.backtest.snapshots import build_snapshot, load_snapshot


def _score_security_worker(
    base: Security,
    as_of: str,
    score_field: str,
    cache_dir: Path = Path(".cache/snapshots"),
) -> tuple[str, float, str]:
    """Worker function for ProcessPoolExecutor to score one security at one date.

    Args:
        base: Base Security object
        as_of: Evaluation date (YYYY-MM-DD)
        score_field: Field to extract from value_security result
        cache_dir: Cache directory for snapshots

    Returns:
        Tuple of (ticker, score, sector)
    """
    try:
        # Try cached snapshot first
        snapshot = load_snapshot(base.ticker, as_of, cache_dir=cache_dir)
        if snapshot is None:
            snapshot = build_snapshot(base, as_of, cache_dir=cache_dir)

        # The composite multi-factor score is the alpha signal we validate.
        # Other fields (e.g. cost_of_equity) are risk metrics, not signals.
        if score_field == "composite":
            from iam.engine.composite import score as composite_score

            score = composite_score(snapshot).composite
            return base.ticker, score, base.sector

        # Evaluate using the full stack (black box)
        result = value_security(snapshot)

        # Extract score
        if score_field in result:
            score = result[score_field]
        else:
            score = result.get("model_result", {}).get("value", 0.0)

        return base.ticker, score, base.sector

    except Exception:
        # Return NaN score on failure
        return base.ticker, float("nan"), base.sector


def run_backtest(
    universe: list[Security],
    dates: list[str],  # YYYY-MM-DD format, month-ends preferred
    price_block: pd.DataFrame,  # Pre-loaded price block (date, ticker) MultiIndex
    config: object | None = None,
    score_field: str = "composite",
) -> pd.DataFrame:
    """Run historical backtest with parallel scoring.

    Args:
        universe: List of base Security objects
        dates: List of evaluation dates (YYYY-MM-DD)
        price_block: Pre-loaded price block DataFrame with (date, ticker) index
        config: BacktestConfig with n_jobs_cpu and cache_dir
        score_field: Field to extract from value_security result

    Returns:
        DataFrame with columns: date, ic, ic_sector_neutral, hit_rate, spread, top, bottom, coverage, n_securities
    """
    n_jobs_cpu = getattr(config, "n_jobs_cpu", 4) if config else 4
    cache_dir = (
        getattr(config, "snapshot_cache", Path(".cache/snapshots"))
        if config
        else Path(".cache/snapshots")
    )

    if hasattr(price_block, "to_pandas"):
        price_block = price_block.to_pandas()
    if isinstance(price_block.index, pd.MultiIndex):
        price_block = price_block.reset_index()
    if "date" in price_block.columns:
        price_block = price_block.copy()
        price_block["date"] = pd.to_datetime(price_block["date"]).dt.strftime("%Y-%m-%d")
        price_block = price_block.set_index(["date", "ticker"])

    results = []

    with ProcessPoolExecutor(max_workers=n_jobs_cpu) as executor:
        for date in tqdm(dates, desc="Backtesting"):
            try:
                futures = [
                    executor.submit(_score_security_worker, base, date, score_field, cache_dir)
                    for base in universe
                ]

                scores = {}
                sectors = {}
                for future in futures:
                    ticker, score, sector = future.result()
                    scores[ticker] = score
                    sectors[ticker] = sector

            except Exception as e:
                print(f"Warning: Parallel scoring failed on {date}: {e}")
                continue

            # Get forward returns for this date
            try:
                fwd = price_block.xs(date, level="date")["fwd_ret"]
            except KeyError:
                continue

            # Build score/return dataframe with sector column
            common_tickers = [t for t in scores.keys() if t in fwd.index and not pd.isna(scores[t])]
            if len(common_tickers) < 10:
                continue

            df = pd.DataFrame(
                {
                    "ticker": common_tickers,
                    "score": [scores[t] for t in common_tickers],
                    "fwd": [fwd[t] for t in common_tickers],
                    "sector": [sectors[t] for t in common_tickers],
                }
            )

            # Calculate metrics
            ic = information_coefficient(df)
            ic_sn = (
                information_coefficient(df, sector_col="sector") if "sector" in df.columns else ic
            )
            hr = hit_rate(df)
            spreads = decile_spread(df)

            results.append(
                {
                    "date": date,
                    "ic": ic,
                    "ic_sector_neutral": ic_sn,
                    "hit_rate": hr,
                    "spread": spreads["spread"],
                    "top": spreads["top"],
                    "bottom": spreads["bottom"],
                    "coverage": spreads["coverage"],
                    "n_securities": len(common_tickers),
                }
            )

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
