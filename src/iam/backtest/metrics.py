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
