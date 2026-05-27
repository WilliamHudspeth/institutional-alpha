"""Production-grade backtest harness.

Plugs empirical Information Coefficient into the Bayesian layer.
Maintains one-way dependency: only imports from iam.api.value_security().
"""

from .calibration import ic_to_reliability, summarize_backtest, write_calibration
from .metrics import information_coefficient, information_ratio, hit_rate
from .prices import get_price_block
from .quantiles import decile_spread, quantile_spread_by_date
from .runner import run_backtest, print_backtest_summary
from .snapshots import build_snapshot, load_snapshot

__all__ = [
    "run_backtest",
    "print_backtest_summary",
    "build_snapshot",
    "load_snapshot",
    "get_price_block",
    "information_coefficient",
    "information_ratio",
    "hit_rate",
    "decile_spread",
    "quantile_spread_by_date",
    "ic_to_reliability",
    "summarize_backtest",
    "write_calibration",
]
