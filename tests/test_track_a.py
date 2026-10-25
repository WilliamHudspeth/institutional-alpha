"""Offline tests for the Track A universe, ticker hints, bulk reader and coverage report."""

import json
import re
import zipfile
from datetime import date

import numpy as np
import pandas as pd
import pytest

from iam.backtest.track_a import bulk, coverage, tickers, universe
from iam.backtest.track_a.errors import TrackADataError
from iam.data.edgar.facts import MAX_STALE_DAYS


def _fact(val, start, end, filed, form="10-K", accn=None):
    row = {"val": val, "end": end, "filed": filed, "form": form, "accn": accn or f"a-{filed}-{end}"}
    if start:
        row["start"] = start
    return row


def _doc(cik, revenue_rows, float_rows=(), name="Co", tag="Revenues", extra=None):
    gaap = {tag: {"units": {"USD": list(revenue_rows)}}}
    gaap.update(extra or {})
    return {
        "cik": cik,
        "entityName": name,
        "facts": {
            "us-gaap": gaap,
            "dei": {"EntityPublicFloat": {"units": {"USD": list(float_rows)}}},
        },
    }


def _annuals(scale, years=range(2008, 2016), lag_days=60):
    """One 10-K revenue fact per calendar fiscal year, filed ``lag_days`` after year end."""
    rows = []
    for y in years:
        filed = (pd.Timestamp(f"{y}-12-31") + pd.Timedelta(days=lag_days)).date().isoformat()
        rows.append(_fact(scale * (1 + 0.05 * (y - 2008)), f"{y}-01-01", f"{y}-12-31", filed))
    return rows


def _floats(value, years=range(2008, 2016)):
    return [_fact(value, None, f"{y}-06-30", f"{y + 1}-03-01") for y in years]


# --------------------------------------------------------------------------- universe


