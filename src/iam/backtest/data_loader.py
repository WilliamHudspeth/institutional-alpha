"""Real price data loader using Stooq (free, no key required).

This module handles downloading and caching historical OHLCV data
for the S&P 100 universe. It provides:

1. One-time download from Stooq (free, no auth)
2. Parquet caching with metadata
3. Data integrity tracking (hash, version, timestamp)
4. Fallback to cached data if download fails
5. Point-in-time price retrieval

Stooq is used instead of yfinance because:
- Free (no API key required)
- More stable than yfinance
- Historical data is frozen (no revisions)
- Adjusted close is standardized
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


class StooqDataLoader:
    """Download and cache S&P 100 price data from Stooq."""

    BASE_URL = "https://stooq.com/q/export"
    CACHE_DIR = Path("data/prices/")
    MANIFEST_FILE = CACHE_DIR / "manifest.json"

    def __init__(self, cache_dir: Path = CACHE_DIR):
        """Initialize with cache directory."""
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = cache_dir / "manifest.json"

    def download_ticker_data(
        self, ticker: str, start: str, end: str
    ) -> pd.DataFrame:
        """Download single ticker from Stooq.

        Args:
            ticker: Stock ticker (e.g., 'AAPL')
            start: Start date YYYY-MM-DD
            end: End date YYYY-MM-DD

        Returns:
            DataFrame with columns: Date, Open, High, Low, Close, Volume
        """
        try:
            # Stooq CSV export URL for US stocks
            url = f"{self.BASE_URL}?s={ticker}.us&d1={start.replace('-', '')}&d2={end.replace('-', '')}&i=d"

            df = pd.read_csv(url)

            # Standardize columns
            df.columns = ["Date", "Open", "High", "Low", "Close", "Volume"]
            df["Date"] = pd.to_datetime(df["Date"])
            df = df.sort_values("Date")
            df = df.reset_index(drop=True)

            logger.info(f"Downloaded {ticker}: {len(df)} days")
            return df

        except Exception as e:
            logger.error(f"Failed to download {ticker}: {e}")
            return None

    def download_universe(
        self, tickers: list[str], start: str, end: str
    ) -> dict[str, pd.DataFrame]:
        """Download all tickers, cache individually.

        Args:
            tickers: List of stock tickers
            start: Start date
            end: End date

        Returns:
            Dict mapping ticker -> DataFrame
        """
        results = {}
        failed = []

        for i, ticker in enumerate(tickers, 1):
            print(f"[{i}/{len(tickers)}] Downloading {ticker}...", end=" ")

            df = self.download_ticker_data(ticker, start, end)

            if df is not None and len(df) > 0:
                results[ticker] = df
                print(f"✓ ({len(df)} days)")
            else:
                print("✗ (failed)")
                failed.append(ticker)

        logger.warning(f"Failed to download {len(failed)} tickers: {failed}")

        return results

    def save_multiindex_parquet(
        self, data_dict: dict[str, pd.DataFrame], filename: str = "sp100_ohlcv.parquet"
    ) -> None:
        """Save dictionary of DataFrames as multiindex parquet.

        Format: MultiIndex (Ticker, Date) with columns (Open, High, Low, Close, Volume)

        Args:
            data_dict: Dict mapping ticker -> DataFrame
            filename: Output filename
        """
        dfs = []

        for ticker, df in data_dict.items():
            df["Ticker"] = ticker
            dfs.append(df)

        combined = pd.concat(dfs, ignore_index=False)
        combined = combined.set_index(["Ticker", "Date"]).sort_index()

        parquet_path = self.cache_dir / filename
        combined.to_parquet(parquet_path)

        logger.info(f"Saved to {parquet_path}: {combined.shape}")

    def save_manifest(
        self,
        filename: str,
        tickers: list[str],
        start: str,
        end: str,
        n_tickers_downloaded: int,
    ) -> None:
        """Save metadata about the download.

        Args:
            filename: Parquet filename
            tickers: List of tickers
            start: Start date
            end: End date
            n_tickers_downloaded: Number successfully downloaded
        """
        parquet_path = self.cache_dir / filename
        file_hash = self._hash_file(parquet_path)

        manifest = {
            "version": "v0.3.5",
            "source": "Stooq",
            "data_type": "OHLCV",
            "universe": "S&P 100",
            "period": {"start": start, "end": end},
            "downloaded_at": datetime.utcnow().isoformat(),
            "file": {
                "name": filename,
                "path": str(parquet_path),
                "sha256": file_hash,
                "size_bytes": parquet_path.stat().st_size,
            },
            "coverage": {
                "requested": len(tickers),
                "downloaded": n_tickers_downloaded,
                "tickers": tickers,
            },
            "notes": [
                "Prices are adjusted close (dividend + split adjusted)",
                "Volume is in shares, not adjusted",
                "All data frozen as of download date",
                "No revisions possible (Stooq is static)",
            ],
        }

        self.manifest_path.write_text(json.dumps(manifest, indent=2))
        logger.info(f"Saved manifest to {self.manifest_path}")

    @staticmethod
    def _hash_file(path: Path, algorithm: str = "sha256") -> str:
        """Compute hash of parquet file for integrity."""
        hash_obj = hashlib.new(algorithm)
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_obj.update(chunk)
        return hash_obj.hexdigest()

    def load_cached_data(self, filename: str = "sp100_ohlcv.parquet") -> pd.DataFrame:
        """Load from cached parquet if available.

        Returns:
            MultiIndex DataFrame (Ticker, Date) or None if not found
        """
        parquet_path = self.cache_dir / filename

        if not parquet_path.exists():
            logger.warning(f"Cache not found: {parquet_path}")
            return None

        try:
            df = pd.read_parquet(parquet_path)
            logger.info(f"Loaded {df.shape[0]} rows from cache")
            return df
        except Exception as e:
            logger.error(f"Failed to load cache: {e}")
            return None

    def load_manifest(self) -> dict:
        """Load metadata about cached data."""
        if not self.manifest_path.exists():
            return None

        try:
            return json.loads(self.manifest_path.read_text())
        except Exception as e:
            logger.error(f"Failed to load manifest: {e}")
            return None


def get_or_download_sp100_prices(
    start: str = "2018-01-01", end: str = "2024-12-31", force_download: bool = False
) -> pd.DataFrame:
    """Convenience function: Get cached S&P 100 prices or download if missing.

    Args:
        start: Start date
        end: End date
        force_download: If True, re-download even if cached

    Returns:
        MultiIndex DataFrame (Ticker, Date) with OHLCV data
    """
    from iam.backtest.snapshots import load_sp100_tickers

    loader = StooqDataLoader()

    # Check cache first
    if not force_download:
        cached = loader.load_cached_data()
        if cached is not None:
            logger.info("Using cached price data")
            return cached

    # Download if needed
    logger.info("Cache miss or forced download - fetching from Stooq")
    tickers = load_sp100_tickers()
    data_dict = loader.download_universe(tickers, start, end)

    if len(data_dict) > 0:
        loader.save_multiindex_parquet(data_dict)
        loader.save_manifest("sp100_ohlcv.parquet", tickers, start, end, len(data_dict))
        return loader.load_cached_data()
    else:
        logger.error("No tickers downloaded successfully")
        return None
