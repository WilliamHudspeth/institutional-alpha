"""Tests for the tiered, capability-aware data layer."""

from __future__ import annotations

import pandas as pd
import pytest

from iam.backtest.sources.base import DataSource, DataSourceError
from iam.backtest.sources.fmp_source import FMPSource
from iam.backtest.sources.tiers import (
    Capability,
    DataTier,
    TieredDataSource,
)
from iam.backtest.sources.tiingo_source import TiingoSource

AS_OF = pd.Timestamp("2024-06-28")


class _Fake(DataSource):
    """Configurable fake source for routing tests."""

    def __init__(self, name, tier, caps, *, available=True, price=None, debt=None, hist=True):
        self.name = name
        self.tier = tier
        self.capabilities = caps
        self._available = available
        self._price = price
        self._debt = debt
        self._hist = hist
        self.price_calls = 0
        self.debt_calls = 0

    def is_available(self):
        return self._available

    def fetch_price(self, ticker, as_of):
        self.price_calls += 1
        if self._price is None:
            raise DataSourceError(self.name, ticker, "no price")
        return self._price

    def fetch_debt(self, ticker, as_of):
        self.debt_calls += 1
        if self._debt is None:
            raise DataSourceError(self.name, ticker, "no debt")
        return self._debt

    def download_history(self, ticker, start, end):
        if not self._hist:
            return None
        return pd.DataFrame({"Close": [1.0, 2.0]})


# --------------------------------------------------------------------------- #
# Routing
# --------------------------------------------------------------------------- #
def test_debt_never_routed_to_price_only_source():
    """The core fix: a price-only source is never consulted for debt."""
    premium = _Fake("fmp", DataTier.PREMIUM, Capability.PRICE | Capability.DEBT, debt=4.2e8)
    price_only = _Fake("stooq", DataTier.FALLBACK, Capability.PRICE)
    tiered = TieredDataSource([price_only, premium])

    assert tiered.fetch_debt("AAPL", AS_OF) == 4.2e8
    assert price_only.debt_calls == 0  # never touched for debt


def test_no_debt_capable_source_raises_instead_of_fabricating_zero():
    """Missing fundamentals must surface, not masquerade as a real 0.0."""
    price_only = _Fake("stooq", DataTier.FALLBACK, Capability.PRICE)
    tiered = TieredDataSource([price_only])
    with pytest.raises(DataSourceError):
        tiered.fetch_debt("AAPL", AS_OF)


def test_higher_tier_wins_for_price():
    premium = _Fake("fmp", DataTier.PREMIUM, Capability.PRICE, price=101.0)
    community = _Fake("yfinance", DataTier.COMMUNITY, Capability.PRICE, price=100.0)
    tiered = TieredDataSource([community, premium])  # unsorted input
    assert tiered.fetch_price("AAPL", AS_OF) == 101.0
    assert premium.price_calls == 1
    assert community.price_calls == 0  # premium answered, community not consulted


def test_falls_through_to_lower_tier_and_flags_degraded():
    premium = _Fake("fmp", DataTier.PREMIUM, Capability.PRICE, price=None)  # fails
    community = _Fake("yfinance", DataTier.COMMUNITY, Capability.PRICE, price=100.0)
    tiered = TieredDataSource([premium, community])
    assert tiered.fetch_price("AAPL", AS_OF) == 100.0
    degraded = tiered.degraded_fields()
    assert len(degraded) == 1
    assert degraded[0].source == "yfinance"
    assert degraded[0].tier == DataTier.COMMUNITY


def test_no_degradation_when_best_tier_answers():
    premium = _Fake("fmp", DataTier.PREMIUM, Capability.PRICE, price=100.0)
    community = _Fake("yfinance", DataTier.COMMUNITY, Capability.PRICE, price=99.0)
    tiered = TieredDataSource([premium, community])
    tiered.fetch_price("AAPL", AS_OF)
    assert tiered.degraded_fields() == []


def test_unavailable_premium_is_skipped():
    premium = _Fake(
        "fmp", DataTier.PREMIUM, Capability.PRICE | Capability.DEBT, available=False, debt=1.0
    )
    community = _Fake("yfinance", DataTier.COMMUNITY, Capability.DEBT, debt=5.0)
    tiered = TieredDataSource([premium, community])
    assert tiered.fetch_debt("AAPL", AS_OF) == 5.0
    assert premium.debt_calls == 0


def test_audit_summary_is_manifest_ready():
    premium = _Fake("fmp", DataTier.PREMIUM, Capability.PRICE, price=100.0)
    community = _Fake("yfinance", DataTier.COMMUNITY, Capability.DEBT, debt=7.0)
    tiered = TieredDataSource([premium, community])
    tiered.fetch_price("AAPL", AS_OF)
    tiered.fetch_debt("AAPL", AS_OF)
    summary = tiered.audit_summary()
    assert summary["requests"] == 2
    assert summary["by_tier"]["PREMIUM"] == 1
    assert summary["source_order"] == ["fmp", "yfinance"]


def test_registry_resolves_tier_for_sources_without_class_attrs():
    """A plain source with only a name resolves tier/caps from the registry."""

    class Bare(DataSource):
        name = "stooq"

        def fetch_price(self, t, a):
            return 1.0

        def fetch_debt(self, t, a):
            return 0.0

        def download_history(self, t, s, e):
            return None

    tiered = TieredDataSource([Bare()])
    # stooq registry entry is FALLBACK / PRICE|HISTORY -> not DEBT-capable
    with pytest.raises(DataSourceError):
        tiered.fetch_debt("AAPL", AS_OF)


# --------------------------------------------------------------------------- #
# Premium adapters (offline, mocked HTTP)
# --------------------------------------------------------------------------- #
def test_fmp_unavailable_without_key():
    assert FMPSource(api_key=None).is_available() is False


def test_fmp_parses_price_and_debt_from_mocked_json():
    def fake_get(url):
        if "historical-price-full" in url:
            return {
                "historical": [
                    {"date": "2024-06-28", "close": 210.0},
                    {"date": "2024-06-27", "close": 208.0},
                ]
            }
        if "balance-sheet-statement" in url:
            return [
                {"date": "2024-03-30", "totalDebt": 1.05e11},
                {"date": "2023-12-30", "totalDebt": 1.10e11},
            ]
        return {}

    fmp = FMPSource(api_key="TEST", http_get=fake_get)
    assert fmp.is_available()
    assert fmp.fetch_price("AAPL", AS_OF) == 210.0
    assert fmp.fetch_debt("AAPL", AS_OF) == 1.05e11  # latest filing on/before as_of


def test_fmp_derives_total_debt_when_field_missing():
    def fake_get(url):
        return [{"date": "2024-03-30", "shortTermDebt": 2.0e9, "longTermDebt": 8.0e9}]

    fmp = FMPSource(api_key="TEST", http_get=fake_get)
    assert fmp.fetch_debt("AAPL", AS_OF) == 1.0e10


def test_tiingo_declares_no_debt_capability():
    assert Capability.DEBT not in TiingoSource(api_key="X").capabilities
    with pytest.raises(DataSourceError):
        TiingoSource(api_key="X").fetch_debt("AAPL", AS_OF)


def test_tiingo_parses_adjusted_close():
    def fake_get(url):
        return [
            {"date": "2024-06-27T00:00:00Z", "close": 100.0, "adjClose": 99.5},
            {"date": "2024-06-28T00:00:00Z", "close": 101.0, "adjClose": 100.5},
        ]

    t = TiingoSource(api_key="TEST", http_get=fake_get)
    assert t.fetch_price("AAPL", AS_OF) == 100.5
