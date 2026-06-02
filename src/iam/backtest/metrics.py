"""Institutional backtest metrics using Spearman rank correlation.

Information Coefficient measures the predictive power of a signal:
- IC > 0.02: Statistically significant
- IC > 0.05: Economically meaningful
- IC > 0.10: Excellent signal
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.stats import norm, spearmanr


def information_coefficient(df: pd.DataFrame, sector_col: str | None = None) -> float:
    """Calculate Spearman rank correlation between scores and forward returns.

    Can compute global IC or sector-neutral IC (averaged across sectors).

    Args:
        df: DataFrame with columns 'score' (model signal) and 'fwd' (forward return)
        sector_col: If provided, compute sector-neutral IC instead of global IC

    Returns:
        Spearman rank correlation coefficient, or NaN if insufficient data
    """
    if sector_col and sector_col in df.columns:
        return ic_sector_neutral(df, sector_col=sector_col)

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


def rolling_ic_stability(ic_series: pd.Series, window: int = 12) -> pd.Series:
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


def statistical_significance(ic_mean: float, ic_std: float, n: int) -> dict:
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


def newey_west_se(ic_mean: float, ic_std: float, n: int, nlags: int = 3) -> float:
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


def newey_west_se_rigorous(ic_series: pd.Series, nlags: int = 3) -> tuple[float, float, float]:
    """Compute rigorous Newey-West standard error using statsmodels HAC covariance.

    Args:
        ic_series: Time series of Information Coefficient values
        nlags: Number of lags for HAC covariance

    Returns:
        Tuple of (t_stat, p_value, se) where:
        - t_stat: t-statistic for mean = 0
        - p_value: Two-tailed p-value
        - se: Newey-West adjusted standard error
    """
    ic_clean = ic_series.dropna().values

    if len(ic_clean) < nlags + 2:
        return np.nan, 1.0, np.nan

    # Regress IC series on constant
    X = sm.add_constant(np.ones(len(ic_clean)))
    model = sm.OLS(ic_clean, X).fit(cov_type="HAC", cov_kwds={"maxlags": nlags})

    t_stat = model.tvalues[0]  # t-stat for the constant (mean)
    p_value = 2 * (1 - norm.cdf(abs(t_stat)))  # Two-tailed

    se = float(model.bse[0])  # Standard error from HAC

    return t_stat, p_value, se


def ic_value_weighted(
    df: pd.DataFrame,
    mcap_col: str = "market_cap",
    score_col: str = "score",
    fwd_col: str = "fwd",
) -> float:
    """Value-weighted rank IC: weighted Spearman between composite score and forward return.

    Ranks both series then computes the weighted Pearson correlation of those ranks,
    using market cap as weights. This tells you whether the signal holds in names
    where you can actually deploy real size, not just in micro-caps.

    Falls back to equal-weighted Spearman when market cap data is unavailable.
    """
    valid = df[[score_col, fwd_col]].copy()
    if mcap_col in df.columns:
        valid[mcap_col] = df[mcap_col]
        valid = valid.dropna()
    else:
        valid = valid.dropna()

    if len(valid) < 5:
        return np.nan

    # Rank both series (average ties)
    rank_score = valid[score_col].rank(method="average")
    rank_fwd = valid[fwd_col].rank(method="average")

    if mcap_col in valid.columns and valid[mcap_col].sum() > 0:
        w = valid[mcap_col].values.astype(float)
        w = w / w.sum()
        mu_s = np.dot(w, rank_score.values)
        mu_f = np.dot(w, rank_fwd.values)
        cov = np.dot(w, (rank_score.values - mu_s) * (rank_fwd.values - mu_f))
        var_s = np.dot(w, (rank_score.values - mu_s) ** 2)
        var_f = np.dot(w, (rank_fwd.values - mu_f) ** 2)
        if var_s <= 0 or var_f <= 0:
            return np.nan
        return float(cov / np.sqrt(var_s * var_f))

    # No market cap — fall back to equal-weight Spearman
    corr, _ = spearmanr(rank_score, rank_fwd, nan_policy="omit")
    return corr


def ic_sector_neutral(df: pd.DataFrame, sector_col: str = "sector") -> float:
    """Calculate sector-neutral Information Coefficient.

    Computes IC within each sector separately, then returns weighted average.
    This removes sector allocation beta from the IC calculation.

    Args:
        df: DataFrame with columns 'score' (model signal), 'fwd' (forward return), and sector_col
        sector_col: Name of sector column

    Returns:
        Weighted average sector-neutral IC, or NaN if insufficient data
    """
    if sector_col not in df.columns:
        return np.nan

    ics = []
    weights = []

    for sector, group in df.groupby(sector_col):
        if len(group) > 5:  # Require at least 5 securities per sector
            ic = information_coefficient(group)
            if not np.isnan(ic):
                ics.append(ic)
                weights.append(len(group))

    if not ics:
        return np.nan

    # Weighted average
    return np.average(ics, weights=weights)


def fisher_mean(correlations: np.ndarray) -> float:
    """Calculate mean of correlations using Fisher z-transformation.

    Proper way to average Spearman correlations that may include negative values.

    Args:
        correlations: Array of correlation coefficients (between -1 and 1)

    Returns:
        Fisher z-transformed mean, transformed back to correlation scale
    """
    # Clip to prevent arctanh overflow
    correlations = np.clip(correlations, -0.999, 0.999)

    # Fisher z-transformation
    z = np.arctanh(correlations)

    # Average in z-space
    z_mean = np.nanmean(z)

    # Inverse transformation
    return np.tanh(z_mean)
