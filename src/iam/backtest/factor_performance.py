"""Per-factor performance tracking and stability analysis.

Decomposes backtest IC into individual factor contributions, tracks rolling
IC by factor, and detects regime-dependent performance shifts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


@dataclass
class FactorMetrics:
    """Performance metrics for a single factor."""

    factor_name: str
    ic_mean: float
    ic_std: float
    information_ratio: float
    hit_rate: float
    rolling_ic_trend: float  # Correlation of rolling IC with time
    regime_correlation: Optional[dict] = None  # regime → IC


def compute_factor_ic(
    factor_scores: pd.Series, forward_returns: pd.Series
) -> float:
    """Compute Information Coefficient for a factor.

    Args:
        factor_scores: Series of factor values (ranks are computed internally)
        forward_returns: Series of forward-looking returns

    Returns:
        Spearman rank correlation between factor and returns
    """
    from scipy.stats import spearmanr

    common_idx = factor_scores.index.intersection(forward_returns.index)
    if len(common_idx) < 2:
        return np.nan

    scores = factor_scores.loc[common_idx]
    returns = forward_returns.loc[common_idx]

    # Drop NaNs
    valid_mask = scores.notna() & returns.notna()
    scores = scores[valid_mask]
    returns = returns[valid_mask]

    if len(scores) < 2:
        return np.nan

    ic, _ = spearmanr(scores, returns)
    return ic if not np.isnan(ic) else 0.0


def decompose_backtest_by_factor(
    backtest_results: pd.DataFrame,
    factor_rankings: dict[str, pd.DataFrame],
) -> dict[str, FactorMetrics]:
    """Decompose overall backtest IC into per-factor contributions.

    Args:
        backtest_results: DataFrame with dates as index, tickers as columns (forward returns)
        factor_rankings: Dict of {factor_name: DataFrame with tickers as index, dates as columns}

    Returns:
        Dict mapping factor names to FactorMetrics
    """
    metrics = {}

    for factor_name, factor_df in factor_rankings.items():
        # Extract factor scores and returns for each date
        factor_ics = []

        # Align dates between backtest results and factor rankings
        common_dates = backtest_results.index.intersection(factor_df.columns)

        for date in common_dates:
            if date not in backtest_results.index or date not in factor_df.columns:
                continue

            # Factor scores for this date (tickers)
            factor_scores = factor_df[date]

            # Forward returns for this date (tickers)
            forward_returns = backtest_results.loc[date]

            # Ensure both are Series with same index
            common_tickers = factor_scores.index.intersection(forward_returns.index)
            if len(common_tickers) < 2:
                continue

            factor_scores = factor_scores[common_tickers]
            forward_returns = forward_returns[common_tickers]

            # Compute IC for this factor on this date
            ic = compute_factor_ic(factor_scores, forward_returns)
            if not np.isnan(ic):
                factor_ics.append(ic)

        if len(factor_ics) < 2:
            continue

        factor_ics_series = pd.Series(factor_ics)
        ic_mean = factor_ics_series.mean()
        ic_std = factor_ics_series.std()
        ir = ic_mean / ic_std if ic_std > 0 else 0.0

        # Rolling IC trend (correlation with time)
        rolling_trend = (
            factor_ics_series.rolling(window=min(6, len(factor_ics_series)))
            .apply(lambda x: np.corrcoef(np.arange(len(x)), x)[0, 1] if len(x) > 1 else 0)
            .mean()
        )

        metrics[factor_name] = FactorMetrics(
            factor_name=factor_name,
            ic_mean=ic_mean,
            ic_std=ic_std,
            information_ratio=ir,
            hit_rate=sum(1 for ic in factor_ics if ic > 0) / len(factor_ics),
            rolling_ic_trend=rolling_trend if not np.isnan(rolling_trend) else 0.0,
        )

    return metrics


def compute_factor_correlations(
    factor_rankings: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """Compute correlation matrix between factor rankings.

    Identifies redundant or highly correlated factors (low orthogonality).

    Args:
        factor_rankings: Dict of {factor_name: Series of ranks}

    Returns:
        Correlation matrix (factors × factors)
    """
    factor_data = {}

    for factor_name, factor_df in factor_rankings.items():
        # Stack all dates into one series, keeping ticker index
        factor_data[factor_name] = factor_df.unstack().dropna()

    if not factor_data:
        return pd.DataFrame()

    return pd.DataFrame(factor_data).corr()


def identify_regime_dependent_factors(
    factor_ic_series: dict[str, pd.Series],
    macro_regime_series: pd.Series,
) -> dict[str, float]:
    """Identify which factors are most sensitive to macro regime changes.

    Args:
        factor_ic_series: Dict of {factor_name: Series of IC values by date}
        macro_regime_series: Series of regime labels (e.g., 0, 1, 2, 3)

    Returns:
        Dict mapping factor names to regime sensitivity (correlation with regime changes)
    """
    sensitivities = {}

    for factor_name, ic_series in factor_ic_series.items():
        common_dates = ic_series.index.intersection(macro_regime_series.index)

        if len(common_dates) < 3:
            continue

        ic_aligned = ic_series.loc[common_dates].values
        regime_aligned = macro_regime_series.loc[common_dates].values

        # Correlation between factor IC and regime
        if len(ic_aligned) > 1 and ic_aligned.std() > 0:
            corr = np.corrcoef(ic_aligned, regime_aligned)[0, 1]
            sensitivities[factor_name] = corr if not np.isnan(corr) else 0.0

    return sensitivities


def generate_factor_report(metrics: dict[str, FactorMetrics]) -> str:
    """Generate a text report of factor performance.

    Args:
        metrics: Dict of factor name → FactorMetrics

    Returns:
        Formatted text report
    """
    lines = [
        "=" * 80,
        "FACTOR PERFORMANCE REPORT",
        "=" * 80,
        "",
        f"{'Factor':<30} {'IC Mean':>12} {'IC Std':>12} {'IR':>10} {'Hit Rate':>10}",
        "-" * 80,
    ]

    # Sort by IR (descending)
    sorted_factors = sorted(
        metrics.values(), key=lambda m: m.information_ratio, reverse=True
    )

    for metric in sorted_factors:
        lines.append(
            f"{metric.factor_name:<30} {metric.ic_mean:>12.4f} {metric.ic_std:>12.4f} "
            f"{metric.information_ratio:>10.2f} {metric.hit_rate:>10.1%}"
        )

    lines.extend(
        [
            "=" * 80,
            "",
        ]
    )

    return "\n".join(lines)
