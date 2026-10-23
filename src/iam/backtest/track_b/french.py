"""Kenneth French Data Library loader (market, Fama-French factors, momentum, industries).

Each library file is a zipped CSV holding several tables one after another: a few
lines of description, a header row starting with a comma, then rows keyed by
``YYYYMM`` (monthly), ``YYYY`` (annual) or ``YYYYMMDD`` (daily). Returns are in
percent and missing values are written as -99.99 or -999.

:func:`parse_french_csv` splits a file into :class:`FrenchTable` objects, telling
the frequency from the date width rather than from the free-text titles, which
differ between files. The convenience loaders return decimal returns indexed by
period-end dates.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .cache import DownloadCache, TrackBDataError

FRENCH_BASE_URL = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
FF5_DATASET = "F-F_Research_Data_5_Factors_2x3"
FF3_DATASET = "F-F_Research_Data_Factors"
MOMENTUM_DATASET = "F-F_Momentum_Factor"
INDUSTRY49_DATASET = "49_Industry_Portfolios"

MISSING_VALUES = (-99.99, -999.0)
_FREQ_BY_WIDTH = {4: "annual", 6: "monthly", 8: "daily"}


@dataclass
class FrenchTable:
    title: str  # the description line directly above the header, or ""
    frequency: str  # "monthly", "annual" or "daily"
    data: pd.DataFrame  # raw values as published (percent), indexed by period end


def french_url(dataset: str) -> str:
    return f"{FRENCH_BASE_URL}{dataset}_CSV.zip"


def _period_end(keys: list[str], frequency: str) -> pd.DatetimeIndex:
    if frequency == "monthly":
        return pd.DatetimeIndex(pd.to_datetime(keys, format="%Y%m") + pd.offsets.MonthEnd(0))
    if frequency == "annual":
        return pd.DatetimeIndex(pd.to_datetime(keys, format="%Y") + pd.offsets.YearEnd(0))
    return pd.DatetimeIndex(pd.to_datetime(keys, format="%Y%m%d"))


def _is_data_row(line: str) -> bool:
    head = line.split(",", 1)[0].strip()
    return head.isdigit() and len(head) in _FREQ_BY_WIDTH


def parse_french_csv(text: str) -> list[FrenchTable]:
    """Split one French library CSV into its tables, in file order."""
    lines = text.splitlines()
    tables: list[FrenchTable] = []
    i = 0
    while i < len(lines):
        if not lines[i].startswith(","):
            i += 1
            continue
        columns = [c.strip() for c in lines[i].split(",")[1:]]
        title = lines[i - 1].strip() if i > 0 else ""
        if title and _is_data_row(lines[i - 1]):
            title = ""
        i += 1
        keys: list[str] = []
        rows: list[list[float]] = []
        while i < len(lines) and _is_data_row(lines[i]):
            parts = [p.strip() for p in lines[i].split(",")]
            keys.append(parts[0])
            rows.append([float(p) if p else np.nan for p in parts[1 : len(columns) + 1]])
            i += 1
        if not keys:
            continue
        widths = {len(k) for k in keys}
        if len(widths) != 1:
            raise TrackBDataError(f"table {title!r} mixes date formats {sorted(widths)}")
        frequency = _FREQ_BY_WIDTH[widths.pop()]
        frame = pd.DataFrame(rows, columns=columns, index=_period_end(keys, frequency))
        frame.index.name = "date"
        frame = frame.replace(list(MISSING_VALUES), np.nan)
        tables.append(FrenchTable(title=title, frequency=frequency, data=frame))
    if not tables:
        raise TrackBDataError("no tables found in French library file")
    return tables


def read_french_zip(body: bytes) -> list[FrenchTable]:
    with zipfile.ZipFile(io.BytesIO(body)) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if len(names) != 1:
            raise TrackBDataError(f"expected one CSV in the French zip, found {names}")
        text = zf.read(names[0]).decode("latin-1")
    return parse_french_csv(text)


def load_french_tables(dataset: str, cache: DownloadCache | None = None) -> list[FrenchTable]:
    cache = cache or DownloadCache()
    return read_french_zip(cache.fetch(f"french_{dataset}.zip", french_url(dataset)))


def select_table(
    tables: list[FrenchTable], frequency: str = "monthly", title_contains: str | None = None
) -> FrenchTable:
    """The first table of ``frequency`` whose title contains ``title_contains`` (case-insensitive)."""
    for t in tables:
        if t.frequency != frequency:
            continue
        if title_contains is None or title_contains.lower() in t.title.lower():
            return t
    raise TrackBDataError(
        f"no {frequency} table titled like {title_contains!r}; "
        f"have {[(t.frequency, t.title) for t in tables]}"
    )


def _as_decimal(table: FrenchTable, expected: list[str] | None = None) -> pd.DataFrame:
    frame = table.data
    if expected is not None:
        missing = [c for c in expected if c not in frame.columns]
        if missing:
            raise TrackBDataError(f"French table {table.title!r} lacks columns {missing}")
        frame = frame[expected]
    return frame / 100.0


def french_ff5_monthly(cache: DownloadCache | None = None) -> pd.DataFrame:
    """Monthly Mkt-RF, SMB, HML, RMW, CMA and RF as decimals, from July 1963."""
    tables = load_french_tables(FF5_DATASET, cache)
    cols = ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "RF"]
    return _as_decimal(select_table(tables, "monthly"), cols)


def french_momentum_monthly(cache: DownloadCache | None = None) -> pd.Series:
    """Monthly UMD momentum factor (``Mom``) as decimals."""
    tables = load_french_tables(MOMENTUM_DATASET, cache)
    return _as_decimal(select_table(tables, "monthly"), ["Mom"])["Mom"]


def french_industry49_monthly(
    cache: DownloadCache | None = None, weighting: str = "value"
) -> pd.DataFrame:
    """Monthly returns of the 49 industry portfolios, value or equal weighted, as decimals."""
    if weighting not in ("value", "equal"):
        raise ValueError("weighting must be 'value' or 'equal'")
    tables = load_french_tables(INDUSTRY49_DATASET, cache)
    title = f"Average {weighting.capitalize()} Weighted Returns -- Monthly"
    return _as_decimal(select_table(tables, "monthly", title))
