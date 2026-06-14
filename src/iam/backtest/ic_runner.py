"""Multi-horizon, per-factor IC backtest engine.

Extends the existing runner with:
- Multiple forward-return horizons (1m, 3m, 6m, 12m)
- Per-factor IC decomposition (not just composite)
- Value-weighted IC (market-cap weighted)
- Per-factor Newey-West significance tests
- Report generation (text + CSV)
"""

from __future__ import annotations

import logging
import warnings
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field
from tqdm import tqdm

from iam.backtest.metrics import (
    hit_rate,
    ic_sector_neutral,
    information_coefficient,
    newey_west_se_rigorous,
)
from iam.backtest.multiple_testing import (
    ValidationMetrics,
    compute_validation_metrics,
    correct_factor_tests,
    effective_num_tests,
)
from iam.backtest.quantiles import decile_spread
from iam.backtest.snapshots import build_snapshot
from iam.data.security import Security
from iam.engine.composite import DEFAULT_WEIGHTS, ScoreResult, score

logger = logging.getLogger(__name__)


class ICBacktestConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    horizons: list[int] = Field(
        default_factory=lambda: [1, 3, 6, 12], description="Horizons in months"
    )
    min_stocks_per_date: int = Field(30, description="Minimum stocks required per evaluation date")
    rebalance_freq: str = Field("ME", description="Evaluation frequency (ME=month-end)")
    start_date: str = Field("2018-01-31", description="Start date (YYYY-MM-DD)")
    end_date: str = Field("2024-12-31", description="End date (YYYY-MM-DD)")
    nw_lags: int = Field(3, description="Newey-West lags for standard errors")
    results_dir: Path = Field(Path("data/results/ic"), description="Directory to save IC reports")
    n_jobs_cpu: int = Field(4, ge=1, description="Number of CPU workers for scoring")
    cache_dir: Path = Field(Path(".cache/snapshots"), description="Snapshot cache directory")

    def validate_paths(self) -> None:
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)


def _score_worker(
    base: Security,
    as_of: str,
    cache_dir: Path,
) -> tuple[str, float, dict[str, float], float, str]:
    """Score a security and return composite and per-factor values.

    Returns:
        ticker, composite_score, factor_values, market_cap, sector
    """
    try:
        snapshot = build_snapshot(base, as_of, cache_dir=cache_dir)
        if snapshot is None or snapshot.market.price is None or np.isnan(snapshot.market.price):
            return base.ticker, float("nan"), {}, float("nan"), base.sector or ""

        # Score the snapshot
        res: ScoreResult = score(snapshot)

        # Extract per-factor effective values
        factor_vals = {name: c.effective() for name, c in res.factor_breakdown.items()}

        mcap = snapshot.market.market_cap
        if mcap is None or np.isnan(mcap):
            mcap = float("nan")

        return base.ticker, res.composite, factor_vals, mcap, base.sector or ""

    except Exception as e:
        logger.debug(f"Scoring failed for {base.ticker} on {as_of}: {e}")
        return base.ticker, float("nan"), {}, float("nan"), base.sector or ""


class BacktestResult(dict):
    """Subclass of dict holding multi-horizon backtest DataFrames and validation metrics."""

    def __init__(self, horizons_dict: dict[int, pd.DataFrame], validation: ValidationMetrics):
        super().__init__(horizons_dict)
        self.validation = validation


