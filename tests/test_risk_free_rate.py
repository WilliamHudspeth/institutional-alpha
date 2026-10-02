"""The risk-free rate must come from a live ^TNX quote or the documented
baseline — never from the mock/random quotes the market tape uses for display."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from iam.data import markets
from iam.data.damodaran import DamodaranProvider


@pytest.fixture(autouse=True)
def _clear_live_cache():
    markets._live_cache.clear()
    markets._live_fail_ts.clear()
    yield
    markets._live_cache.clear()
    markets._live_fail_ts.clear()


def test_mock_quote_is_never_returned_as_live():
    mock = markets._mock_quote("^TNX", True)
    assert mock.stale
    with patch.object(markets, "_fetch_one", return_value=mock):
        assert markets.fetch_live_quote("^TNX") is None


def test_failures_are_cached_for_the_ttl():
    with patch.object(markets, "_fetch_one", side_effect=RuntimeError("down")) as fetch:
        assert markets.fetch_live_quote("^TNX") is None
        assert markets.fetch_live_quote("^TNX") is None
    assert fetch.call_count == 1


def test_live_quotes_are_cached():
    live = markets.Quote(symbol="^TNX", last=4.31)
    with patch.object(markets, "_fetch_one", return_value=live) as fetch:
        assert markets.fetch_live_quote("^TNX") is live
        assert markets.fetch_live_quote("^TNX") is live
    assert fetch.call_count == 1


@pytest.mark.parametrize(
    ("pct", "expected"),
    # Low yields matter: 0.68% (mid-2020) and 2.0% used to come back 10x too high.
    [(5.24, 0.0524), (4.31, 0.0431), (2.0, 0.02), (0.68, 0.0068), (15.8, 0.158)],
)
def test_rate_reads_tnx_quote_as_percent(pct, expected):
    with patch.object(markets, "fetch_live_quote", return_value=markets.Quote("^TNX", last=pct)):
        assert DamodaranProvider.get_risk_free_rate() == pytest.approx(expected)


@pytest.mark.parametrize("pct", [0.0, -0.1, 42.5])
def test_implausible_tnx_quote_falls_back_to_baseline(pct):
    with patch.object(markets, "fetch_live_quote", return_value=markets.Quote("^TNX", last=pct)):
        assert DamodaranProvider.get_risk_free_rate() == DamodaranProvider.CURRENT_RISK_FREE_RATE


class _FakeTicker:
    """Yahoo quotes ^TNX in percent: 5.24 means 5.24% (checked live, Oct 2026)."""

    def __init__(self, _symbol):
        self.fast_info = type("FI", (), {"last_price": 5.24, "previous_close": 5.20})()


def test_market_layer_keeps_yahoo_rate_quotes_in_percent():
    with patch.object(markets, "_HAS_YF", True), patch.object(markets, "yf", create=True) as yf:
        yf.Ticker = _FakeTicker
        q = markets._fetch_one("^TNX", want_history=False)
    assert q.last == pytest.approx(5.24)
    assert q.change_bps == pytest.approx(4.0)


def test_rate_falls_back_to_documented_baseline():
    with patch.object(markets, "fetch_live_quote", return_value=None):
        assert DamodaranProvider.get_risk_free_rate() == DamodaranProvider.CURRENT_RISK_FREE_RATE


def test_rate_lookup_does_not_fetch_the_whole_tape():
    with (
        patch.object(markets, "fetch_market_snapshot") as tape,
        patch.object(markets, "fetch_live_quote", return_value=None),
    ):
        DamodaranProvider.get_risk_free_rate()
    tape.assert_not_called()
