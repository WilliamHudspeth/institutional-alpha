#!/usr/bin/env python3
"""Helper script to build price parquet file with forward returns pre-computed.

This script downloads OHLCV data from yfinance (or Stooq as fallback),
computes forward returns, and caches to parquet for fast backtest loading.

Usage:
    python scripts/build_price_parquet.py --start 2018-01-01 --end 2024-12-31 --horizon 63
"""

import hashlib
import json
from datetime import datetime

import pandas as pd
import polars as pl
import typer

from iam.backtest.config import BacktestConfig
from iam.backtest.sources import build_tiered_source
from iam.backtest.universe import load_universe_tickers

app = typer.Typer()


@app.command()
def build_prices(
    start: str = typer.Option("2018-01-01", "--start", help="Start date (YYYY-MM-DD)"),
    end: str = typer.Option("2024-12-31", "--end", help="End date (YYYY-MM-DD)"),
    horizon: int = typer.Option(63, "--horizon", help="Forward return horizon (days)"),
    verbose: bool = typer.Option(False, "--verbose", help="Verbose output"),
):
    """Download prices and build parquet with forward returns pre-computed."""
    typer.echo("📦 Building price parquet...")
    typer.echo()

    config = BacktestConfig(start=start, end=end, horizon_days=horizon)
    config.validate_paths()

    # Load tickers
    typer.echo(f"📋 Loading tickers from {config.universe_file}...")
    try:
        tickers = load_universe_tickers(config.universe_file)
        typer.echo(f"   ✓ {len(tickers)} tickers")
    except FileNotFoundError as e:
        typer.echo(f"   ✗ {e}", err=True)
        raise typer.Exit(1)

    typer.echo()

    # Download prices via the tiered data source chain.
    # Per-ticker so one ticker's failure can't abort the whole batch, and so
    # each row's serving source is recorded for the provenance/audit trail.
    chain = build_tiered_source()
    typer.echo(f"📊 Downloading {len(tickers)} tickers via {chain!r}...")
    # Extend download window to cover all horizons, not just the primary one.
    max_horizon = max(config.horizons_days + [horizon])
    end_with_horizon = (pd.Timestamp(end) + pd.Timedelta(days=max_horizon)).strftime("%Y-%m-%d")

    rows = []
    errors = []
    source_counts: dict[str, int] = {}

    for ticker in typer.progressbar(tickers, label="Downloading", show_pos=True, show_percent=True):
        try:
            df = chain.download_history(ticker, start, end_with_horizon)
        except Exception as e:
            if verbose:
                typer.echo(f"      {ticker}: {e}")
            errors.append((ticker, f"unexpected error: {e}"))
            continue
        if df is None or df.empty or "Close" not in df.columns:
            errors.append((ticker, "no data from any source"))
            continue
        used = chain.last_used or "unknown"
        source_counts[used] = source_counts.get(used, 0) + 1
        out = pd.DataFrame(
            {
                "date": df["Date"].dt.strftime("%Y-%m-%d"),
                "ticker": ticker,
                "close": df["Close"].astype(float),
            }
        ).dropna(subset=["close"])
        rows.extend(out.to_dict("records"))

    if not rows:
        typer.echo("✗ No price data downloaded from any source", err=True)
        raise typer.Exit(1)

    data_source = "+".join(sorted(source_counts)) or "none"
    typer.echo(
        f"   ✓ {len(rows)} records from {data_source} "
        f"(by source: {source_counts}); {len(errors)} tickers failed"
    )

    typer.echo()

    # Convert to Polars and compute forward returns
    typer.echo("📈 Computing forward returns...")
    df_pl = pl.DataFrame(rows)
    df_pl = df_pl.with_columns(
        pl.col("date").str.to_date(),
    )

    # Sort by ticker and date for computing returns
    df_pl = df_pl.sort(["ticker", "date"])

    # Compute one forward-return column per horizon.
    # fwd_ret_{H}d = price[t+H] / price[t] - 1.
    # fwd_ret is kept as an alias for the primary horizon.
    all_horizons = sorted(set(config.horizons_days + [horizon]))
    horizon_exprs = [
        pl.col("close")
        .shift(-h)
        .over("ticker")
        .truediv(pl.col("close"))
        .sub(1)
        .alias(f"fwd_ret_{h}d")
        for h in all_horizons
    ]
    df_pl = df_pl.with_columns(horizon_exprs)
    # Primary alias so existing consumers reading "fwd_ret" keep working.
    df_pl = df_pl.with_columns(pl.col(f"fwd_ret_{horizon}d").alias("fwd_ret"))

    # Filter to evaluation period (exclude forward period)
    df_pl = df_pl.filter(pl.col("date") <= end)

    typer.echo(f"   ✓ {len(df_pl)} rows with forward returns")

    typer.echo()

    # Write parquet
    typer.echo(f"💾 Writing parquet to {config.price_file}...")
    config.price_file.parent.mkdir(parents=True, exist_ok=True)
    df_pl.write_parquet(config.price_file)

    # Compute file hash
    file_hash = hashlib.sha256(config.price_file.read_bytes()).hexdigest()[:12]

    typer.echo(f"   ✓ Parquet written (hash: {file_hash})")

    typer.echo()

    # Write manifest
    typer.echo("📋 Writing manifest...")
    manifest = {
        "_meta": {
            "version": "v0.4.0-rc1",
            "timestamp": datetime.utcnow().isoformat(),
            "data_source": data_source,
            "source_breakdown": source_counts,
        },
        "config": {
            "start": start,
            "end": end,
            "horizon_days": horizon,
            "all_horizons_days": all_horizons,
        },
        "data": {
            "file_path": str(config.price_file),
            "file_hash": file_hash,
            "n_rows": len(df_pl),
            "n_unique_dates": df_pl["date"].n_unique(),
            "n_unique_tickers": df_pl["ticker"].n_unique(),
            "date_range": [
                df_pl["date"].min().isoformat(),
                df_pl["date"].max().isoformat(),
            ],
        },
        "errors": [{"ticker": t, "reason": r} for t, r in errors],
    }

    manifest_path = config.price_file.parent / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    typer.echo(f"   ✓ Manifest written to {manifest_path}")

    typer.echo()
    typer.echo("✓ Price parquet build complete!")
    if errors:
        typer.echo(f"   ⚠️  {len(errors)} tickers failed")


if __name__ == "__main__":
    app()
