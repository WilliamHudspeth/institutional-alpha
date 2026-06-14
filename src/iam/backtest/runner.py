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
from iam.backtest.metrics import hit_rate, ic_value_weighted, information_coefficient
from iam.backtest.quantiles import decile_spread
from iam.backtest.snapshots import build_snapshot, load_snapshot


def _score_security_worker(
    base: Security,
    as_of: str,
    score_field: str,
    cache_dir: Path = Path(".cache/snapshots"),
) -> tuple[str, float, str | None, float | None]:
    """Worker function for ProcessPoolExecutor to score one security at one date.

    Args:
        base: Base Security object
        as_of: Evaluation date (YYYY-MM-DD)
        score_field: Field to extract from value_security result
        cache_dir: Cache directory for snapshots

    Returns:
        Tuple of (ticker, score, sector, market_cap)
    """
    try:
        # Try cached snapshot first
        snapshot = load_snapshot(base.ticker, as_of, cache_dir=cache_dir)
        if snapshot is None:
            snapshot = build_snapshot(base, as_of, cache_dir=cache_dir)

        market_cap = snapshot.market.market_cap if snapshot.market else None

        # The composite multi-factor score is the alpha signal we validate.
        # Other fields (e.g. cost_of_equity) are risk metrics, not signals.
        if score_field == "composite":
            from iam.engine.composite import score as composite_score

            score = composite_score(snapshot).composite
            return base.ticker, score, base.sector, market_cap

        # Evaluate using the full stack (black box)
        result = value_security(snapshot)

        # Extract score
        if score_field in result:
            score = result[score_field]
        else:
            score = result.get("model_result", {}).get("value", 0.0)

        return base.ticker, score, base.sector, market_cap

    except Exception:
        # Return NaN score on failure
        return base.ticker, float("nan"), base.sector, None


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
        DataFrame with columns: date, ic, ic_vw, ic_sector_neutral, hit_rate, spread, top,
        bottom, coverage, n_securities, plus ic_{H}d / ic_vw_{H}d columns for each horizon
        column found in the price block (e.g. ic_21d, ic_63d, ic_126d, ic_252d).
    """
    n_jobs_cpu = getattr(config, "n_jobs_cpu", 4) if config else 4
    cache_dir = (
        getattr(config, "snapshot_cache", Path(".cache/snapshots"))
        if config
        else Path(".cache/snapshots")
    )

    if hasattr(price_block, "to_pandas"):
        try:
            price_block = price_block.to_pandas()
        except Exception:
            price_block = pd.DataFrame(price_block.to_dicts())
    if isinstance(price_block.index, pd.MultiIndex):
        price_block = price_block.reset_index()
    if "date" in price_block.columns:
        price_block = price_block.copy()
        price_block["date"] = pd.to_datetime(price_block["date"]).dt.strftime("%Y-%m-%d")
        price_block = price_block.set_index(["date", "ticker"])

    # Discover which per-horizon columns are present (e.g. fwd_ret_21d).
    horizon_cols = sorted(
        [c for c in price_block.columns if c.startswith("fwd_ret_") and c.endswith("d")],
        key=lambda c: int(c[len("fwd_ret_") : -1]),
    )

    results = []

    with ProcessPoolExecutor(max_workers=n_jobs_cpu) as executor:
        for date in tqdm(dates, desc="Backtesting"):
            try:
                futures = [
                    executor.submit(_score_security_worker, base, date, score_field, cache_dir)
                    for base in universe
                ]

                scores: dict[str, float] = {}
                sectors: dict[str, str] = {}
                mcaps: dict[str, float | None] = {}
                for future in futures:
                    ticker, score, sector, market_cap = future.result()
                    scores[ticker] = score
                    sectors[ticker] = sector
                    mcaps[ticker] = market_cap

            except Exception as e:
                print(f"Warning: Parallel scoring failed on {date}: {e}")
                continue

            # Get primary forward returns for this date
            try:
                fwd = price_block.xs(date, level="date")["fwd_ret"]
            except KeyError:
                continue

            common_tickers = [t for t in scores.keys() if t in fwd.index and not pd.isna(scores[t])]
            if len(common_tickers) < 10:
                continue

            df = pd.DataFrame(
                {
                    "ticker": common_tickers,
                    "score": [scores[t] for t in common_tickers],
                    "fwd": [fwd[t] for t in common_tickers],
                    "sector": [sectors[t] for t in common_tickers],
                    "market_cap": [mcaps.get(t) for t in common_tickers],
                }
            )

            # Primary-horizon metrics (backward-compatible columns)
            ic = information_coefficient(df)
            ic_vw = ic_value_weighted(df)
            ic_sn = (
                information_coefficient(df, sector_col="sector") if "sector" in df.columns else ic
            )
            hr = hit_rate(df)
            spreads = decile_spread(df)

            row: dict = {
                "date": date,
                "ic": ic,
                "ic_vw": ic_vw,
                "ic_sector_neutral": ic_sn,
                "hit_rate": hr,
                "spread": spreads["spread"],
                "top": spreads["top"],
                "bottom": spreads["bottom"],
                "coverage": spreads["coverage"],
                "n_securities": len(common_tickers),
            }

            # Per-horizon IC columns: ic_21d, ic_vw_21d, ic_63d, ...
            date_slice = (
                price_block.xs(date, level="date")
                if date in price_block.index.get_level_values(0)
                else None
            )
            if date_slice is not None:
                for hcol in horizon_cols:
                    h_label = hcol[len("fwd_ret_") :]  # e.g. "21d"
                    if hcol not in date_slice.columns:
                        continue
                    h_fwd = date_slice[hcol]
                    h_tickers = [
                        t for t in common_tickers if t in h_fwd.index and not pd.isna(h_fwd.get(t))
                    ]
                    if len(h_tickers) < 10:
                        continue
                    h_df = pd.DataFrame(
                        {
                            "ticker": h_tickers,
                            "score": [scores[t] for t in h_tickers],
                            "fwd": [h_fwd[t] for t in h_tickers],
                            "market_cap": [mcaps.get(t) for t in h_tickers],
                        }
                    )
                    row[f"ic_{h_label}"] = information_coefficient(h_df)
                    row[f"ic_vw_{h_label}"] = ic_value_weighted(h_df)

            results.append(row)

    if not results:
        raise ValueError("No valid backtest results generated")

    results_df = pd.DataFrame(results)
    results_df["date"] = pd.to_datetime(results_df["date"])
    results_df = results_df.set_index("date")

    return results_df


def print_backtest_summary(results_df: pd.DataFrame) -> dict:
    """Print institutional backtest summary including multi-horizon IC table."""
    from iam.backtest.metrics import information_ratio, newey_west_se_rigorous

    summary = summarize_backtest(results_df)

    print("\n" + "=" * 70)
    print("BACKTEST SUMMARY — COMPOSITE SCORE")
    print("=" * 70)
    print(f"IC Mean:           {summary['ic_mean']:+.4f}")
    print(f"IC VW:             {results_df['ic_vw'].mean():+.4f}" if "ic_vw" in results_df else "")
    print(f"IC Std:            {summary['ic_std']:.4f}")
    print(f"IC IR:             {summary['icir']:.2f}")
    print(f"Hit Rate:          {summary['hit_rate']:.1%}")
    print(f"Decile Spread:     {summary['spread_mean']:+.2%}")
    print(f"Top Decile Return: {summary['top_decile_mean']:+.2%}")
    print(f"Bot Decile Return: {summary['bottom_decile_mean']:+.2%}")

    # Multi-horizon table
    horizon_cols = sorted(
        [
            c
            for c in results_df.columns
            if c.startswith("ic_") and c.endswith("d") and "_vw_" not in c
        ],
        key=lambda c: int(c[len("ic_") : -1]),
    )
    if horizon_cols:
        print()
        print(
            f"  {'Horizon':>8}  {'Mean IC':>8}  {'IC VW':>8}  {'ICIR':>6}  {'NW t-stat':>10}  {'Sig':>4}"
        )
        print("  " + "-" * 54)
        for hcol in horizon_cols:
            h_label = hcol[len("ic_") :]
            vw_col = f"ic_vw_{h_label}"
            series = results_df[hcol].dropna()
            if len(series) < 3:
                continue
            mean_ic = series.mean()
            icir = information_ratio(series)
            t_stat, _, _ = newey_west_se_rigorous(series, nlags=3)
            vw_mean = results_df[vw_col].mean() if vw_col in results_df else float("nan")
            sig = "**" if abs(t_stat) > 2.6 else ("*" if abs(t_stat) > 1.96 else "")
            print(
                f"  {h_label:>8}  {mean_ic:>+8.4f}  {vw_mean:>+8.4f}  {icir:>6.2f}  {t_stat:>10.2f}  {sig:>4}"
            )

    # Print Research Validation block
    from iam.engine.composite import DEFAULT_WEIGHTS
    from iam.backtest.multiple_testing import compute_validation_metrics
    factor_names = list(DEFAULT_WEIGHTS.keys())
    val = compute_validation_metrics(results_df, factor_names)

    print("\nResearch Validation")
    print("-------------------")
    print(f"PSR:                      {val.psr:.4f}" if not np.isnan(val.psr) else "PSR:                      N/A")
    print(f"DSR:                      {val.dsr:.4f}" if not np.isnan(val.dsr) else "DSR:                      N/A")
    print(f"PBO:                      {val.pbo:.4f}" if not np.isnan(val.pbo) else "PBO:                      N/A")
    print(f"SPA p-value:              {val.spa_pvalue:.4f}" if not np.isnan(val.spa_pvalue) else "SPA p-value:              N/A")
    print(f"Effective Tests:          {val.effective_tests:.2f}" if not np.isnan(val.effective_tests) else "Effective Tests:          N/A")
    print(f"FWER Significant Factors: {val.fwer_significant_factors}")
    print(f"FDR Significant Factors:  {val.fdr_significant_factors}")

    print("=" * 70)
    return summary
