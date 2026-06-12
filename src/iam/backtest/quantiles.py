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


def quantile_turnover(
    df_current: pd.DataFrame,
    df_previous: pd.DataFrame,
    n_deciles: int = 10,
) -> float:
    """Calculate turnover between two time periods (fraction of holdings that changed).

    Args:
        df_current: Current date decile assignments
        df_previous: Previous date decile assignments
        n_deciles: Number of quantiles

    Returns:
        Fraction of holdings that changed decile (0 to 1)
    """
    # Assign deciles
    try:
        df_current = df_current.copy()
        df_previous = df_previous.copy()

        df_current["decile"] = pd.qcut(
            df_current["score"], n_deciles, labels=False, duplicates="drop"
        )
        df_previous["decile"] = pd.qcut(
            df_previous["score"], n_deciles, labels=False, duplicates="drop"
        )
    except ValueError:
        return float(np.nan)

    # Find common tickers
    if "ticker" not in df_current.index.names:
        current_tickers = set(df_current.index)
        previous_tickers = set(df_previous.index)
    else:
        current_tickers = set(df_current.index.get_level_values("ticker"))
        previous_tickers = set(df_previous.index.get_level_values("ticker"))

    common = current_tickers & previous_tickers

    if not common:
        return float(np.nan)

    # Compare decile assignments
    changed = 0
    for ticker in common:
        if "ticker" in df_current.index.names:
            curr_dec = df_current.loc[ticker, "decile"]
            prev_dec = df_previous.loc[ticker, "decile"]
        else:
            curr_dec = df_current.loc[ticker, "decile"]
            prev_dec = df_previous.loc[ticker, "decile"]

        if pd.notna(curr_dec) and pd.notna(prev_dec) and curr_dec != prev_dec:
            changed += 1

    return changed / len(common)


def spread_after_costs(
    spread: float,
    turnover: float,
    cost_bps: float = 5.0,
) -> float:
    """Adjust spread for transaction costs.

    Args:
        spread: Raw decile spread (top - bottom return)
        turnover: Fraction of holdings that changed (0-1)
        cost_bps: Transaction cost per round-trip in basis points

    Returns:
        Spread minus transaction cost drag
    """
    if np.isnan(spread) or np.isnan(turnover):
        return float(np.nan)

    # Cost = turnover * cost_bps / 10000 * 2 (buy + sell)
    cost = turnover * (cost_bps / 10000) * 2

    return spread - cost
