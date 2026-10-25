"""Offline tests for EDGAR Form 25 delistings parser and classifier."""

from __future__ import annotations

from typing import Any

import pandas as pd
import pytest

from iam.backtest.track_a.delistings import (
    SHUMWAY_RETURNS,
    Delisting,
    Form25,
    classify_delisting,
    common_delisting,
    delisting_return,
    fetch_delisting,
    filings_frame,
    is_common_class,
    parse_form25_xml,
)
from iam.backtest.track_a.errors import TrackADataError
from iam.data.edgar.client import EdgarError

TWITTER_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<notificationOfRemoval>
  <schemaVersion>X0203</schemaVersion>
  <exchange><cik>0000876661</cik><entityName>NEW YORK STOCK EXCHANGE LLC</entityName></exchange>
  <issuer><cik>0001418091</cik><entityName>TWITTER, INC.</entityName><fileNumber>001-36164</fileNumber></issuer>
  <descriptionClassSecurity>Common Stock</descriptionClassSecurity>
  <ruleProvision>17 CFR 240.12d2-2(a)(3)</ruleProvision>
  <signatureData>signed</signatureData>
</notificationOfRemoval>
"""


def _make_xml(
    *,
    exchange_name: str = "NEW YORK STOCK EXCHANGE LLC",
    exchange_cik: str = "0000876661",
    class_desc: str = "Common Stock",
    rule: str = "17 CFR 240.12d2-2(a)(3)",
    xmlns: str = "",
) -> bytes:
    ns_attr = f' xmlns="{xmlns}"' if xmlns else ""
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f"<notificationOfRemoval{ns_attr}>"
        f"<schemaVersion>X0203</schemaVersion>"
        f"<exchange><cik>{exchange_cik}</cik><entityName>{exchange_name}</entityName></exchange>"
        f"<issuer><cik>0001418091</cik><entityName>TEST CORP</entityName></issuer>"
        f"<descriptionClassSecurity>{class_desc}</descriptionClassSecurity>"
        f"<ruleProvision>{rule}</ruleProvision>"
        f"</notificationOfRemoval>"
    ).encode()


def test_filings_frame_merges_and_deduplicates() -> None:
    submissions = {
        "filings": {
            "recent": {
                "accessionNumber": ["0001-22-000003", "0001-22-000002"],
                "filingDate": ["2022-10-28", "2022-07-26"],
                "form": ["25-NSE", "DEFM14A"],
                "items": ["", ""],
                "primaryDocument": ["xslF25X02/primary_doc.xml", "defm14a.htm"],
            }
        }
    }
    page = {
        "accessionNumber": ["0001-22-000002", "0001-20-000001"],
        "filingDate": ["2022-07-26", "2020-05-22"],
        "form": ["DEFM14A", "8-K"],
        "items": ["", "1.03,9.01"],
        "primaryDocument": ["defm14a.htm", "form8k.htm"],
    }
    df = filings_frame(submissions, [page])
    assert list(df.columns) == ["accession", "filed", "form", "items", "primary_document"]
    assert list(df["accession"]) == [
        "0001-20-000001",
        "0001-22-000002",
        "0001-22-000003",
    ]
    assert df.loc[0, "items"] == ("1.03", "9.01")
    assert df.loc[1, "items"] == ()
    assert df.loc[2, "filed"] == pd.Timestamp("2022-10-28")


def test_parse_form25_xml_twitter_and_namespace() -> None:
    f25 = parse_form25_xml(TWITTER_XML, "0001-22-000003", "2022-10-28")
    assert f25 == Form25(
        accession="0001-22-000003",
        filed=pd.Timestamp("2022-10-28"),
        exchange_cik="0000876661",
        exchange_name="NEW YORK STOCK EXCHANGE LLC",
        exchange="nyse",
        class_description="Common Stock",
        rule="a3",
        is_common=True,
    )

    namespaced = _make_xml(xmlns="http://www.sec.gov/edgar/form25")
    f25_ns = parse_form25_xml(namespaced, "0001-22-000004", pd.Timestamp("2022-10-28"))
    assert f25_ns.exchange == "nyse"
    assert f25_ns.rule == "a3"
    assert f25_ns.is_common is True


def test_parse_form25_xml_refuses_doctype() -> None:
    bad = b'<?xml version="1.0"?><!DOCTYPE foo><notificationOfRemoval></notificationOfRemoval>'
    with pytest.raises(TrackADataError, match="DOCTYPE"):
        parse_form25_xml(bad, "0001-22-000001", "2022-01-01")


@pytest.mark.parametrize(
    ("entity_name", "expected"),
    [
        ("The NASDAQ Stock Market LLC", "nasdaq"),
        ("NYSE American LLC", "amex"),
        ("NYSE MKT LLC", "amex"),
        ("NYSE Arca, Inc.", "arca"),
        ("Cboe BZX Exchange, Inc.", "cboe"),
        ("NEW YORK STOCK EXCHANGE LLC", "nyse"),
        ("IEX Exchange", "other"),
    ],
)
def test_parse_form25_exchange_mapping(entity_name: str, expected: str) -> None:
    xml = _make_xml(exchange_name=entity_name, rule="unrecognized text")
    parsed = parse_form25_xml(xml, "accn", "2022-01-01")
    assert parsed.exchange == expected
    assert parsed.rule == "unknown"


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("Common Stock", True),
        ("Class A Common Stock, par value $0.0001", True),
        ("Common Stock Purchase Warrants", False),
        # A rights plan attached to the common stock is still the common class.
        (
            "Common Stock, par value $.01 per share, and associated Preferred Stock Purchase Rights",
            True,
        ),
        ("Common Stock (including the associated Series A Junior Participating Rights)", True),
        ("Common Stock, $0.01 par value, with attached preferred share purchase rights", True),
        ("Class A Common Stock (including shareholder rights)", True),
        ("Rights to Purchase Series A Preferred Stock", False),
        ("Rights to purchase Common Stock", False),
        ("Units, each consisting of one share of Class A common stock and one-half warrant", False),
        ("Common Stock and Warrants", False),
        # Structured products named after the common stock (Citigroup, 2012) and ETNs.
        ("Tangible Dividend Enhanced Common Stock (T-DECS)", False),
        ("Guarantor of Citi FI Enhanced Europe 50 ETNs due March 22, 2028", False),
        ("See Attached", None),
        ("6.375% Senior Notes due 2025", False),
        ("Depositary Shares, each representing 1/1000th of a share of Series A Preferred", False),
        ("Ordinary Shares", True),
        ("Shares of Beneficial Interest", True),
        ("", None),
        ("Units", False),
        ("American Depositary Shares", True),
        ("Series B Trust Preferred Securities", False),
    ],
)
def test_is_common_class(description: str, expected: bool | None) -> None:
    assert is_common_class(description) is expected


def _filings_df(rows: list[tuple[str, str, str, str]]) -> pd.DataFrame:
    return filings_frame(
        {
            "accessionNumber": [r[0] for r in rows],
            "filingDate": [r[1] for r in rows],
            "form": [r[2] for r in rows],
            "items": [r[3] for r in rows],
            "primaryDocument": ["doc.htm" for _ in rows],
        }
    )


def _sample_form25(
    rule: str = "a3",
    filed: str = "2022-10-28",
    exchange: str = "nyse",
    is_common: bool | None = True,
    accession: str = "0001-22-000100",
) -> Form25:
    return Form25(
        accession=accession,
        filed=pd.Timestamp(filed),
        exchange_cik="0000876661",
        exchange_name="NEW YORK STOCK EXCHANGE LLC",
        exchange=exchange,
        class_description="Common Stock" if is_common else "",
        rule=rule,
        is_common=is_common,
    )


def test_classify_delisting_cases_and_lookahead_guard() -> None:
    # a3 + DEFM14A -> merger with both evidence strings
    filings_merger = _filings_df(
        [
            ("acc-defm", "2022-07-26", "DEFM14A", ""),
            ("acc-late", "2022-12-27", "8-K", "1.03"),  # 60 days after Form 25 -> ignored
        ]
    )
    d_merger = classify_delisting(_sample_form25(rule="a3"), filings_merger, 1418091)
    assert d_merger.category == "merger"
    assert d_merger.effective == pd.Timestamp("2022-11-07")
    assert "rule 12d2-2(a)(3)" in d_merger.evidence
    assert "DEFM14A on 2022-07-26" in d_merger.evidence
    assert all("2022-12-27" not in ev for ev in d_merger.evidence)

    # b -> performance
    d_b = classify_delisting(_sample_form25(rule="b"), _filings_df([]), 100)
    assert d_b.category == "performance"
    assert d_b.evidence == ("rule 12d2-2(b)",)

    # c + 8-A12B 30 days later -> transfer
    filings_transfer = _filings_df([("acc-8a", "2022-11-27", "8-A12B", "")])
    d_transfer = classify_delisting(_sample_form25(rule="c"), filings_transfer, 100)
    assert d_transfer.category == "transfer"
    assert "8-A12B on 2022-11-27" in d_transfer.evidence

    # c alone -> voluntary
    d_vol = classify_delisting(_sample_form25(rule="c"), _filings_df([]), 100)
    assert d_vol.category == "voluntary"

    # 8-K 1.03 with rule a3 -> performance (bankruptcy beats everything)
    filings_bk = _filings_df([("acc-bk", "2022-05-22", "8-K", "1.03")])
    d_bk = classify_delisting(_sample_form25(rule="a3"), filings_bk, 100)
    assert d_bk.category == "performance"
    assert "8-K 1.03 on 2022-05-22" in d_bk.evidence


def test_common_delisting_selection_and_periodic_stop_rule() -> None:
    pref = _sample_form25(rule="a1", filed="2021-03-01", is_common=False, accession="acc-pref")
    comm = _sample_form25(rule="a3", filed="2022-10-28", is_common=True, accession="acc-comm")

    # preferred first then common later -> the common one
    res = common_delisting([pref, comm], _filings_df([]), 1418091)
    assert res is not None
    assert res.accession == "acc-comm"
    assert res.category == "merger"

    # only preferreds -> None
    assert common_delisting([pref], _filings_df([]), 1418091) is None

    # a transfer to another exchange in 2014, then a bankruptcy delisting in 2019 -> 2019
    moved = _sample_form25(rule="c", filed="2014-03-03", accession="acc-move")
    failed = _sample_form25(rule="b", filed="2019-06-03", accession="acc-fail")
    filings_moved = _filings_df([("acc-8a", "2014-03-20", "8-A12B", "")])
    terminal = common_delisting([moved, failed], filings_moved, 1418091)
    assert terminal is not None
    assert (terminal.accession, terminal.category) == ("acc-fail", "performance")
    # a transfer alone is not a delisting
    assert common_delisting([moved], filings_moved, 1418091) is None

    # Rule (a)(3) after which the same CIK keeps filing: a reorganisation, not a delisting
    # (ExxonMobil, July 2026). The same event with reports stopping is a merger.
    reorg = _sample_form25(rule="a3", filed="2026-07-02", accession="acc-reorg")
    keeps_filing = _filings_df([("acc-10q", "2026-11-04", "10-Q", "")])
    assert common_delisting([reorg], keeps_filing, 34088) is None
    relists = _filings_df([("acc-8a", "2026-06-25", "8-A12B", "")])
    assert common_delisting([reorg], relists, 34088) is None
    stops = _filings_df([("acc-10q", "2026-08-01", "10-Q", "")])
    recent = common_delisting([reorg], stops, 34088, observed="2026-08-15")
    assert recent.category == "merger"
    assert any(e.startswith("provisional") for e in recent.evidence)  # only 44 days observed
    # A merged-away company stops filing; the flag clears with the observation date.
    settled = common_delisting([reorg], stops, 34088, observed="2027-01-05")
    assert settled.category == "merger"
    assert not any(e.startswith("provisional") for e in settled.evidence)

    # A bankruptcy delisting stays terminal even though the company keeps reporting.
    bk = _sample_form25(rule="b", filed="2020-10-30", accession="acc-bk")
    assert common_delisting([bk], keeps_filing, 1657853).category == "performance"

    # class None with 10-Q filed 200 days later -> None
    unk = _sample_form25(rule="unknown", filed="2020-01-01", is_common=None, accession="acc-unk")
    filings_active = _filings_df([("acc-10q", "2020-07-20", "10-Q", "")])
    assert common_delisting([unk], filings_active, 1418091) is None

    # class None and reports stopped -> used with extra evidence string
    res_stopped = common_delisting([unk], _filings_df([]), 1418091)
    assert res_stopped is not None
    assert res_stopped.accession == "acc-unk"
    assert "class not stated; periodic reports stopped" in res_stopped.evidence


def test_delisting_return_cases() -> None:
    d_perf_nyse = Delisting(
        cik=1,
        form25_filed=pd.Timestamp("2022-10-28"),
        effective=pd.Timestamp("2022-11-07"),
        exchange="nyse",
        rule="b",
        category="performance",
        evidence=("rule 12d2-2(b)",),
        accession="acc1",
    )
    d_perf_nasdaq = Delisting(**{**d_perf_nyse.__dict__, "exchange": "nasdaq"})
    d_perf_cboe = Delisting(**{**d_perf_nyse.__dict__, "exchange": "cboe"})
    d_merger = Delisting(**{**d_perf_nyse.__dict__, "category": "merger"})

    assert delisting_return(d_perf_nyse, "drop") is None
    assert delisting_return(d_perf_nyse, "last_price") == 0.0
    assert delisting_return(d_perf_nyse, "penalised") == SHUMWAY_RETURNS["nyse"] == -0.30
    assert delisting_return(d_perf_nasdaq, "penalised") == -0.55
    assert delisting_return(d_perf_cboe, "penalised") == -0.30
    # An unknown exchange takes the larger penalty, never silently dropping out.
    d_perf_other = Delisting(**{**d_perf_nyse.__dict__, "exchange": "other"})
    assert delisting_return(d_perf_other, "penalised") == -0.55
    assert delisting_return(d_merger, "penalised") == 0.0

    with pytest.raises(ValueError, match="Unknown delisting return case"):
        delisting_return(d_perf_nyse, "invalid")


class _FakeClient:
    def __init__(
        self,
        submissions_data: dict[str, Any],
        pages: dict[str, dict[str, Any]],
        archives: dict[tuple[int, str, str], bytes],
    ) -> None:
        self._sub = submissions_data
        self._pages = pages
        self._archives = archives

    def submissions(self, cik: int) -> dict[str, Any]:
        return self._sub

    def submissions_page(self, name: str) -> dict[str, Any]:
        return self._pages[name]

    def archive_file(self, cik: int, accn: str, name: str) -> bytes:
        key = (int(cik), accn, name)
        if key not in self._archives:
            raise EdgarError(f"404 for {key}")
        return self._archives[key]


def test_fetch_delisting_with_fake_client() -> None:
    sub = {
        "filings": {
            "recent": {
                "accessionNumber": ["0001-22-000003"],
                "filingDate": ["2022-10-28"],
                "form": ["25-NSE"],
                "items": [""],
                "primaryDocument": ["xslF25X02/primary_doc.xml"],
            },
            "files": [{"name": "CIK0001418091-submissions-001.json"}],
        }
    }
    pages = {
        "CIK0001418091-submissions-001.json": {
            "accessionNumber": ["0001-22-000002"],
            "filingDate": ["2022-07-26"],
            "form": ["DEFM14A"],
            "items": [""],
            "primaryDocument": ["defm14a.htm"],
        }
    }
    archives = {(1418091, "0001-22-000003", "primary_doc.xml"): TWITTER_XML}
    client = _FakeClient(sub, pages, archives)

    res = fetch_delisting(client, 1418091)  # type: ignore[arg-type]
    assert res is not None
    assert res.cik == 1418091
    assert res.category == "merger"
    assert res.exchange == "nyse"
    assert res.effective == pd.Timestamp("2022-11-07")
    assert res.evidence == ("rule 12d2-2(a)(3)", "DEFM14A on 2022-07-26")

    # Missing XML fallback (older text Form 25) -> class None, rule unknown
    client_missing = _FakeClient(sub, pages, {})
    res_missing = fetch_delisting(client_missing, 1418091)  # type: ignore[arg-type]
    assert res_missing is not None
    assert res_missing.rule == "unknown"
    assert res_missing.category == "merger"
    assert "class not stated; periodic reports stopped" in res_missing.evidence
