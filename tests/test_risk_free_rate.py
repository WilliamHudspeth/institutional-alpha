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


@pytest.mark.parametrize("quoted", [43.1, 4.31, 0.431, 0.0431])
def test_rate_handles_every_tnx_scale(quoted):
    with patch.object(markets, "fetch_live_quote", return_value=markets.Quote("^TNX", last=quoted)):
        assert DamodaranProvider.get_risk_free_rate() == pytest.approx(0.0431)


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