class TestUniverse:
    def test_availability_uses_one_business_day_lag(self):
        assert universe.as_of_for(pd.Timestamp("2011-03-31")) == date(2011, 3, 30)
        # Month ending on a Monday: the usable filing date is the previous Friday.
        assert universe.as_of_for(pd.Timestamp("2014-03-31")) == date(2014, 3, 28)

    def test_filing_is_invisible_until_after_its_filed_date(self):
        doc = _doc(1, [_fact(1e9, "2010-01-01", "2010-12-31", "2011-03-31")],
                   _floats(5e8, range(2009, 2012)))  # fmt: skip
        months = [pd.Timestamp("2011-03-31"), pd.Timestamp("2011-04-30")]
        rows = universe.evaluate_filer(doc, months, size_measure="revenue")
        assert rows[0].revenue_ttm is None and "no Revenues fiscal-year fact" in rows[0].reason
        assert rows[1].revenue_ttm == pytest.approx(1e9) and rows[1].reason is None
        # Ranking on float, the member stays eligible and the revenue gap is only recorded.
        by_float = universe.evaluate_filer(doc, months)
        assert by_float[0].reason is None and by_float[0].revenue_reason is not None

    def test_restatement_counts_only_once_filed(self):
        rows = [
            _fact(1e9, "2010-01-01", "2010-12-31", "2011-03-01", accn="orig"),
            _fact(8e8, "2010-01-01", "2010-12-31", "2011-09-15", form="10-K/A", accn="restated"),
        ]
        doc = _doc(1, rows, _floats(5e8, range(2009, 2012)))
        months = [pd.Timestamp("2011-08-31"), pd.Timestamp("2011-09-30")]
        before, after = universe.evaluate_filer(doc, months)
        assert before.revenue_ttm == pytest.approx(1e9)
        assert after.revenue_ttm == pytest.approx(8e8)

    def test_memoised_evaluation_matches_month_by_month(self):
        rng = np.random.default_rng(0)
        rows = []
        for y in range(2008, 2015):
            filed_k = f"{y + 1}-02-{int(rng.integers(10, 28))}"
            rows.append(_fact(float(rng.uniform(1e9, 2e9)), f"{y}-01-01", f"{y}-12-31", filed_k))
            for q, end in ((1, "03-31"), (2, "06-30"), (3, "09-30")):
                filed_q = (pd.Timestamp(f"{y}-{end}") + pd.Timedelta(days=40)).date().isoformat()
                rows.append(_fact(float(rng.uniform(2e8, 5e8)) * q, f"{y}-01-01", f"{y}-{end}",
                                  filed_q, form="10-Q"))  # fmt: skip
        doc = _doc(7, rows, _floats(3e8, range(2008, 2013)))  # floats stop: later months fail
        months = universe.month_ends("2009-01-31", "2016-12-31")
        fast = universe.evaluate_filer(doc, months, size_measure="revenue")
        for m, row in zip(months, fast):
            as_of = universe.as_of_for(m)
            ttm = universe.revenue_as_of(doc, as_of)
            flt, _, float_reason = universe.public_float_as_of(doc, as_of)
            reason = ttm.reason if ttm.value is None else float_reason
            # Same outcome. The messages may differ in the date they quote (filing date versus
            # as-of) and in how many other tags they list, so compare the first clause only.
            assert (row.reason is None) == (reason is None), m
            if reason is not None:

                def first(text: str) -> str:
                    return re.sub(r"\d{4}-\d{2}-\d{2}", "D", text.split(";")[0])

                assert first(row.reason) == first(reason), m
            if reason is None:
                assert row.revenue_ttm == pytest.approx(ttm.value), m
                assert row.public_float == pytest.approx(flt), m

    def test_stale_revenue_is_excluded(self):
        doc = _doc(1, _annuals(1e9, range(2008, 2011)), _floats(5e8, range(2008, 2013)))
        last_end = date(2010, 12, 31)
        late = pd.Timestamp(last_end) + pd.Timedelta(days=MAX_STALE_DAYS + 40)
        (row,) = universe.evaluate_filer(doc, [late + pd.offsets.MonthEnd(0)], "revenue")
        assert row.revenue_ttm is None and "stale" in row.reason

    def test_requires_positive_recent_public_float(self):
        no_float = _doc(1, _annuals(1e9))
        zero = _doc(2, _annuals(1e9), [_fact(0, None, "2011-06-30", "2012-03-01")])
        old = _doc(3, _annuals(1e9), [_fact(5e8, None, "2009-06-30", "2010-03-01")])
        m = [pd.Timestamp("2012-06-30")]
        assert "no public float" in universe.evaluate_filer(no_float, m)[0].reason
        assert "no positive public float" in universe.evaluate_filer(zero, m)[0].reason
        assert "older than" in universe.evaluate_filer(old, m)[0].reason

    def test_a_zero_float_between_positive_years_is_ignored(self):
        # AT&T's 10-K filed 2011-03-01 reports a float of 0 between $146.6B and $186.1B.
        floats = [
            _fact(146.6e9, None, "2009-06-30", "2010-02-25"),
            _fact(146.6e9, None, "2009-06-30", "2010-11-05", form="10-Q"),  # repeated on 10-Qs
            _fact(0, None, "2010-12-31", "2011-03-01"),
            _fact(186.1e9, None, "2011-06-30", "2012-02-24"),
        ]
        doc = _doc(732717, _annuals(1.2e11), floats)
        june, march = universe.evaluate_filer(
            doc, [pd.Timestamp("2011-06-30"), pd.Timestamp("2012-03-31")]
        )
        assert june.reason is None and june.public_float == pytest.approx(146.6e9)
        assert june.float_as_of == date(2009, 6, 30)
        assert march.public_float == pytest.approx(186.1e9)

    def test_bank_composite_only_when_standard_tags_fail(self):
        legs = {
            "InterestAndDividendIncomeOperating": {"units": {"USD": _annuals(6e8)}},
            "NoninterestIncome": {"units": {"USD": _annuals(4e8)}},
        }
        bank = _doc(1, [], _floats(5e8), tag="Unused", extra=legs)
        ttm = universe.revenue_as_of(bank, date(2012, 6, 30))
        assert ttm.value == pytest.approx((6e8 + 4e8) * 1.15)
        assert ttm.method.startswith("bank")
        both = _doc(2, _annuals(2e9), _floats(5e8), extra=legs)
        assert universe.revenue_as_of(both, date(2012, 6, 30)).tag == "Revenues"

    def test_ever_large_prefilter(self):
        assert universe.ever_large(_doc(1, _annuals(3e8)))
        assert not universe.ever_large(_doc(2, _annuals(1e8, range(2008, 2010))))
        quarterly_only = _doc(3, [_fact(9e9, "2010-01-01", "2010-03-31", "2010-05-01", "10-Q")])
        assert not universe.ever_large(quarterly_only)
        # No standard revenue tag at all, but a large float: still evaluated.
        assert universe.ever_large(_doc(4, [], _floats(2e9), tag="Unused"))

    def test_ranking_by_float_by_revenue_and_exclusions(self):
        docs = [
            _doc(1, _annuals(5e9), _floats(1e10), name="Big float"),
            _doc(3, _annuals(9e9), _floats(2e9), name="Big revenue"),
            _doc(4, _annuals(2e10), name="Private filer"),
            _doc(5, _annuals(1e9), _floats(1e9), name="Small"),
            _doc(6, [], _floats(8e9), tag="Unused", name="No standard revenue tag"),
        ]
        by_float, excluded = universe.build_universe(docs, "2012-06-30", "2012-06-30", size=3)
        assert by_float["cik"].tolist() == [1, 6, 3]
        assert by_float["rank"].tolist() == [1, 2, 3]
        assert (by_float["size_measure"] == "public_float").all()
        assert pd.isna(by_float.loc[1, "revenue_ttm"])  # recorded as missing, still a member
        reasons = dict(zip(excluded["cik"], excluded["reason"]))
        assert "no public float" in reasons[4]
        assert 5 not in reasons  # eligible but below the cut, not an exclusion

        by_rev, excluded = universe.build_universe(
            docs, "2012-06-30", "2012-06-30", size=2, size_measure="revenue"
        )
        assert by_rev["cik"].tolist() == [3, 1]
        assert 6 in set(excluded["cik"])  # no revenue: excluded when ranking on it

    def test_no_merging_on_matching_figures(self):
        docs = [
            _doc(1, _annuals(5e9), _floats(1e10), name="Parent"),
            # Registrant subsidiary filing alongside its parent: no positive float, so excluded.
            _doc(2, _annuals(5e9), [_fact(0, None, "2011-06-30", "2012-03-01")], name="OpCo"),
            # Unrelated companies with the same rounded float, or revenue 0.1% away: both stay.
            _doc(3, _annuals(5e9 * 1.001), _floats(8e9), name="Unrelated A"),
            _doc(4, _annuals(2e9), _floats(8e9), name="Unrelated B, same float"),
        ]
        members, excluded = universe.build_universe(docs, "2012-06-30", "2012-06-30", size=10)
        assert members["cik"].tolist() == [1, 3, 4]
        assert "no positive public float" in excluded.set_index("cik").loc[2, "reason"]

    def test_delisted_filers_leave_from_the_effective_date(self):
        docs = [_doc(1, _annuals(5e9), _floats(1e10)), _doc(2, _annuals(4e9), _floats(9e9))]
        members, excluded = universe.build_universe(
            docs, "2012-05-31", "2012-07-31", delisted={2: pd.Timestamp("2012-06-15")}
        )
        per_month = members.groupby("month_end")["cik"].apply(list).to_dict()
        assert per_month[pd.Timestamp("2012-05-31")] == [1, 2]
        assert per_month[pd.Timestamp("2012-06-30")] == [1]
        assert "delisted, effective 2012-06-15" in set(excluded["reason"])

    def test_unknown_size_measure_raises(self):
        with pytest.raises(ValueError):
            universe.build_universe([], "2012-01-31", "2012-01-31", size_measure="market_cap")


