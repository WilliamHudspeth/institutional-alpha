"""Quantile analysis: decile spread between top and bottom performers.

This shows whether high scores actually predict positive returns.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def decile_spread(df: pd.DataFrame, n_deciles: int = 10) -> dict:
    """Calculate average forward return in top and bottom deciles.

    Args:
        df: DataFrame with 'score' and 'fwd' columns
        n_deciles: Number of quantiles (default 10 for deciles)

    Returns:
        Dict with:
        - top: Mean forward return of top decile
        - bottom: Mean forward return of bottom decile
        - spread: top - bottom
        - coverage: Fraction of securities in deciles (vs dropped due to ties)
    """
    df = df.copy()

    # Create deciles (handles ties by dropping)
    try:
        df["decile"] = pd.qcut(df["score"], n_deciles, labels=False, duplicates="drop")
    except ValueError:
        # If too few unique scores for n_deciles
        return {
            "top": np.nan,
            "bottom": np.nan,
            "spread": np.nan,
            "coverage": 0.0,
        }

    n_with_decile = df["decile"].notna().sum()
    coverage = n_with_decile / len(df)

    if n_with_decile < 2:
        return {
            "top": np.nan,
            "bottom": np.nan,
            "spread": np.nan,
            "coverage": coverage,
        }

    max_decile = df["decile"].max()
    min_decile = df["decile"].min()

    top = df[df["decile"] == max_decile]["fwd"].mean()
    bottom = df[df["decile"] == min_decile]["fwd"].mean()

    return {
        "top": top if not np.isnan(top) else np.nan,
        "bottom": bottom if not np.isnan(bottom) else np.nan,
        "spread": (top - bottom) if not (np.isnan(top) or np.isnan(bottom)) else np.nan,
        "coverage": coverage,
    }


def quantile_spread_by_date(df: pd.DataFrame, n_deciles: int = 10) -> pd.DataFrame:
    """Calculate decile spread for each date in a time series."""
    results = []

    for date, group in df.groupby(level="date"):
        spreads = decile_spread(group, n_deciles=n_deciles)
        spreads["date"] = date
        results.append(spreads)

    if not results:
        return pd.DataFrame()

    return pd.DataFrame(results).set_index("date")
