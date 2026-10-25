"""Point-in-time Damodaran industry datasets (vintages published January 2000 onward).

Damodaran publishes annual industry spreadsheets in early January with market data as of
31 December and trailing accounting data. A vintage is named here by its PUBLICATION year:
a backtest date in year Y may use vintage Y from 15 January Y onward; dates on 1-14 January
use Y-1.

Archive file names carry the DATA year, one less than the publication year: ``betas24.xls``
holds data at the end of 2024 and its "Date updated" cell reads 2025-01-05 (checked for every
dated file, 2013 to 2024; files before 2013 carry no date and are assumed to follow the same
convention). Reading the suffix as the publication year would use every file a year before it
existed. The current files (``pc/datasets/<name>.xls``) are the vintage published in
``CURRENT_YEAR``.

Historical layouts vary across years (sheet names, header row offsets, header text
"Industry Name" or "Industry", column titles). This module locates sheets and columns by
normalised header text and caches every downloaded file with its SHA-256 record via
:class:`~iam.backtest.track_b.cache.DownloadCache`.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from iam.backtest.track_b.cache import DownloadCache, FileRecord, TrackBDataError, Transport

from .errors import TrackADataError
from .industry_crosswalk import INDUSTRY_CROSSWALK

ARCHIVE_URL_TEMPLATE = "https://pages.stern.nyu.edu/~adamodar/pc/archives/{name}{yy}.xls"
CURRENT_URL_TEMPLATE = "https://pages.stern.nyu.edu/~adamodar/pc/datasets/{name}.xls"

VINTAGE_AVAILABLE_DAY: tuple[int, int] = (1, 15)
# Publication years served from the archive (files 99 to 24) and from the current files.
ARCHIVE_YEARS = range(2000, 2026)
CURRENT_YEAR = 2026
MISSING_YEARS: set[int] = set()

DEFAULT_CACHE_ROOT = Path("data/reference/damodaran")
_HEADER_SCAN_ROWS = 25
_INDUSTRY_HEADERS = ("industry name", "industry")
_PREFERRED_SHEET = "Industry Averages"
_XLS_MAGIC = b"\xd0\xcf\x11\xe0"
_XLSX_MAGIC = b"PK"

# dataset -> {canonical_column: (accepted_header_texts, required)}
COLUMNS: dict[str, dict[str, tuple[tuple[str, ...], bool]]] = {
    "betas": {
        "n_firms": (("number of firms",), True),
        "beta": (("average beta", "beta"), True),
        "de_ratio": (("market d/e ratio", "d/e ratio"), True),
        "tax_rate": (("tax rate", "effective tax rate"), True),
        "unlevered_beta": (("unlevered beta",), True),
        "unlevered_beta_cash_corrected": (("unlevered beta corrected for cash...",), True),
    },
    "wacc": {
        "n_firms": (("number of firms",), True),
        "cost_of_equity": (("cost of equity",), True),
        "cost_of_debt": (("cost of debt",), True),
        "after_tax_cost_of_debt": (("after-tax cost of debt",), True),
        "cost_of_capital": (("cost of capital",), True),
    },
    "margin": {
        "n_firms": (("number of firms",), True),
        "pretax_operating_margin": (
            ("ebit/sales", "pre-tax unadjusted operating margin", "pre-tax unadjusted..."),
            True,
        ),
        "after_tax_operating_margin": (
            (
                "after-tax operating margin (ebit(1-t)/sales)",
                "after-tax unadjusted operating margin",
                "after-tax operating margin...",
                "after-tax unadjusted operating margin...",
            ),
            False,  # absent from the 2013 file, which has only lease-adjusted after-tax margins
        ),
        "net_margin": (("net margin",), True),
    },
    "fundgr": {
        "n_firms": (("number of firms",), True),
        "roe": (("roe",), True),
        "retention_ratio": (("retention ratio",), True),
        "fundamental_growth": (("fundamental growth",), True),
    },
    "vebitda": {
        "n_firms": (("number of firms",), True),
        "ev_ebitda": (("value/ebitda", "ev/ebitda"), True),
        "ev_ebit": (("value/ebit", "ev/ebit"), True),
    },
    "psdata": {
        "n_firms": (("number of firms",), True),
        "price_sales": (("price/sales",), True),
        "ev_sales": (("value/sales", "ev/sales"), True),
    },
    "pedata": {
        "n_firms": (("number of firms",), True),
        "current_pe": (("price/current eps", "current pe"), True),
        "trailing_pe": (("price/trailing eps", "trailing pe"), True),
        "expected_growth": (
            ("expected growth", "expected growth - next 5 years", "expected growth..."),
            True,
        ),
    },
    "capex": {
        "n_firms": (("number of firms",), True),
        "net_capex_sales": (("net cap ex/sales", "net cap ex/sales..."), True),
        "sales_to_capital": (
            ("sales/capital", "sales/ invested capital (ltm)", "sales/ invested capital..."),
            False,
        ),
    },
}


@dataclass(frozen=True)
class VintageChoice:
    """Resolution of the Damodaran vintage year usable on a given date."""

    year_wanted: int
    year_used: int
    stale: bool
    reason: str | None = None


@dataclass(frozen=True)
class ParsedDataset:
    """Parsed industry table from one Damodaran vintage workbook."""

    name: str
    sheet: str
    header_row: int
    frame: pd.DataFrame
    missing_optional: tuple[str, ...]


def _norm(text: object) -> str:
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return ""
    return re.sub(r"\s+", " ", str(text)).strip().lower()


def _to_float(cell: object) -> float:
    """Parse a numeric cell, numeric string, or percent string ('4.06%'), else NaN."""
    if isinstance(cell, str):
        text = cell.strip().replace(",", "")
        if not text:
            return float("nan")
        try:
            return float(text[:-1]) / 100.0 if text.endswith("%") else float(text)
        except ValueError:
            return float("nan")
    value = pd.to_numeric(cell, errors="coerce")
    return float("nan") if pd.isna(value) else float(value)


def _as_date(value: date | datetime | pd.Timestamp | str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    parsed: date = pd.Timestamp(value).date()
    return parsed


def vintage_for(dt: date | datetime | pd.Timestamp | str) -> int:
    """Return vintage year Y if ``dt`` is on or after 15 January Y, else Y - 1."""
    d = _as_date(dt)
    cutoff = date(d.year, VINTAGE_AVAILABLE_DAY[0], VINTAGE_AVAILABLE_DAY[1])
    return d.year if d >= cutoff else d.year - 1


def resolve_vintage(dt: date | datetime | pd.Timestamp | str | int) -> VintageChoice:
    """Resolve ``dt`` (or an integer vintage year) to an available vintage year.

    Falls back to the latest earlier available year when the wanted year is
    missing, setting ``stale=True`` with a reason. Never uses a vintage newer
    than the wanted year. Raises :class:`ValueError` for years before the first vintage (2000).
    """
    if isinstance(dt, int) and not isinstance(dt, bool):
        year_wanted = dt
    else:
        year_wanted = vintage_for(dt)

    available = sorted(set(ARCHIVE_YEARS) | {CURRENT_YEAR})
    if year_wanted < available[0]:
        raise ValueError(
            f"Damodaran vintage {year_wanted} is before the first archive year ({available[0]})"
        )
    if year_wanted in available and year_wanted not in MISSING_YEARS:
        return VintageChoice(
            year_wanted=year_wanted,
            year_used=year_wanted,
            stale=False,
            reason=None,
        )

    earlier = [y for y in available if y < year_wanted and y not in MISSING_YEARS]
    if not earlier:
        raise ValueError(f"no Damodaran vintage available on or before {year_wanted}")
    year_used = earlier[-1]
    return VintageChoice(
        year_wanted=year_wanted,
        year_used=year_used,
        stale=True,
        reason=f"vintage {year_wanted} is unavailable; falling back to {year_used}",
    )


def vintage_url(name: str, year: int) -> str:
    """Return the download URL for dataset ``name`` and vintage ``year``."""
    if name not in COLUMNS:
        raise ValueError(f"unknown Damodaran dataset {name!r}")
    if year in MISSING_YEARS:
        raise ValueError(f"Damodaran vintage {year} is not available in the archive")
    if year in ARCHIVE_YEARS:
        yy = f"{(year - 1) % 100:02d}"  # the file carries the data year
        return ARCHIVE_URL_TEMPLATE.format(name=name, yy=yy)
    if year == CURRENT_YEAR:
        return CURRENT_URL_TEMPLATE.format(name=name)
    raise ValueError(f"unsupported Damodaran vintage year {year}")


def _find_header_row(grid: pd.DataFrame, max_rows: int = _HEADER_SCAN_ROWS) -> int | None:
    """First row whose first cell is an industry header and whose second is a firm count.

    The 2014 files say "Industry" instead of "Industry Name"; requiring "Number of firms" next
    to it keeps a stray "Industry" label in the notes above the table from matching.
    """
    if grid.empty or grid.shape[1] < 2:
        return None
    limit = min(len(grid), max_rows)
    for i in range(limit):
        if _norm(grid.iat[i, 0]) in _INDUSTRY_HEADERS and _norm(grid.iat[i, 1]).startswith(
            "number of"
        ):
            return i
    return None


def _select_sheet(name: str, sheets: dict[str, pd.DataFrame]) -> tuple[str, pd.DataFrame, int]:
    if not sheets:
        raise TrackADataError(f"Damodaran dataset {name!r} has no sheets")
    if _PREFERRED_SHEET in sheets:
        grid = sheets[_PREFERRED_SHEET]
        h = _find_header_row(grid)
        if h is not None:
            return _PREFERRED_SHEET, grid, h
    for sheet_name, grid in sheets.items():
        h = _find_header_row(grid)
        if h is not None:
            return sheet_name, grid, h
    raise TrackADataError(
        f"Damodaran dataset {name!r} has no sheet with an industry header row "
        f"in the first {_HEADER_SCAN_ROWS} rows"
    )


def _match_column(headers: list[str], accepted: tuple[str, ...]) -> int | None:
    exacts = [_norm(p) for p in accepted if not p.endswith("...")]
    prefixes = [_norm(p[:-3]) for p in accepted if p.endswith("...")]

    for j, h in enumerate(headers):
        if h and h in exacts:
            return j
    for j, h in enumerate(headers):
        if h and any(h.startswith(pref) for pref in prefixes):
            return j
    return None


def parse_dataset(name: str, sheets: dict[str, pd.DataFrame]) -> ParsedDataset:
    """Parse a multi-sheet raw Excel dict into a canonical :class:`ParsedDataset`."""
    if name not in COLUMNS:
        raise ValueError(f"unknown Damodaran dataset {name!r}")
    spec = COLUMNS[name]
    sheet_name, grid, header_row = _select_sheet(name, sheets)

    raw_header = list(grid.iloc[header_row])
    norm_headers = [_norm(v) for v in raw_header]
    seen_headers = [
        str(v).strip()
        for v in raw_header
        if v is not None and not (isinstance(v, float) and pd.isna(v)) and str(v).strip()
    ]

    positions: dict[str, int] = {}
    missing_required: list[str] = []
    missing_optional: list[str] = []
    for canonical, (accepted, required) in spec.items():
        col_idx = _match_column(norm_headers, accepted)
        if col_idx is not None:
            positions[canonical] = col_idx
        elif required:
            missing_required.append(canonical)
        else:
            missing_optional.append(canonical)

    if missing_required:
        raise TrackADataError(
            f"Damodaran dataset {name!r} is missing required columns {missing_required}; "
            f"headers seen: {seen_headers}"
        )

    rows: list[int] = []
    industries: list[str] = []
    seen_industries: set[str] = set()
    for i in range(header_row + 1, len(grid)):
        cell = grid.iat[i, 0]
        if cell is None or (isinstance(cell, float) and pd.isna(cell)):
            break
        industry = str(cell).strip()
        if not industry:
            break
        if _norm(industry).startswith("total market"):
            continue
        if industry in seen_industries:
            raise TrackADataError(
                f"Damodaran dataset {name!r} contains duplicate industry {industry!r}"
            )
        seen_industries.add(industry)
        rows.append(i)
        industries.append(industry)

    data = {
        canonical: [_to_float(grid.iat[i, j]) for i in rows] for canonical, j in positions.items()
    }
    frame = pd.DataFrame(data, index=pd.Index(industries, name="industry"))
    return ParsedDataset(
        name=name,
        sheet=sheet_name,
        header_row=header_row,
        frame=frame,
        missing_optional=tuple(missing_optional),
    )


def normalise_industry(name: str) -> str:
    """Normalise an industry name into a cross-vintage join key."""
    text = name.lower().strip()
    text = re.sub(r"\(\s*general\s*\)\s*$", "", text)
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9/\-\s]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _detect_engine(body: bytes, name: str, year: int) -> str:
    if body.startswith(_XLS_MAGIC):
        return "xlrd"
    if body.startswith(_XLSX_MAGIC):
        return "openpyxl"
    raise TrackADataError(f"unrecognised or corrupt workbook bytes for {name} ({year})")


def load_vintage(
    name: str,
    year: int,
    cache_root: Path = DEFAULT_CACHE_ROOT,
    transport: Transport | None = None,
) -> tuple[ParsedDataset, FileRecord]:
    """Download (or read from cache) and parse dataset ``name`` for ``year``."""
    url = vintage_url(name, year)
    key = url.rsplit("/", 1)[-1]
    cache = DownloadCache(Path(cache_root) / str(year), transport=transport, ttl_seconds=None)
    try:
        body = cache.fetch(key, url)
    except TrackBDataError as exc:
        raise TrackADataError(str(exc)) from exc

    engine = _detect_engine(body, name, year)
    try:
        sheets = pd.read_excel(io.BytesIO(body), header=None, sheet_name=None, engine=engine)
    except Exception as exc:  # noqa: BLE001
        raise TrackADataError(f"could not read workbook for {name} ({year}): {exc}") from exc

    parsed = parse_dataset(name, sheets)
    provenance = cache.provenance()
    record = FileRecord(**provenance[-1])
    return parsed, record


_CROSSWALK_BY_KEY = {normalise_industry(k): v[0] for k, v in INDUSTRY_CROSSWALK.items()}


def current_industry(name: str) -> str | None:
    """The current industry name for a published name: itself, its crosswalk target, or None."""
    key = normalise_industry(name)
    if key in _CROSSWALK_BY_KEY:
        return _CROSSWALK_BY_KEY[key]
    return name.strip()


def to_current_industries(table: ParsedDataset) -> tuple[pd.DataFrame, tuple[str, ...]]:
    """Re-key a vintage's table by current industry names.

    Old names are mapped through ``INDUSTRY_CROSSWALK``. Where several old industries map to one
    current industry (Electric Utility East, Central and West to Power), each column is averaged
    weighted by number of firms (equal weights when a count is missing) and ``n_firms`` is summed.
    Returns the table and the published names that have no current equivalent.
    """
    frame = table.frame.copy()
    targets = [current_industry(str(i)) for i in frame.index]
    unmapped = tuple(str(i) for i, t in zip(frame.index, targets) if t is None)
    frame["_current"] = targets
    frame = frame[frame["_current"].notna()]
    value_cols = [c for c in frame.columns if c not in ("_current", "n_firms")]
    rows = {}
    for name, group in frame.groupby("_current", sort=True):
        if "n_firms" in group and group["n_firms"].notna().all():
            weights = group["n_firms"].astype(float)
        else:
            weights = pd.Series(1.0, index=group.index)
        row = {}
        for col in value_cols:
            ok = group[col].notna()
            w = weights[ok]
            row[col] = (
                float((group.loc[ok, col] * w).sum() / w.sum()) if w.sum() > 0 else float("nan")
            )
        if "n_firms" in group:
            row["n_firms"] = float(group["n_firms"].sum(min_count=1))
        rows[name] = row
    out = pd.DataFrame.from_dict(rows, orient="index")
    out.index.name = "industry"
    return out, unmapped


def industry_value(table: ParsedDataset, industry: str, column: str) -> float | None:
    """Look up ``column`` for a CURRENT industry name in any vintage, or ``None``.

    Older vintages are translated with :func:`to_current_industries` first, so the engine can ask
    for "Power" in 2012 and get the firm-weighted value of the three electric utility groups.
    """
    if column not in table.frame.columns:
        return None
    current, _ = to_current_industries(table)
    target = normalise_industry(industry)
    for name in current.index:
        if normalise_industry(str(name)) == target:
            val = current.at[name, column]
            return None if pd.isna(val) else float(val)
    return None
