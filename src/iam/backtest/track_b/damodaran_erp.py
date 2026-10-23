"""Damodaran implied equity risk premium: annual ``histimpl.xls`` and monthly ``ERPbymonth.xlsx``.

Two files, both free:

- ``histimpl.xls``: one row per year from 1960, each estimated at the end of that
  year (start of the next). Used as a slow valuation signal for Rung 4.
- ``ERPbymonth.xlsx``: one row per month from September 2008, estimated at the
  start of that month.

Columns are located by header text and a missing required header raises, because
Damodaran's layouts change between updates (Section 3 of the backtest strategy).
Each output row carries ``available_from``, the first date a backtest may use it:

- annual row for year Y: 15 January of Y+1 (he publishes in early January);
- monthly row dated the 1st: ``MONTHLY_PUBLICATION_LAG_DAYS`` later. The exact
  posting day is not recorded, so the lag is a conservative assumption.
"""

from __future__ import annotations

import io
import re
from datetime import datetime

import pandas as pd

from .cache import DownloadCache, TrackBDataError

HISTIMPL_URL = "https://pages.stern.nyu.edu/~adamodar/pc/datasets/histimpl.xls"
ERP_MONTHLY_URL = "https://pages.stern.nyu.edu/~adamodar/pc/implprem/ERPbymonth.xlsx"
MONTHLY_PUBLICATION_LAG_DAYS = 7

# output column -> header text in the file; True marks a required column.
ANNUAL_COLUMNS: dict[str, tuple[str, bool]] = {
    "erp_fcfe": ("Implied ERP (FCFE)", True),
    "erp_ddm": ("Implied Premium (DDM)", True),
    "tbond": ("T.Bond Rate", True),
    "tbill": ("T.Bill Rate", False),
    "earnings_yield": ("Earnings Yield", False),
    "dividend_yield": ("Dividend Yield", False),
    "sp500": ("S&P 500", False),
    "erp_fcfe_sustainable": ("Implied Premium (FCFE with sustainable Payout)", False),
}
MONTHLY_COLUMNS: dict[str, tuple[str, bool]] = {
    "erp_t12m": ("ERP (T12m)", True),
    "tbond": ("T.Bond Rate", True),
    "sp500": ("S&P 500", True),
    "erp_t12m_sustainable": ("ERP (T12 m with sustainable payout)", False),
    "erp_normalized": ("ERP (Normalized)", False),
    "erp_smoothed": ("ERP (Smoothed)", False),
    "expected_return": ("Expected Return", False),
}


def _norm(text: object) -> str:
    return re.sub(r"\s+", " ", str(text)).strip().lower()


def _find_header_row(grid: pd.DataFrame, first_header: str) -> int:
    target = _norm(first_header)
    for i in range(min(len(grid), 40)):
        if _norm(grid.iat[i, 0]) == target:
            return i
    raise TrackBDataError(f"header row starting {first_header!r} not found")


def _column_positions(header: pd.Series, spec: dict[str, tuple[str, bool]]) -> dict[str, int]:
    by_text = {_norm(v): j for j, v in enumerate(header) if pd.notna(v)}
    positions: dict[str, int] = {}
    missing = []
    for out, (text, required) in spec.items():
        j = by_text.get(_norm(text))
        if j is not None:
            positions[out] = j
        elif required:
            missing.append(text)
    if missing:
        raise TrackBDataError(f"Damodaran file is missing required headers {missing}")
    return positions


def _to_float(cell: object) -> float:
    """A numeric cell; text cells such as '4.06%' (seen in ERPbymonth.xlsx) are parsed too."""
    if isinstance(cell, str):
        text = cell.strip().replace(",", "")
        try:
            return float(text[:-1]) / 100.0 if text.endswith("%") else float(text)
        except ValueError:
            return float("nan")
    value = pd.to_numeric(cell, errors="coerce")
    return float("nan") if pd.isna(value) else float(value)


def _numeric(grid: pd.DataFrame, rows: list[int], positions: dict[str, int]) -> pd.DataFrame:
    return pd.DataFrame(
        {out: [_to_float(grid.iat[i, j]) for i in rows] for out, j in positions.items()}
    )