# --------------------------------------------------------------------------- tickers


class TestTickers:
    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("twtr-20211231.htm", "TWTR"),
            ("aapl-20230930_htm.xml", "AAPL"),
            ("xslF25X02/primary_doc.xml", None),
            ("d283119d10k.htm", None),
            ("brk.a-20231231.htm", "BRK-A"),
            ("form10-k.htm", None),
            ("ex-20231231.htm", None),
            ("lehman-20081130.xml", "LEHMAN"),
        ],
    )
    def test_document_names(self, name, expected):
        assert tickers.ticker_from_document(name) == expected

    def test_spans_and_lookup(self):
        filings = pd.DataFrame(
            {
                "filed": pd.to_datetime(["2019-05-01", "2019-08-01", "2020-02-01", "2020-05-01",
                                         "2020-08-01"]),
                "form": ["10-Q", "10-Q", "10-K", "10-Q", "8-K"],
                "accession": ["a1", "a2", "a3", "a4", "a5"],
                "primary_document": ["old-20190331.htm", "old-20190630.htm", "new-20191231.htm",
                                     "new-20200331.htm", "old-20200801.htm"],
            }
        )  # fmt: skip
        hints = tickers.hints_from_filings(filings)
        assert len(hints) == 4  # the 8-K is not a periodic filing
        spans = tickers.ticker_spans(hints)
        assert spans["ticker"].tolist() == ["OLD", "NEW"]
        assert tickers.ticker_at(spans, pd.Timestamp("2019-12-31")) == "OLD"
        assert tickers.ticker_at(spans, pd.Timestamp("2020-03-01")) == "NEW"
        assert tickers.ticker_at(spans, pd.Timestamp("2019-01-01")) is None
        # A hint filed on the day itself is not yet usable (one business day of lag).
        assert tickers.ticker_at(spans, pd.Timestamp("2020-02-01")) == "OLD"
        # Hints that stopped long ago are not trusted.
        assert tickers.ticker_at(spans, pd.Timestamp("2022-06-30")) is None

    def test_hint_from_index_prefers_instance(self):
        index = {"directory": {"item": [
            {"name": "d123d10k.htm"}, {"name": "leh-20071130_cal.xml"},
            {"name": "leh-20071130.xsd"}, {"name": "leh-20071130.xml"},
        ]}}  # fmt: skip
        assert tickers.hint_from_index(index) == "LEH"
        assert tickers.hint_from_index({"directory": {"item": [{"name": "d1d10k.htm"}]}}) is None

    def test_reused_tickers(self):
        a = pd.DataFrame({"ticker": ["GM"], "first_filed": [pd.Timestamp("2005-01-01")],
                          "last_filed": [pd.Timestamp("2009-05-01")], "n_filings": [10]})  # fmt: skip
        b = a.assign(first_filed=pd.Timestamp("2010-11-01"), last_filed=pd.Timestamp("2026-01-01"))
        c = a.assign(ticker="F")
        out = tickers.reused_tickers({1: a, 2: b, 3: c})
        assert out["cik"].tolist() == [1, 2]


