"""Production-grade backtest harness (v0.4).

Hardened infrastructure with yfinance → Stooq fallback, Polars performance,
diskcache PIT snapshots, statsmodels Newey-West, sector-neutral IC, ProcessPool
scoring, and Bayesian shrinkage calibration.

Maintains one-way dependency: only imports from iam.api.value_security().
"""

from .calibration import (
    ic_to_reliability,
    ic_to_reliability_bayesian,
    summarize_backtest,
    write_calibration,
)
from .config import BacktestConfig
from .manifest import BacktestManifest
from .metrics import (
    fisher_mean,
    hit_rate,
    ic_sector_neutral,
    information_coefficient,
    information_ratio,
    newey_west_se,
    newey_west_se_rigorous,
    rolling_ic_stability,
    statistical_significance,
)
from .prices import load_price_block, load_price_block_for_date
from .quantiles import decile_spread, quantile_spread_by_date, quantile_turnover, spread_after_costs
from .runner import print_backtest_summary, run_backtest
from .snapshots import build_snapshot, get_snapshot_cache, load_snapshot
from .universe import load_universe_from_json, load_universe_tickers

__all__ = [
    # Config & manifest
    "BacktestConfig",
    "BacktestManifest",
    # Universe loading
    "load_universe_from_json",
    "load_universe_tickers",
    # Snapshots & caching
    "build_snapshot",
    "load_snapshot",
    "get_snapshot_cache",
    # Price data
    "load_price_block",
    "load_price_block_for_date",
    # Metrics (institutional)
    "information_coefficient",
    "information_ratio",
    "hit_rate",
    "rolling_ic_stability",
    "statistical_significance",
    "newey_west_se",
    "newey_west_se_rigorous",
    "ic_sector_neutral",
    "fisher_mean",
    # Quantiles & costs
    "decile_spread",
    "quantile_spread_by_date",
    "quantile_turnover",
    "spread_after_costs",
    # Runner
    "run_backtest",
    "print_backtest_summary",
    # Calibration
    "ic_to_reliability",
    "ic_to_reliability_bayesian",
    "summarize_backtest",
    "write_calibration",
]