_TEXT_DATE_FORMATS = ("%d-%b-%y", "%d-%b-%Y", "%Y-%m-%d", "%m/%d/%Y")


def _month_start(cell: object) -> pd.Timestamp | None:
    """A date cell, or a date typed as text (one row of ERPbymonth.xlsx reads '1-Sep-24')."""
    if isinstance(cell, datetime):  # pd.Timestamp is a datetime subclass
        return pd.Timestamp(cell).normalize()
    if isinstance(cell, str):
        for fmt in _TEXT_DATE_FORMATS:
            try:
                return pd.Timestamp(datetime.strptime(cell.strip(), fmt))
            except ValueError:
                continue
    return None


def parse_histimpl(grid: pd.DataFrame) -> pd.DataFrame:
    """Annual table from the raw cell grid of ``histimpl.xls`` (read with ``header=None``)."""
    h = _find_header_row(grid, "Year")
    positions = _column_positions(grid.iloc[h], ANNUAL_COLUMNS)
    rows, years = [], []
    for i in range(h + 1, len(grid)):
        cell = grid.iat[i, 0]
        try:
            year = int(cell)
        except (TypeError, ValueError):
            break  # the summary block below the table starts with text or blanks
        if year != cell or not 1900 <= year <= 2100:
            break
        rows.append(i)
        years.append(year)
    if not rows:
        raise TrackBDataError("histimpl.xls has no annual rows")
    out = _numeric(grid, rows, positions)
    out.index = pd.Index(years, name="year")
    if not out.index.is_monotonic_increasing or out.index.has_duplicates:
        raise TrackBDataError("histimpl.xls years are not strictly increasing")
    out["available_from"] = pd.to_datetime([f"{y + 1}-01-15" for y in years])
    return out


def parse_erp_monthly(grid: pd.DataFrame) -> pd.DataFrame:
    """Monthly table from the raw cell grid of ``ERPbymonth.xlsx`` (first sheet)."""
    h = _find_header_row(grid, "Start of month")
    positions = _column_positions(grid.iloc[h], MONTHLY_COLUMNS)
    rows, dates = [], []
    for i in range(h + 1, len(grid)):
        month = _month_start(grid.iat[i, 0])
        if month is None:
            break  # the notes and averages below the table
        rows.append(i)
        dates.append(month)
    if not rows:
        raise TrackBDataError("ERPbymonth.xlsx has no monthly rows")
    out = _numeric(grid, rows, positions)
    out.index = pd.DatetimeIndex(dates, name="month_start")
    if not out.index.is_monotonic_increasing or out.index.has_duplicates:
        raise TrackBDataError("ERPbymonth.xlsx months are not strictly increasing")
    out["available_from"] = out.index + pd.Timedelta(days=MONTHLY_PUBLICATION_LAG_DAYS)
    return out


def load_histimpl(cache: DownloadCache | None = None) -> pd.DataFrame:
    """Annual implied ERP (FCFE and DDM), T-bond rate and yields, 1960 onward."""
    cache = cache or DownloadCache()
    body = cache.fetch("damodaran_histimpl.xls", HISTIMPL_URL)
    grid = pd.read_excel(io.BytesIO(body), header=None, sheet_name=0, engine="xlrd")
    return parse_histimpl(grid)


def load_erp_monthly(cache: DownloadCache | None = None) -> pd.DataFrame:
    """Monthly implied ERP from September 2008."""
    cache = cache or DownloadCache()
    body = cache.fetch("damodaran_ERPbymonth.xlsx", ERP_MONTHLY_URL)
    grid = pd.read_excel(io.BytesIO(body), header=None, sheet_name=0, engine="openpyxl")
    return parse_erp_monthly(grid)


def erp_as_of(table: pd.DataFrame, date: pd.Timestamp, column: str) -> float | None:
    """Latest non-missing ``column`` value whose ``available_from`` is on or before ``date``."""
    usable = table.loc[table["available_from"] <= pd.Timestamp(date), column].dropna()
    return None if usable.empty else float(usable.iloc[-1])