# --------------------------------------------------------------------------- bulk


class TestBulk:
    def test_iter_companyfacts_filters_by_cik(self, tmp_path):
        path = tmp_path / "companyfacts.zip"
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("CIK0000000001.json", json.dumps({"cik": 1, "facts": {}}))
            zf.writestr("CIK0000000002.json", json.dumps({"cik": 2, "facts": {}}))
            zf.writestr("readme.txt", "x")
            zf.writestr("CIK0000000003.json", "{}")
        assert [d["cik"] for d in bulk.iter_companyfacts(path)] == [1, 2]
        assert [d["cik"] for d in bulk.iter_companyfacts(path, {2})] == [2]

    def test_download_writes_record_and_reuses_it(self, tmp_path):
        body = b"zip-bytes" * 1000

        class Resp:
            status_code = 200

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def iter_content(self, n):
                yield body[:500]
                yield body[500:]

        class Session:
            calls = 0

            def get(self, url, **kw):
                Session.calls += 1
                assert kw["headers"]["User-Agent"] == "Test Agent test@example.com"
                return Resp()

        clock = lambda: 1_700_000_000.0  # noqa: E731
        path, rec = bulk.download_companyfacts(
            tmp_path, user_agent="Test Agent test@example.com", session=Session(), wall_clock=clock
        )
        assert path.read_bytes() == body and rec.size_bytes == len(body)
        assert bulk.verify(path).sha256 == rec.sha256
        bulk.download_companyfacts(tmp_path, user_agent="Test Agent test@example.com",
                                   session=Session(), wall_clock=clock)  # fmt: skip
        assert Session.calls == 1
        path.write_bytes(b"tampered")
        with pytest.raises(TrackADataError, match="SHA-256"):
            bulk.verify(path)

    def test_failed_download_leaves_no_file(self, tmp_path):
        class Resp:
            status_code = 403

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        class Session:
            def get(self, url, **kw):
                return Resp()

        with pytest.raises(TrackADataError, match="403"):
            bulk.download_companyfacts(tmp_path, user_agent="x y@z.com", session=Session())
        assert not list(tmp_path.glob("*.zip"))


