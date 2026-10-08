"""Live adapter: ``Security.revenue_mix`` comes from the 10-K geographic mix.

Offline: yfinance is faked and the EDGAR provider ``_edgar_revenue_mix`` is patched in every
test (or driven through recorded fixtures). Nothing here reaches the network.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest
import yfinance as yf

from iam.data.edgar.client import EdgarClient
from iam.data.edgar.geography import GeographicMix, GeographicMixResult, MemberRow
from iam.data.providers import yfinance_adapter as ya
from iam.data.providers.yfinance_adapter import YFinanceAdapter
from iam.valuation.country_tax import company_marginal_tax
from tests.edgar.geo_helpers import geo_routes
from tests.edgar.helpers import FixtureTransport

US_ONLY_TAX = 0.25  # Damodaran's United States rate in the shipped dataset


def _mix(shares: dict[str, float]) -> GeographicMix:
    return GeographicMix(
        mix=dict(shares),
        coverage_of_total_revenue=0.987,
        resolved_share=1.0,
        unresolved=(),
        excluded=(),
        concept="RevenueFromContractWithCustomerExcludingAssessedTax",
        period_start="2024-10-01",
        period_end="2025-09-30",
        total_revenue=1000.0,
        members=tuple(MemberRow(k, k, v, True) for k, v in shares.items()),
        cik=1,
        accn="0000000001-25-000001",
        form="10-K",
        filed="2025-11-01",
        instance_url="https://www.sec.gov/Archives/edgar/data/1/x/x_htm.xml",
    )


def _fetch(monkeypatch, provider, ticker: str = "EDGT"):
    class MockTicker:
        def __init__(self, _ticker):
            self.info = {"currentPrice": 100.0, "marketCap": 1000.0, "totalDebt": 230.0}
            self.financials = pd.DataFrame()
            self.cashflow = pd.DataFrame()

    monkeypatch.setattr(yf, "Ticker", MockTicker)
    monkeypatch.setattr(ya, "_get_cached_data", lambda _t: None)
    monkeypatch.setattr(ya, "_save_cached_data", lambda _t, _d: None)
    monkeypatch.setattr(ya, "_edgar_revenue_mix", provider)
    return YFinanceAdapter().fetch(ticker)


def test_fetch_puts_the_10k_mix_and_its_source_on_the_security(monkeypatch):
    calls: list[tuple[str, date]] = []
    mix = _mix({"Germany": 0.5, "Ireland": 0.5})

    def provider(ticker, as_of):
        calls.append((ticker, as_of))
        return GeographicMixResult(mix=mix, cik=1)

    sec = _fetch(monkeypatch, provider)
    assert calls == [("EDGT", date.today())]
    assert sec.revenue_mix == {"Germany": 0.5, "Ireland": 0.5}
    assert sec.qualitative["revenue_mix_source"] == (
        "SEC EDGAR 10-K 0000000001-25-000001 filed 2025-11-01, FY ending 2025-09-30, "
        "tag RevenueFromContractWithCustomerExcludingAssessedTax, coverage 98.7%"
    )


def test_marginal_tax_is_revenue_weighted_once_the_mix_is_set(monkeypatch):
    sec = _fetch(
        monkeypatch, lambda t, d: GeographicMixResult(mix=_mix({"Germany": 0.5, "Ireland": 0.5}))
    )
    assert "revenue-weighted" in sec.qualitative["tax_rate_source"]
    assert sec.qualitative["tax_rate"] != pytest.approx(US_ONLY_TAX)
    # the same rate company_marginal_tax gives the Security as built
    assert sec.qualitative["tax_rate"] == company_marginal_tax(sec)[0]


def test_provider_returning_a_reason_leaves_the_mix_empty_and_records_it(monkeypatch):
    sec = _fetch(
        monkeypatch,
        lambda t, d: GeographicMixResult(reason="no 10-K filed on or before 2026-10-06 for CIK 1"),
    )
    assert sec.revenue_mix == {}
    assert sec.qualitative["revenue_mix_source"] == (
        "EDGAR geographic mix unavailable: no 10-K filed on or before 2026-10-06 for CIK 1"
    )
    assert "no revenue mix" in sec.qualitative["tax_rate_source"]
    assert sec.qualitative["tax_rate"] == pytest.approx(US_ONLY_TAX)


def test_provider_exception_never_escapes_fetch(monkeypatch):
    def boom(ticker, as_of):
        raise RuntimeError("EDGAR is down")

    sec = _fetch(monkeypatch, boom)
    assert sec.ticker == "EDGT"
    assert sec.revenue_mix == {}
    assert sec.qualitative["revenue_mix_source"] == (
        "EDGAR geographic mix unavailable: RuntimeError: EDGAR is down"
    )


def test_result_with_neither_mix_nor_reason_is_recorded_not_invented(monkeypatch):
    sec = _fetch(monkeypatch, lambda t, d: GeographicMixResult())
    assert sec.revenue_mix == {}
    assert sec.qualitative["revenue_mix_source"].startswith("EDGAR geographic mix unavailable")


def test_cached_security_round_trips_the_mix_and_its_source():
    from iam.data.security import Security

    sec = Security(
        ticker="RT",
        revenue_mix={"United States": 0.6, "OtherCountries": 0.4},
        qualitative={"revenue_mix_source": "SEC EDGAR 10-K x"},
    )
    back = ya._deserialize_security(ya._serialize_security(sec))
    assert back.revenue_mix == {"United States": 0.6, "OtherCountries": 0.4}
    assert back.qualitative["revenue_mix_source"] == "SEC EDGAR 10-K x"


def test_cache_hit_returns_the_cached_mix_without_asking_edgar(monkeypatch):
    from iam.data.security import Security

    cached = ya._serialize_security(Security(ticker="HIT", revenue_mix={"Japan": 1.0}))
    monkeypatch.setattr(ya, "_get_cached_data", lambda _t: cached)

    def never(ticker, as_of):
        raise AssertionError("EDGAR must not be asked on a cache hit")

    monkeypatch.setattr(ya, "_edgar_revenue_mix", never)
    assert YFinanceAdapter().fetch("HIT").revenue_mix == {"Japan": 1.0}


def test_default_provider_reads_the_recorded_filing(tmp_path):
    client = EdgarClient(tmp_path, transport=FixtureTransport(geo_routes()), sleep=lambda s: None)
    res = ya._edgar_revenue_mix("BLK", date(2026, 6, 30), client=client)
    assert res.reason is None and res.mix is not None
    assert set(res.mix.mix) == {"Americas", "Europe", "AsiaPacific"}
