"""Tests for the SEC EDGAR source and manifest provenance wiring."""

from __future__ import annotations

import pandas as pd
import pytest

from iam.backtest.sources.base import DataSourceError
from iam.backtest.sources.sec_edgar_source import SecEdgarSource
from iam.backtest.sources.tiers import Capability, DataTier, TieredDataSource

AS_OF = pd.Timestamp("2024-06-28")


def _edgar_with(responses: dict):
    """SecEdgarSource whose HTTP returns canned JSON keyed by URL substring."""

    def fake_get(url: str):
        for key, payload in responses.items():
            if key in url:
                return payload
        return {}

    return SecEdgarSource(http_get=fake_get)


_CIK_MAP = {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}}


def test_edgar_declares_no_price_capability():
    src = SecEdgarSource()
    assert Capability.PRICE not in src.capabilities
    assert src.tier == DataTier.OFFICIAL
    with pytest.raises(DataSourceError):
        src.fetch_price("AAPL", AS_OF)


def test_edgar_assembles_debt_from_current_plus_noncurrent():
    edgar = _edgar_with(
        {
            "company_tickers.json": _CIK_MAP,
            "DebtCurrent.json": {
                "units": {
                    "USD": [
                        {"end": "2024-03-30", "val": 1.0e10, "filed": "2024-05-02"},
                    ]
                }
            },
            "LongTermDebtNoncurrent.json": {
                "units": {
                    "USD": [
                        {"end": "2024-03-30", "val": 9.0e10, "filed": "2024-05-02"},
                    ]
                }
            },
        }
    )
    assert edgar.fetch_debt("AAPL", AS_OF) == 1.0e11  # 10B current + 90B noncurrent


def test_edgar_point_in_time_excludes_unfiled_data():
    """A value whose FILING date is after as_of must not be visible (no look-ahead)."""
    edgar = _edgar_with(
        {
            "company_tickers.json": _CIK_MAP,
            "DebtCurrent.json": {
                "units": {
                    "USD": [
                        {"end": "2023-12-30", "val": 5.0e9, "filed": "2024-02-01"},  # visible
                        {
                            "end": "2024-06-29",
                            "val": 9.9e9,
                            "filed": "2024-08-01",
                        },  # filed AFTER as_of
                    ]
                }
            },
            "LongTermDebtNoncurrent.json": {
                "units": {
                    "USD": [
                        {"end": "2023-12-30", "val": 8.0e10, "filed": "2024-02-01"},
                        {
                            "end": "2024-06-29",
                            "val": 9.9e10,
                            "filed": "2024-08-01",
                        },  # not yet filed
                    ]
                }
            },
        }
    )
    # Must use the Feb-filed Q4-2023 numbers, not the Aug-filed ones.
    assert edgar.fetch_debt("AAPL", AS_OF) == 5.0e9 + 8.0e10


def test_edgar_unknown_ticker_raises():
    edgar = _edgar_with({"company_tickers.json": _CIK_MAP})
    with pytest.raises(DataSourceError):
        edgar.fetch_debt("ZZZZ", AS_OF)


def test_edgar_falls_back_to_single_combined_tag():
    edgar = _edgar_with(
        {
            "company_tickers.json": _CIK_MAP,
            # No DebtCurrent / LongTermDebtNoncurrent -> empty {} -> None
            "LongTermDebt.json": {
                "units": {
                    "USD": [
                        {"end": "2024-03-30", "val": 7.5e10, "filed": "2024-05-02"},
                    ]
                }
            },
        }
    )
    assert edgar.fetch_debt("AAPL", AS_OF) == 7.5e10


def test_edgar_routes_correctly_inside_tiered_chain():
    """In a tiered chain, EDGAR (OFFICIAL) outranks yfinance (COMMUNITY) for debt."""

    edgar = _edgar_with(
        {
            "company_tickers.json": _CIK_MAP,
            "LongTermDebt.json": {
                "units": {
                    "USD": [
                        {"end": "2024-03-30", "val": 6.0e10, "filed": "2024-05-02"},
                    ]
                }
            },
        }
    )

    class _Yf:
        name = "yfinance"
        tier = DataTier.COMMUNITY
        capabilities = Capability.PRICE | Capability.DEBT

        def is_available(self):
            return True

        def fetch_price(self, t, a):
            return 100.0

        def fetch_debt(self, t, a):
            return 1.0  # should be ignored; EDGAR wins

        def download_history(self, t, s, e):
            return None

    tiered = TieredDataSource([_Yf(), edgar])
    assert tiered.fetch_debt("AAPL", AS_OF) == 6.0e10
    # provenance shows OFFICIAL tier served debt, not degraded
    assert tiered.provenance[-1].tier == DataTier.OFFICIAL
    assert tiered.degraded_fields() == []


# --------------------------------------------------------------------------- #
# Manifest provenance wiring
# --------------------------------------------------------------------------- #
def test_manifest_records_provenance_and_degraded_flag():
    from iam.backtest.config import BacktestConfig
    from iam.backtest.manifest import BacktestManifest

    cfg = BacktestConfig()
    provenance = {
        "requests": 3,
        "by_tier": {"PREMIUM": 1, "COMMUNITY": 2},
        "degraded_count": 2,
        "source_order": ["fmp", "yfinance", "stooq"],
    }
    m = BacktestManifest(cfg, data_provenance=provenance).to_dict()
    assert m["data_provenance"]["requests"] == 3
    assert m["_meta"]["degraded_data"] is True


def test_manifest_backward_compatible_without_provenance():
    from iam.backtest.config import BacktestConfig
    from iam.backtest.manifest import BacktestManifest

    m = BacktestManifest(BacktestConfig()).to_dict()
    assert "data_provenance" not in m
    assert "degraded_data" not in m["_meta"]
