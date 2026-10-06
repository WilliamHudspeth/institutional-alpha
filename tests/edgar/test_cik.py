"""Ticker -> CIK resolution, with a date-aware override table for reorganisations."""

from __future__ import annotations

from datetime import date

import pytest

from iam.data.edgar.cik import (
    CIK_OVERRIDES,
    CikOverride,
    UnresolvedTickerError,
    resolve_cik,
)
from iam.data.edgar.client import TICKERS_URL, EdgarClient
from tests.edgar.helpers import FixtureTransport, recorded_routes

OLD_BLK = 1364742
NEW_BLK = 2012383


@pytest.fixture()
def transport():
    return FixtureTransport(recorded_routes())


@pytest.fixture()
def client(tmp_path, transport):
    return EdgarClient(tmp_path / "cache", transport=transport, sleep=lambda s: None)


def test_plain_ticker_resolves_from_company_tickers(client):
    res = resolve_cik("AAPL", client=client)
    assert res.cik == 320193
    assert res.source == "company_tickers"


def test_ticker_is_case_insensitive(client):
    assert resolve_cik("msft", client=client).cik == 789019


def test_company_tickers_downloaded_once(client, transport):
    resolve_cik("AAPL", client=client)
    resolve_cik("MSFT", client=client)
    assert transport.calls == [TICKERS_URL]


def test_unresolved_ticker_raises_never_guesses(client):
    with pytest.raises(UnresolvedTickerError, match="ZZZZ"):
        resolve_cik("ZZZZ", client=client)


def test_blk_2020_resolves_to_the_old_holding_company(client):
    res = resolve_cik("BLK", date(2020, 6, 30), client=client)
    assert res.cik == OLD_BLK
    assert res.source == "override"


def test_blk_2026_resolves_to_the_new_holding_company(client):
    assert resolve_cik("BLK", date(2026, 6, 30), client=client).cik == NEW_BLK


def test_blk_without_a_date_is_the_current_entity(client):
    assert resolve_cik("BLK", client=client).cik == NEW_BLK


def test_blk_cutover_is_the_new_entitys_first_filing(client):
    # Old entity's last 10-Q was filed 2024-08-06; the new entity's first 10-Q on 2024-11-06.
    assert resolve_cik("BLK", date(2024, 11, 5), client=client).cik == OLD_BLK
    assert resolve_cik("BLK", date(2024, 11, 6), client=client).cik == NEW_BLK


def test_every_override_documents_its_source():
    assert "BLK" in CIK_OVERRIDES
    for entries in CIK_OVERRIDES.values():
        for entry in entries:
            assert entry.source.strip()


def test_override_windows_do_not_overlap():
    for entries in CIK_OVERRIDES.values():
        spans = sorted((e.valid_from or date.min, e.valid_to or date.max) for e in entries)
        for (_, prev_to), (next_from, _) in zip(spans, spans[1:], strict=False):
            assert prev_to < next_from


def test_date_outside_every_override_window_raises(client):
    table = {"XYZ": (CikOverride(5, date(2020, 1, 1), date(2020, 12, 31), "test"),)}
    with pytest.raises(UnresolvedTickerError, match="XYZ"):
        resolve_cik("XYZ", date(2021, 6, 1), client=client, overrides=table)


def test_string_dates_are_accepted(client):
    assert resolve_cik("BLK", "2020-06-30", client=client).cik == OLD_BLK