class ICBacktest:
    def __init__(
        self,
        securities: list[Security],
        price_block: pd.DataFrame,
        config: ICBacktestConfig | None = None,
    ):
        self.securities = securities

        # Process price block
        if hasattr(price_block, "to_pandas"):
            try:
                price_block = price_block.to_pandas()
            except Exception:
                price_block = pd.DataFrame(price_block.to_dicts())
        if isinstance(price_block.index, pd.MultiIndex):
            price_block = price_block.reset_index()

        if "date" in price_block.columns:
            price_block = price_block.copy()
            price_block["date"] = pd.to_datetime(price_block["date"]).dt.strftime("%Y-%m-%d")
            # We assume columns: date, ticker, close, fwd_ret (maybe others)
            self.price_block = price_block.set_index(["date", "ticker"])
        else:
            self.price_block = price_block

        self.config = config or ICBacktestConfig()
        self.factor_names = list(DEFAULT_WEIGHTS.keys())
        self.results: dict[int, pd.DataFrame] = {}

    def _get_forward_returns(self, date: str, horizon_months: int) -> pd.Series | None:
        """Calculate forward returns at specific horizon from price block."""
        # Find the target date
        date_dt = pd.to_datetime(date)
        target_dt = date_dt + pd.DateOffset(months=horizon_months)
        target_str = target_dt.strftime("%Y-%m-%d")

        # Get unique dates in price block
        all_dates = self.price_block.index.get_level_values("date").unique().sort_values()

        # Find closest date >= target
        valid_dates = all_dates[all_dates >= target_str]
        if len(valid_dates) == 0:
            return None

        actual_target_str = valid_dates[0]

        try:
            curr_prices = self.price_block.xs(date, level="date")["close"]
            fwd_prices = self.price_block.xs(actual_target_str, level="date")["close"]

            common = curr_prices.index.intersection(fwd_prices.index)
            if len(common) == 0:
                return None

            rets = (fwd_prices[common] / curr_prices[common]) - 1
            return rets
        except KeyError:
            return None

    def _compute_weighted_ic(self, df: pd.DataFrame) -> float:
        """Calculate market-cap weighted Pearson correlation."""
        # Need score, fwd, mcap
        valid = df.dropna(subset=["score", "fwd", "mcap"])
        if len(valid) < 2:
            return float("nan")

        weights = valid["mcap"].values
        w_sum = weights.sum()
        if w_sum <= 0:
            return float("nan")

        weights = weights / w_sum

        score_vals = valid["score"].values
        fwd_vals = valid["fwd"].values

        w_score = score_vals - np.average(score_vals, weights=weights)
        w_fwd = fwd_vals - np.average(fwd_vals, weights=weights)

        numerator = np.sum(weights * w_score * w_fwd)
        denom_score = np.sum(weights * w_score**2)
        denom_fwd = np.sum(weights * w_fwd**2)

        if denom_score <= 0 or denom_fwd <= 0:
            return float("nan")

        return float(numerator / np.sqrt(denom_score * denom_fwd))

    def run(self) -> dict[int, pd.DataFrame]:
        self.config.validate_paths()
        dates_range = pd.date_range(
            self.config.start_date, self.config.end_date, freq=self.config.rebalance_freq
        )
        dates = dates_range.strftime("%Y-%m-%d").tolist()

        all_results: dict[int, list] = {h: [] for h in self.config.horizons}

        with ProcessPoolExecutor(max_workers=self.config.n_jobs_cpu) as executor:
            for date in tqdm(dates, desc="IC Backtest"):
                # 1. Parallel scoring
                try:
                    futures = [
                        executor.submit(_score_worker, base, date, self.config.cache_dir)
                        for base in self.securities
                    ]

                    scores = {}
                    sectors = {}
                    mcaps = {}
                    factor_scores: dict[str, dict] = {f: {} for f in self.factor_names}

                    for future in futures:
                        ticker, comp, f_vals, mcap, sector = future.result()
                        if not np.isnan(comp):
                            scores[ticker] = comp
                            sectors[ticker] = sector
                            mcaps[ticker] = mcap
                            for f_name, f_val in f_vals.items():
                                if f_name in factor_scores:
                                    factor_scores[f_name][ticker] = f_val
                except Exception as e:
                    logger.warning(f"Parallel scoring failed on {date}: {e}")
                    continue

                if len(scores) < self.config.min_stocks_per_date:
                    continue

                # 2. Per-horizon analysis
                for h in self.config.horizons:
                    rets = self._get_forward_returns(date, h)
                    if rets is None:
                        continue

                    common_tickers = [
                        t for t in scores.keys() if t in rets.index and not pd.isna(rets[t])
                    ]
                    if len(common_tickers) < self.config.min_stocks_per_date:
                        continue

                    df = pd.DataFrame(
                        {
                            "ticker": common_tickers,
                            "score": [scores[t] for t in common_tickers],
                            "fwd": [rets[t] for t in common_tickers],
                            "sector": [sectors[t] for t in common_tickers],
                            "mcap": [mcaps[t] for t in common_tickers],
                        }
                    )

                    # Compute composite metrics
                    ic = information_coefficient(df)
                    ic_sn = (
                        ic_sector_neutral(df, sector_col="sector")
                        if "sector" in df.columns
                        else float("nan")
                    )
                    ic_weighted = self._compute_weighted_ic(df)
                    hr = hit_rate(df)
                    spreads = decile_spread(df)

                    row = {
                        "date": date,
                        "ic": ic,
                        "ic_sector_neutral": ic_sn,
                        "ic_weighted": ic_weighted,
                        "hit_rate": hr,
                        "spread": spreads.get("spread", float("nan")),
                        "top": spreads.get("top", float("nan")),
                        "bottom": spreads.get("bottom", float("nan")),
                        "n_stocks": len(common_tickers),
                    }

                    # Per-factor IC
                    for f in self.factor_names:
                        f_series = pd.Series(
                            [factor_scores[f].get(t, float("nan")) for t in common_tickers]
                        )
                        f_df = pd.DataFrame({"score": f_series, "fwd": df["fwd"]})
                        row[f"ic_{f}"] = information_coefficient(f_df)

                    all_results[h].append(row)

        for h in self.config.horizons:
            if all_results[h]:
                df = pd.DataFrame(all_results[h])
                df["date"] = pd.to_datetime(df["date"])
                df = df.set_index("date")
                self.results[h] = df
            else:
                self.results[h] = pd.DataFrame()

        # Compute validation metrics on 1-month horizon if present
        df1 = self.results.get(1, pd.DataFrame())
        if not df1.empty:
            validation = compute_validation_metrics(df1, self.factor_names)
        else:
            validation = ValidationMetrics(
                psr=float("nan"),
                dsr=float("nan"),
                pbo=float("nan"),
                spa_pvalue=float("nan"),
                effective_tests=float("nan"),
                fwer_significant_factors=0,
                fdr_significant_factors=0,
            )
        return BacktestResult(self.results, validation)

    def compute_statistics(self) -> dict[int, dict]:
        stats: dict[int, dict] = {}
        for h, df in self.results.items():
            if df.empty:
                stats[h] = {}
                continue

            ic_series = df["ic"].dropna()
            if len(ic_series) < 3:
                stats[h] = {
                    "mean_ic": np.nan,
                    "icir": np.nan,
                    "t_stat": np.nan,
                    "p_value": np.nan,
                    "n_obs": len(ic_series),
                }
                continue

            mean_ic = ic_series.mean()
            std_ic = ic_series.std()
            icir = mean_ic / std_ic if std_ic > 0 else float("nan")
            n = len(ic_series)

            t_stat, p_value, _ = newey_west_se_rigorous(ic_series, nlags=self.config.nw_lags)

            stats[h] = {
                "mean_ic": mean_ic,
                "icir": icir,
                "t_stat": t_stat,
                "p_value": p_value,
                "n_obs": n,
            }
        return stats

    def compute_factor_statistics(self) -> pd.DataFrame:
        if 1 not in self.results or self.results[1].empty:
            return pd.DataFrame()

        df1 = self.results[1]
        rows = []

        # Calculate robust Spearman correlation for effective tests (M_eff)
        factor_cols = [f"ic_{f}" for f in self.factor_names if f"ic_{f}" in df1.columns]
        if len(factor_cols) > 1:
            ic_df = df1[factor_cols].copy()
            # Suppress constant input warnings for Spearman correlation
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                corr_df = ic_df.fillna(0).corr(method="spearman").clip(-0.999, 0.999)

            # Fill NaNs from zero-variance columns with 0, but enforce 1.0 on the diagonal
            corr_df = corr_df.fillna(0.0)
            corr_matrix = corr_df.values.copy()
            np.fill_diagonal(corr_matrix, 1.0)

            m_eff = effective_num_tests(corr_matrix)
        else:
            m_eff = 1.0

        t_stats_dict = {}

        for f in self.factor_names:
            col = f"ic_{f}"
            if col not in df1.columns:
                continue
            ic_series = df1[col].dropna()
            if len(ic_series) < 3:
                continue

            mean_ic = ic_series.mean()
            std_ic = ic_series.std()
            icir = mean_ic / std_ic if std_ic > 0 else float("nan")
            t_stat, p_value, _ = newey_west_se_rigorous(ic_series, nlags=self.config.nw_lags)
            t_stats_dict[f] = t_stat

            rows.append(
                {
                    "factor": f,
                    "ic_mean": mean_ic,
                    "ic_std": std_ic,
                    "icir": icir,
                    "t_stat": t_stat,
                    "p_value": p_value,
                }
            )

        if not rows:
            return pd.DataFrame()

        # Apply FWER (Holm) and FDR (BH) corrections
        mt_report = correct_factor_tests(t_stats_dict, effective_tests=m_eff)
        for row in rows:
            v = next((x for x in mt_report.verdicts if x.name == row["factor"]), None)
            if v:
                row["holm_p"] = v.holm_p
                row["bh_p"] = v.bh_p
                row["survives_holm"] = v.survives_holm
                row["survives_bh"] = v.survives_bh

        return pd.DataFrame(rows).set_index("factor")

    def generate_report(self) -> None:
        self.config.validate_paths()

        stats = self.compute_statistics()
        df1 = self.results.get(1, pd.DataFrame())
        val = None
        if not df1.empty:
            val = compute_validation_metrics(df1, self.factor_names)

        summary_path = self.config.results_dir / "ic_summary.txt"
        with open(summary_path, "w") as f:
            f.write("IC Backtest Results\n")
            f.write("===================\n\n")
            for h, s in stats.items():
                if not s:
                    continue
                f.write(f"Horizon {h} months:\n")
                f.write(f"  Mean IC: {s.get('mean_ic', np.nan):.4f}\n")
                f.write(f"  ICIR:    {s.get('icir', np.nan):.4f}\n")
                f.write(f"  t-stat:  {s.get('t_stat', np.nan):.4f}\n")
                f.write(f"  p-value: {s.get('p_value', np.nan):.6f}\n")
                f.write(f"  n_obs:   {s.get('n_obs', 0)}\n\n")

            if val:
                f.write("Research Validation\n")
                f.write("-------------------\n")
                f.write(
                    f"  PSR:                      {val.psr:.4f}\n"
                    if not np.isnan(val.psr)
                    else "  PSR:                      N/A\n"
                )
                f.write(
                    f"  DSR:                      {val.dsr:.4f}\n"
                    if not np.isnan(val.dsr)
                    else "  DSR:                      N/A\n"
                )
                f.write(
                    f"  PBO:                      {val.pbo:.4f}\n"
                    if not np.isnan(val.pbo)
                    else "  PBO:                      N/A\n"
                )
                f.write(
                    f"  SPA p-value:              {val.spa_pvalue:.4f}\n"
                    if not np.isnan(val.spa_pvalue)
                    else "  SPA p-value:              N/A\n"
                )
                f.write(
                    f"  Effective Tests:          {val.effective_tests:.2f}\n"
                    if not np.isnan(val.effective_tests)
                    else "  Effective Tests:          N/A\n"
                )
                f.write(f"  FWER Significant Factors: {val.fwer_significant_factors}\n")
                f.write(f"  FDR Significant Factors:  {val.fdr_significant_factors}\n\n")

        factor_stats = self.compute_factor_statistics()
        if not factor_stats.empty:
            factor_stats.to_csv(self.config.results_dir / "factor_stats_1m.csv")

        for h, df in self.results.items():
            if not df.empty:
                df.to_csv(self.config.results_dir / f"ic_horizon_{h}m.csv")

        logger.info(f"IC report generated in {self.config.results_dir}")