# --------------------------------------------------------------------------- coverage


class TestCoverage:
    def _prices(self, cik, start, end):
        days = pd.bdate_range(start, end)
        return pd.DataFrame({"cik": cik, "date": days, "close": 10.0})

    def test_gate_uses_the_worse_group(self):
        months = pd.to_datetime(["2015-01-30", "2015-02-27"])
        members = pd.DataFrame(
            [(m, c) for m in months for c in range(1, 11)], columns=["month_end", "cik"]
        )
        # 9 survivors priced throughout; CIK 10 delists in March 2015 and has no prices.
        prices = pd.concat([self._prices(c, "2014-12-01", "2015-06-30") for c in range(1, 10)])
        delisted = pd.DataFrame({"cik": [10], "effective": [pd.Timestamp("2015-03-20")]})
        rep = coverage.coverage_report(members, prices, delisted, horizon_months=1)
        assert rep["coverage"].tolist() == [0.9, 0.9]
        assert rep["coverage_survivors"].tolist() == [1.0, 1.0]
        assert rep["coverage_later_delisted"].tolist() == [0.0, 0.0]
        assert not rep["passes_gate"].any() and rep["survivorship_biased"].all()

    def test_horizon_from_a_business_month_end(self):
        # 27 Feb 2015 is the last business day; the 1-month horizon must reach 31 March.
        members = pd.DataFrame({"month_end": [pd.Timestamp("2015-02-27")], "cik": [1]})
        prices = self._prices(1, "2015-02-01", "2015-03-31")
        rep = coverage.coverage_report(members, prices, pd.DataFrame({"cik": [], "effective": []}))
        assert rep.loc[0, "n_covered"] == 1

    def test_long_horizon_delisting_needs_a_price_near_it(self):
        members = pd.DataFrame({"month_end": [pd.Timestamp("2015-01-30")], "cik": [1]})
        delisted = pd.DataFrame({"cik": [1], "effective": [pd.Timestamp("2015-12-10")]})
        stops_early = self._prices(1, "2015-01-01", "2015-02-27")
        rep = coverage.coverage_report(members, stops_early, delisted, horizon_months=12)
        assert rep.loc[0, "n_covered"] == 0
        reaches = self._prices(1, "2015-01-01", "2015-11-25")
        rep = coverage.coverage_report(members, reaches, delisted, horizon_months=12)
        assert rep.loc[0, "n_covered"] == 1

    def test_delisting_inside_horizon_counts_as_covered(self):
        members = pd.DataFrame({"month_end": [pd.Timestamp("2015-02-27")], "cik": [1]})
        prices = self._prices(1, "2015-02-01", "2015-03-10")  # stops before the horizon end
        delisted = pd.DataFrame({"cik": [1], "effective": [pd.Timestamp("2015-03-20")]})
        rep = coverage.coverage_report(members, prices, delisted, horizon_months=1)
        assert rep.loc[0, "n_covered"] == 1 and rep.loc[0, "passes_gate"]

    def test_missing_end_price_without_delisting_is_not_covered(self):
        members = pd.DataFrame({"month_end": [pd.Timestamp("2015-02-27")], "cik": [1]})
        prices = self._prices(1, "2015-02-01", "2015-03-10")
        empty = pd.DataFrame({"cik": [], "effective": []})
        rep = coverage.coverage_report(members, prices, empty, horizon_months=1)
        assert rep.loc[0, "n_covered"] == 0
        assert coverage.summarise(rep)["months_passing_gate"] == 0

    def test_stale_price_does_not_count(self):
        members = pd.DataFrame({"month_end": [pd.Timestamp("2015-02-27")], "cik": [1]})
        prices = self._prices(1, "2015-01-01", "2015-02-13")
        prices = pd.concat([prices, self._prices(1, "2015-03-20", "2015-04-30")])
        rep = coverage.coverage_report(members, prices, pd.DataFrame({"cik": [], "effective": []}))
        assert rep.loc[0, "n_covered"] == 0
