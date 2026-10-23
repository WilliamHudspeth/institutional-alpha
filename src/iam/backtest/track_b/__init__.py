"""Track B: published, survivorship-free factor returns (Phase 1a of the backtest strategy).

Loaders for the free sources in ``docs/research/backtest-strategy.md`` Section 3:

- ``jkp``: Jensen, Kelly and Pedersen factor and theme returns
- ``osap``: Chen and Zimmermann Open Source Asset Pricing portfolio returns
- ``french``: Kenneth French market, Fama-French factors, momentum, 49 industries
- ``damodaran_erp``: Damodaran implied equity risk premium, annual and monthly

``factor_map`` links engine factors to JKP factors and builds candidate E for the
weight horse race. All downloads go through ``cache.DownloadCache``, which keeps a
SHA-256 record of every file a run used.
"""

from .cache import DownloadCache, FileRecord, TrackBDataError
from .damodaran_erp import erp_as_of, load_erp_monthly, load_histimpl
from .factor_map import (
    CANDIDATE_E,
    ENGINE_TO_JKP,
    ENGINE_TO_JKP_THEME,
    UNMAPPED,
    engine_factor_returns,
    engine_theme_returns,
    make_track_b_candidate,
    sharpe_vector,
    window_correlations,
    window_stats,
)
from .french import (
    french_ff5_monthly,
    french_industry49_monthly,
    french_momentum_monthly,
    load_french_tables,
)
from .jkp import jkp_directions, jkp_wide, load_jkp
from .osap import load_osap_portfolios, load_osap_signal_signs, osap_long_short

__all__ = [
    "CANDIDATE_E",
    "DownloadCache",
    "ENGINE_TO_JKP",
    "ENGINE_TO_JKP_THEME",
    "FileRecord",
    "TrackBDataError",
    "UNMAPPED",
    "engine_factor_returns",
    "engine_theme_returns",
    "erp_as_of",
    "french_ff5_monthly",
    "french_industry49_monthly",
    "french_momentum_monthly",
    "jkp_directions",
    "jkp_wide",
    "load_erp_monthly",
    "load_french_tables",
    "load_histimpl",
    "load_jkp",
    "load_osap_portfolios",
    "load_osap_signal_signs",
    "make_track_b_candidate",
    "osap_long_short",
    "sharpe_vector",
    "window_correlations",
    "window_stats",
]
