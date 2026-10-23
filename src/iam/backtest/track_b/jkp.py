"""Jensen, Kelly and Pedersen (JKP) Global Factor Data: long-short factor and theme returns.

Files are zipped CSVs at ``jkpfactors-data.s3.amazonaws.com/public/`` named
``[region]_[set]_[frequency]_[weighting].zip``, for example
``[usa]_[all_factors]_[monthly]_[vw_cap].zip``. They are in long format, one row
per (factor, month), with decimal returns.

Returns are already signed: a factor whose ``direction`` is -1 (the literature
finds low values outperform) is published as low-minus-high, so every factor's
long-run mean is expected to be positive. Code that compares a JKP factor with an
engine factor therefore needs the engine's own direction on the characteristic,
not just the JKP return (see ``factor_map``).

Stock-level JKP data needs WRDS and is not used.
"""

from __future__ import annotations

import io
import zipfile

import pandas as pd

from .cache import DownloadCache, TrackBDataError

JKP_BASE_URL = "https://jkpfactors-data.s3.amazonaws.com/public/"
FACTOR_SETS = ("all_factors", "all_themes")
FREQUENCIES = ("monthly", "daily")
WEIGHTINGS = ("vw_cap", "vw", "ew")

_REQUIRED = {
    "all_factors": ["name", "direction", "date", "ret", "n_stocks"],
    "all_themes": ["name", "date", "ret", "n_factors"],
}


def jkp_file_name(
    region: str = "usa",
    factor_set: str = "all_factors",
    frequency: str = "monthly",
    weighting: str = "vw_cap",
) -> str:
    if factor_set not in FACTOR_SETS:
        raise ValueError(f"factor_set must be one of {FACTOR_SETS}")
    if frequency not in FREQUENCIES:
        raise ValueError(f"frequency must be one of {FREQUENCIES}")
    if weighting not in WEIGHTINGS:
        raise ValueError(f"weighting must be one of {WEIGHTINGS}")
    return f"[{region}]_[{factor_set}]_[{frequency}]_[{weighting}]"


def jkp_url(name: str) -> str:
    return JKP_BASE_URL + name.replace("[", "%5B").replace("]", "%5D") + ".zip"


def parse_jkp_csv(raw: pd.DataFrame, factor_set: str = "all_factors") -> pd.DataFrame:
    """Validate and normalise one JKP long-format table."""
    missing = [c for c in _REQUIRED[factor_set] if c not in raw.columns]
    if missing:
        raise TrackBDataError(f"JKP {factor_set} file lacks columns {missing}")
    out = raw.copy()
    out["date"] = pd.to_datetime(out["date"])
    out["ret"] = pd.to_numeric(out["ret"], errors="coerce")
    if out.duplicated(["name", "date"]).any():
        raise TrackBDataError("JKP file has duplicate (name, date) rows")
    return out.sort_values(["name", "date"]).reset_index(drop=True)


def read_jkp_zip(body: bytes, factor_set: str = "all_factors") -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(body)) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if len(names) != 1:
            raise TrackBDataError(f"expected one CSV in the JKP zip, found {names}")
        with zf.open(names[0]) as fh:
            raw = pd.read_csv(fh)
    return parse_jkp_csv(raw, factor_set)


def load_jkp(
    region: str = "usa",
    factor_set: str = "all_factors",
    frequency: str = "monthly",
    weighting: str = "vw_cap",
    cache: DownloadCache | None = None,
) -> pd.DataFrame:
    """Long table of JKP returns. The default is US, 153 factors, monthly, capped value weighted."""
    cache = cache or DownloadCache()
    name = jkp_file_name(region, factor_set, frequency, weighting)
    return read_jkp_zip(cache.fetch(f"jkp_{name}.zip", jkp_url(name)), factor_set)


def jkp_wide(long: pd.DataFrame) -> pd.DataFrame:
    """Date x factor matrix of returns."""
    return long.pivot(index="date", columns="name", values="ret").sort_index()


def jkp_directions(long: pd.DataFrame) -> dict[str, int]:
    """Published direction (+1 or -1) of each factor in an ``all_factors`` table."""
    if "direction" not in long.columns:
        raise TrackBDataError("direction is only published for individual factors")
    d = long.groupby("name")["direction"].agg(["min", "max"])
    inconsistent = d.index[d["min"] != d["max"]].tolist()
    if inconsistent:
        raise TrackBDataError(f"JKP direction changes over time for {inconsistent}")
    return {k: int(v) for k, v in d["min"].items()}
