"""Backtest harness for the IAM framework.

Runs the scoring engine over a cross-section of point-in-time securities
and calculates Information Coefficient (IC) and quantile spreads against
forward returns.

Note: Requires pandas. Install with: pip install -e ".[data]"
"""

from collections.abc import Sequence

import pandas as pd

from iam import score
from iam.data.security import Security


class BacktestHarness:
    """Evaluates factor efficacy across a universe of historical data."""

    def __init__(self, data: Sequence[tuple[Security, float]]):
        """
        Args:
            data: A sequence of tuples containing a point-in-time Security
                  and its subsequent forward return (e.g., 1-month or 3-month).
        """
        self.data = data
        self.results_df: pd.DataFrame | None = None

    def run(self) -> pd.DataFrame:
        """Score all securities and return a DataFrame of all factor scores."""
        records = []
        for sec, fwd_ret in self.data:
            res = score(sec)

            # Base record with composite and forward return
            row = {
                "ticker": sec.ticker,
                "forward_return": fwd_ret,
                "composite": res.composite,
            }

            # Add individual factor contributions
            for fname, fcontrib in res.factor_breakdown.items():
                row[fname] = fcontrib.value

            for pname, pcontrib in res.penalties.items():
                # Penalties are tracked separately; store their raw values
                row[pname] = pcontrib.value

            records.append(row)

        self.results_df = pd.DataFrame(records)
        return self.results_df

    def calculate_ic(self) -> pd.Series:
        """Calculate the Information Coefficient (Spearman rank correlation)
        for the composite score and each factor against forward returns.

        Returns:
            pd.Series of IC values indexed by factor name, sorted descending.
        """
        if self.results_df is None:
            self.run()

        exclude = {"ticker", "forward_return"}
        factor_cols = [c for c in self.results_df.columns if c not in exclude]

        ics = {}
        for col in factor_cols:
            ics[col] = self.results_df[col].corr(
                self.results_df["forward_return"], method="spearman"
            )

        return pd.Series(ics, name="IC").sort_values(ascending=False)

    def quantile_spread(self, factor: str = "composite", q: int = 5) -> float:
        """Calculate the spread in average forward returns between the top
        and bottom quantiles of a given factor.
        """
        if self.results_df is None:
            self.run()

        df = self.results_df.copy()
        # Use rank(method="first") to prevent qcut from failing on duplicate zeroes
        df["quantile"] = pd.qcut(df[factor].rank(method="first"), q, labels=False)

        bottom_q_mean = df[df["quantile"] == 0]["forward_return"].mean()
        top_q_mean = df[df["quantile"] == q - 1]["forward_return"].mean()

        return float(top_q_mean - bottom_q_mean)
