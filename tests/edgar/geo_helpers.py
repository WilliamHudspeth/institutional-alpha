"""Helpers for the geographic-mix tests: recorded 10-K routes and a synthetic instance builder.

The recorded files are real SEC responses (see tests/fixtures/edgar/README.md). The
``synthetic_instance`` builder writes a tiny XBRL instance from hand-written numbers; it is
clearly synthetic and exists only to exercise parser rules no recorded filing happens to hit.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from iam.data.edgar import client as edgar_client
from tests.edgar.helpers import FIXTURES

ARCHIVE = "https://www.sec.gov/Archives/edgar/data"

# fixture tag -> (cik, accession, instance file name in the archive)
RECORDED_FILINGS: dict[str, tuple[int, str, str]] = {
    "AAPL_2025": (320193, "0000320193-25-000079", "aapl-20250927_htm.xml"),
    "MSFT_2025": (789019, "0000950170-25-100235", "msft-20250630_htm.xml"),
    "BLK_new_2025": (2012383, "0001193125-26-071966", "blk-20251231_htm.xml"),
    "BLK_new_2024": (2012383, "0000950170-25-026584", "blk-20241231_htm.xml"),
    "BLK_old_2019": (1364742, "0001564590-20-007807", "blk-10k_20191231_htm.xml"),
    "BLK_old_2020": (1364742, "0001564590-21-008796", "blk-10k_20201231_htm.xml"),
}
# submissions pages recorded for the filers whose 10-K is outside filings.recent
RECORDED_PAGES: dict[int, tuple[str, ...]] = {
    1364742: ("006", "007"),
    2012383: ("001", "002"),
}
_FILER_TAG = {320193: "AAPL", 789019: "MSFT", 2012383: "BLK_new", 1364742: "BLK_old"}


def archive_dir(cik: int, accn: str) -> str:
    return f"{ARCHIVE}/{cik}/{accn.replace('-', '')}"


def instance_url(tag: str) -> str:
    cik, accn, name = RECORDED_FILINGS[tag]
    return f"{archive_dir(cik, accn)}/{name}"


def geo_routes() -> dict[str, Path]:
    """Every recorded document the geographic-mix code may request."""
    routes: dict[str, Path] = {edgar_client.TICKERS_URL: FIXTURES / "company_tickers.json"}
    for cik, name in _FILER_TAG.items():
        routes[edgar_client.submissions_url(cik)] = FIXTURES / f"submissions_filings_{name}.json"
        for page in RECORDED_PAGES.get(cik, ()):
            url = edgar_client.submissions_page_url(f"CIK{cik:010d}-submissions-{page}.json")
            routes[url] = FIXTURES / f"submissions_page_{name}_{page}.json"
    for tag, (cik, accn, name) in RECORDED_FILINGS.items():
        routes[f"{archive_dir(cik, accn)}/index.json"] = FIXTURES / f"index_{tag}.json"
        routes[f"{archive_dir(cik, accn)}/{name}"] = FIXTURES / f"instance_{tag}.xml"
    return routes


# ----------------------------------------------------------------------- synthetic instance
GEO_AXIS = "srt:StatementGeographicalAxis"
PRODUCT_AXIS = "srt:ProductOrServiceAxis"

_NS = (
    'xmlns="http://www.xbrl.org/2003/instance" '
    'xmlns:us-gaap="http://fasb.org/us-gaap/2025" xmlns:srt="http://fasb.org/srt/2025" '
    'xmlns:country="http://xbrl.sec.gov/country/2025" xmlns:dei="http://xbrl.sec.gov/dei/2025" '
    'xmlns:xbrldi="http://xbrl.org/2006/xbrldi" xmlns:iso4217="http://www.xbrl.org/2003/iso4217" '
    'xmlns:co="http://example.test/2025"'
)


def fact(
    value: float | None,
    *,
    concept: str = "Revenues",
    period: tuple[str, str] = ("2025-01-01", "2025-12-31"),
    dims: Sequence[tuple[str, str]] = (),
    unit: str = "USD",
) -> dict:
    return {"value": value, "concept": concept, "period": period, "dims": tuple(dims), "unit": unit}


def geo(member: str, value: float | None, **kw) -> dict:
    return fact(value, dims=[(GEO_AXIS, member)], **kw)


def synthetic_instance(
    facts: Sequence[dict],
    *,
    period_end: str = "2025-12-31",
    doc_type: str = "10-K",
    dei_period_end: str | None = None,
) -> bytes:
    """A minimal XBRL instance. SYNTHETIC: numbers are hand-written test inputs."""
    contexts: dict[tuple, str] = {}
    units: set[str] = set()
    body: list[str] = []

    def ctx_id(period: tuple[str, str], dims: tuple[tuple[str, str], ...]) -> str:
        key = (period, dims)
        if key not in contexts:
            contexts[key] = f"c{len(contexts) + 1}"
        return contexts[key]

    dei_end = dei_period_end or period_end
    for f in facts:
        cid = ctx_id(f["period"], f["dims"])
        units.add(f["unit"])
        if f["value"] is None:
            body.append(
                f'<us-gaap:{f["concept"]} contextRef="{cid}" unitRef="{f["unit"]}" '
                'xsi:nil="true" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"/>'
            )
        else:
            body.append(
                f'<us-gaap:{f["concept"]} contextRef="{cid}" unitRef="{f["unit"]}" '
                f'decimals="-6">{f["value"]}</us-gaap:{f["concept"]}>'
            )
    dei_ctx = ctx_id(("2025-01-01", period_end), ())
    body.append(f'<dei:DocumentType contextRef="{dei_ctx}">{doc_type}</dei:DocumentType>')
    body.append(
        f'<dei:DocumentPeriodEndDate contextRef="{dei_ctx}">{dei_end}</dei:DocumentPeriodEndDate>'
    )
    parts = ['<?xml version="1.0" encoding="utf-8"?>', f"<xbrl {_NS}>"]
    for (period, dims), cid in contexts.items():
        seg = "".join(
            f'<xbrldi:explicitMember dimension="{d}">{m}</xbrldi:explicitMember>' for d, m in dims
        )
        segment = f"<segment>{seg}</segment>" if seg else ""
        parts.append(
            f'<context id="{cid}"><entity><identifier scheme="http://www.sec.gov/CIK">'
            f"0000000001</identifier>{segment}</entity><period><startDate>{period[0]}</startDate>"
            f"<endDate>{period[1]}</endDate></period></context>"
        )
    for u in sorted(units):
        parts.append(f'<unit id="{u}"><measure>iso4217:{u}</measure></unit>')
    parts.extend(body)
    parts.append("</xbrl>")
    return "\n".join(parts).encode("utf-8")
