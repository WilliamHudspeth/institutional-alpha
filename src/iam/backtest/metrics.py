"""Institutional backtest metrics using Spearman rank correlation.

Information Coefficient measures the predictive power of a signal:
- IC > 0.02: Statistically significant
- IC > 0.05: Economically meaningful
- IC > 0.10: Excellent signal
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import spearmanr


def information_coefficient(df: pd.DataFrame) -> float:
    """Calculate Spearman rank correlation between scores and forward returns.

    Args:
        df: DataFrame with columns 'score' (model signal) and 'fwd' (forward return)

    Returns:
        Spearman rank correlation coefficient, or NaN if insufficient data
    """
    if df["score"].nunique() < 2:
        return np.nan

    corr, _ = spearmanr(df["score"], df["fwd"], nan_policy="omit")
    return corr


def hit_rate(df: pd.DataFrame) -> float:
    """Fraction of positive forward returns where score > median.

    Simple proxy for directional accuracy.
    """
    median_score = df["score"].median()
    long_case = df[df["score"] > median_score]

    if len(long_case) == 0:
        return np.nan

    positive_returns = (long_case["fwd"] > 0).sum()
    return positive_returns / len(long_case)


def information_ratio(ic_series: pd.Series) -> float:
    """Calculate Information Ratio = mean(IC) / std(IC).

    Measures consistency of the signal over time.
    """
    mean_ic = ic_series.mean()
    std_ic = ic_series.std()

    if std_ic == 0:
        return 0.0

    return mean_ic / std_ic


def rolling_ic_stability(
    ic_series: pd.Series, window: int = 12
) -> pd.Series:
    """Calculate rolling IC to detect regime shifts.

    Args:
        ic_series: Series of monthly IC values
        window: Rolling window (months)

    Returns:
        Series of rolling correlation between time and IC
    """
    rolling = ic_series.rolling(window).apply(
        lambda x: np.corrcoef(np.arange(len(x)), x)[0, 1], raw=False
    )
    return rolling


def statistical_significance(
    ic_mean: float, ic_std: float, n: int
) -> dict:
    """Calculate t-stat and p-value for IC.

    Args:
        ic_mean: Mean Information Coefficient
        ic_std: Standard deviation of IC
        n: Number of observations

    Returns:
        Dict with t-stat, p-value, and significance flag
    """
    from scipy import stats

    if ic_std == 0 or n < 2:
        return {
            "t_stat": 0.0,
            "p_value": 1.0,
            "newey_west_se": ic_std,
            "significant": False,
        }

    # Standard error (will be adjusted with Newey-West below)
    se = ic_std / np.sqrt(n)
    t_stat = ic_mean / se

    # Two-tailed test
    p_value = 2 * (1 - stats.t.cdf(abs(t_stat), n - 1))

    # Newey-West adjustment for overlapping returns
    nw_se = newey_west_se(ic_mean, ic_std, n, nlags=3)
    nw_t_stat = ic_mean / nw_se if nw_se > 0 else 0.0

    return {
        "t_stat": t_stat,
        "newey_west_t_stat": nw_t_stat,
        "p_value": p_value,
        "newey_west_se": nw_se,
        "significant": abs(nw_t_stat) > 2.0,  # 95% confidence
    }


def newey_west_se(
    ic_mean: float, ic_std: float, n: int, nlags: int = 3
) -> float:
    """Newey-West standard error for autocorrelated returns.

    Corrects for autocorrelation from overlapping return windows
    (63-day forward returns have built-in autocorrelation).

    Args:
        ic_mean: Mean IC
        ic_std: Std dev of IC
        n: Number of observations
        nlags: Number of lags for autocorrelation adjustment

    Returns:
        Adjusted standard error
    """
    # Simplified: multiply by sqrt(1 + 2 * rho)
    # where rho is average autocorrelation at each lag
    # For 63-day overlapping windows, typical rho ~ 0.3-0.4
    # Conservative estimate: assume rho ~ 0.35
    rho_avg = 0.35 * nlags  # Simplified autocorrelation estimate

    adjustment_factor = np.sqrt(1 + 2 * rho_avg)
    base_se = ic_std / np.sqrt(n)

    return base_se * adjustment_factor
