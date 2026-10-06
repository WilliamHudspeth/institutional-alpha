"""Shared helpers for the EDGAR tests: a fixture transport and a companyfacts builder."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from iam.data.edgar import client as edgar_client

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "edgar"


class FixtureTransport:
    """Replays recorded EDGAR responses; any URL without a recording is a test failure."""

    def __init__(self, routes: dict[str, Path | bytes]) -> None:
        self.routes = routes
        self.calls: list[str] = []

    def __call__(self, url: str, headers: dict[str, str]) -> tuple[int, bytes]:
        self.calls.append(url)
        if url not in self.routes:
            raise AssertionError(f"no recorded fixture for {url}")
        body = self.routes[url]
        return 200, body.read_bytes() if isinstance(body, Path) else body


def recorded_routes() -> dict[str, Path]:
    routes: dict[str, Path] = {edgar_client.TICKERS_URL: FIXTURES / "company_tickers.json"}
    for name, cik in (
        ("AAPL", 320193),
        ("MSFT", 789019),
        ("BLK_old", 1364742),
        ("BLK_new", 2012383),
    ):
        routes[edgar_client.companyfacts_url(cik)] = FIXTURES / f"companyfacts_{name}.json"
        routes[edgar_client.submissions_url(cik)] = FIXTURES / f"submissions_{name}.json"
    return routes


def row(
    val: float,
    end: str,
    filed: str,
    *,
    start: str | None = None,
    form: str = "10-K",
    accn: str | None = None,
    fy: int = 2023,
    fp: str = "FY",
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "end": end,
        "val": val,
        "accn": accn or f"0000000000-{filed[2:4]}-{filed[5:7]}{filed[8:10]}",
        "fy": fy,
        "fp": fp,
        "form": form,
        "filed": filed,
    }
    if start is not None:
        out["start"] = start
    return out


def facts_doc(
    us_gaap: dict[str, list[dict[str, Any]]] | None = None,
    dei: dict[str, list[dict[str, Any]]] | None = None,
    us_gaap_shares: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """A minimal companyfacts document built from hand-written rows (test input only)."""
    facts: dict[str, Any] = {}
    if us_gaap:
        facts["us-gaap"] = {t: {"units": {"USD": rows}} for t, rows in us_gaap.items()}
    if us_gaap_shares:
        gaap = facts.setdefault("us-gaap", {})
        gaap.update({t: {"units": {"shares": rows}} for t, rows in us_gaap_shares.items()})
    if dei:
        facts["dei"] = {t: {"units": {"shares": rows}} for t, rows in dei.items()}
    return {"cik": 1, "entityName": "TEST CO", "facts": facts}
