#!/usr/bin/env python3
"""Helper script to build price parquet file with forward returns pre-computed.

This script downloads OHLCV data from yfinance (or Stooq as fallback),
computes forward returns, and caches to parquet for fast backtest loading.

Usage:
    python scripts/build_price_parquet.py --start 2018-01-01 --end 2024-12-31 --horizon 63
"""

import typer
import pandas as pd
import polars as pl
from pathlib import Path
from datetime import datetime
import json
import hashlib

try:
    import yfinance as yf

    HAS_YFINANCE = True
except ImportError:
    HAS_YFINANCE = False

from iam.backtest.config import BacktestConfig
from iam.backtest.universe import load_universe_tickers
from iam.backtest.data_loader import StooqDataLoader

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

    # Download prices (yfinance primary, Stooq fallback)
    typer.echo(f"📊 Downloading {len(tickers)} tickers from {start} to {end}...")
    end_with_horizon = (pd.Timestamp(end) + pd.Timedelta(days=horizon)).strftime("%Y-%m-%d")

    rows = []
    errors = []

    # Try yfinance first
    if HAS_YFINANCE:
        typer.echo("   Trying yfinance (primary)...")
        try:
            data = yf.download(
                tickers,
                start=start,
                end=end_with_horizon,
                progress=not verbose,
                auto_adjust=True,
            )

            # Handle single ticker case
            if isinstance(data, pd.Series):
                data = data.to_frame(name="Close")

            if isinstance(data.columns, pd.MultiIndex):
                # Multi-ticker case
                closes = data["Close"]
            else:
                # Single ticker
                closes = data[["Close"]]
                closes.columns = tickers

            # Reshape to long format
            closes = closes.reset_index()
            closes = closes.melt(id_vars=["Date"], var_name="ticker", value_name="close")
            closes = closes.dropna(subset=["close"])
            closes["date"] = closes["Date"].dt.date
            closes = closes[["date", "ticker", "close"]].copy()

            rows.extend(closes.to_dict("records"))
            typer.echo(f"   ✓ yfinance succeeded: {len(rows)} records")
            data_source = "yfinance"

        except Exception as e:
            typer.echo(f"   ⚠️  yfinance failed: {e}")
            data_source = "stooq"

    # Fallback to Stooq if yfinance failed
    if not rows or not HAS_YFINANCE:
        typer.echo("   Trying Stooq (fallback)...")
        loader = StooqDataLoader()

        for ticker in typer.progressbar(
            tickers, label="Downloading", show_pos=True, show_percent=True
        ):
            try:
                df = loader.download_ticker_data(ticker, start, end_with_horizon)
                df = df.reset_index()
                df.columns = ["date", "open", "high", "low", "close", "volume"]
                df["ticker"] = ticker
                rows.extend(df[["date", "ticker", "close"]].to_dict("records"))
            except Exception as e:
                if verbose:
                    typer.echo(f"      {ticker}: {e}")
                errors.append((ticker, str(e)))

        typer.echo(f"   ✓ Stooq succeeded: {len(rows)} records, {len(errors)} errors")
        data_source = "stooq"

    if not rows:
        typer.echo("✗ No price data downloaded", err=True)
        raise typer.Exit(1)

    typer.echo()

    # Convert to Polars and compute forward returns
    typer.echo("📈 Computing forward returns...")
    df_pl = pl.DataFrame(rows)
    df_pl = df_pl.with_columns(
        pl.col("date").str.to_date(),
    )

    # Sort by ticker and date for computing returns
    df_pl = df_pl.sort(["ticker", "date"])

    # Compute forward return: price[t+horizon] / price[t] - 1
    df_pl = df_pl.with_columns(
        pl.col("close").shift(-horizon).over("ticker").truediv(pl.col("close")).sub(1).alias("fwd_ret")
    )

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
            "version": "v0.4.0",
            "timestamp": datetime.utcnow().isoformat(),
            "data_source": data_source,
        },
        "config": {
            "start": start,
            "end": end,
            "horizon_days": horizon,
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
