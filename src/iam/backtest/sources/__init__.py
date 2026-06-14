"""Pluggable data source layer for backtest infrastructure.

Each data source implements the `DataSource` contract (base.py) with three methods:
- fetch_price(ticker, as_of) -> float
- fetch_debt(ticker, as_of) -> float
- download_history(ticker, start, end) -> DataFrame

Available sources:
- YFinanceSource: Primary, institutional-grade (price + debt)
- StooqSource: Fallback, free CSV export (price only)
- FMPSource: Premium, Point-in-time API
- TiingoSource: Premium, Point-in-time API
- SecEdgarSource: Official, keyless SEC XBRL (fundamentals + debt)
- CompositeDataSource: Chain of sources with fallback
- TieredDataSource: Capability-aware source routing

Default chain is built via build_tiered_source().
"""

from .base import DataSource, DataSourceError
from .composite import CompositeDataSource
from .stooq_source import StooqSource
from .tiers import Capability, DataTier, TieredDataSource, build_tiered_source
from .yfinance_source import YFinanceSource


def default_chain(
    yfinance_timeout: float = 10.0,
    stooq_timeout: float = 15.0,
) -> CompositeDataSource:
    """Build the default yfinance → Stooq fallback chain (Legacy)."""
    return CompositeDataSource(
        [
            YFinanceSource(timeout=yfinance_timeout),
            StooqSource(timeout=stooq_timeout),
        ]
    )


__all__ = [
    "DataSource",
    "DataSourceError",
    "YFinanceSource",
    "StooqSource",
    "CompositeDataSource",
    "TieredDataSource",
    "DataTier",
    "Capability",
    "build_tiered_source",
    "default_chain",
]
