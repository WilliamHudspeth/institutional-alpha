"""Chen and Zimmermann Open Source Asset Pricing (OSAP) portfolio returns.

Uses the "original paper" portfolio file (``PredictorPortsFull.csv``): monthly
returns for about 200 predictors, one row per (signal, portfolio, month), where
portfolio ``LS`` is the long-short spread. Returns are in percent and the
long-short leg is already signed in the original paper's direction.

The files live in a Google Drive folder per release. The optional
``openassetpricing`` package (``pip install openassetpricing``) is used only to
look up the download link for a release; the file itself goes through
:class:`DownloadCache`, so it gets the same SHA-256 record as the other Track B
files and a warm cache needs neither the package nor the network. Firm-level
signals are keyed by CRSP PERMNO and are not used.
"""

from __future__ import annotations

import io
from collections.abc import Callable

import pandas as pd

from .cache import DownloadCache, TrackBDataError

DEFAULT_RELEASE = 202510
LONG_SHORT = "LS"

# release, download_name -> URL. Injectable so tests need neither the package nor Drive.
UrlResolver = Callable[[int, str], str]

_PORT_COLUMNS = ["signalname", "port", "date", "ret"]
_DOC_COLUMNS = ["Acronym", "Sign"]


def _package_resolver(release: int, download_name: str) -> str:
    try:
        import openassetpricing as oap
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise TrackBDataError(
            "OSAP needs the optional 'openassetpricing' package to find its download "
            "links: pip install openassetpricing"
        ) from exc
    return str(oap.OpenAP(release)._get_url(download_name))


def parse_osap_portfolios(raw: pd.DataFrame) -> pd.DataFrame:
    """Validate the portfolio file and convert returns to decimals."""
    missing = [c for c in _PORT_COLUMNS if c not in raw.columns]
    if missing:
        raise TrackBDataError(f"OSAP portfolio file lacks columns {missing}")
    out = raw.copy()
    out["port"] = out["port"].astype(str).str.strip()
    out["date"] = pd.to_datetime(out["date"]) + pd.offsets.MonthEnd(0)
    out["ret"] = pd.to_numeric(out["ret"], errors="coerce") / 100.0
    if out.duplicated(["signalname", "port", "date"]).any():
        raise TrackBDataError("OSAP file has duplicate (signal, port, month) rows")
    return out.sort_values(["signalname", "port", "date"]).reset_index(drop=True)


def load_osap_portfolios(
    release: int = DEFAULT_RELEASE,
    cache: DownloadCache | None = None,
    resolver: UrlResolver | None = None,
) -> pd.DataFrame:
    """Long table of OSAP original-paper portfolio returns (all portfolios, decimals)."""
    cache = cache or DownloadCache()
    resolve = resolver or _package_resolver
    body = cache.fetch(f"osap_{release}_PredictorPortsFull.csv", lambda: resolve(release, "op"))
    raw = pd.read_csv(io.BytesIO(body), dtype={"port": str}, na_values=["NA"])
    return parse_osap_portfolios(raw)


def osap_long_short(portfolios: pd.DataFrame) -> pd.DataFrame:
    """Date x signal matrix of long-short returns."""
    ls = portfolios[portfolios["port"] == LONG_SHORT]
    if ls.empty:
        raise TrackBDataError("OSAP portfolio table has no LS rows")
    return ls.pivot(index="date", columns="signalname", values="ret").sort_index()


def load_osap_signal_signs(
    release: int = DEFAULT_RELEASE,
    cache: DownloadCache | None = None,
    resolver: UrlResolver | None = None,
) -> dict[str, int]:
    """Original-paper sign of each signal from ``SignalDoc.csv`` (+1: high values earn more)."""
    cache = cache or DownloadCache()
    resolve = resolver or _package_resolver
    body = cache.fetch(f"osap_{release}_SignalDoc.csv", lambda: resolve(release, "signal_doc"))
    doc = pd.read_csv(io.BytesIO(body), na_values=["NA"])
    missing = [c for c in _DOC_COLUMNS if c not in doc.columns]
    if missing:
        raise TrackBDataError(f"OSAP SignalDoc lacks columns {missing}")
    doc = doc.dropna(subset=_DOC_COLUMNS)
    return {str(a): int(s) for a, s in zip(doc["Acronym"], doc["Sign"], strict=True)}
