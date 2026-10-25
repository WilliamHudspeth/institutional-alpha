"""EDGAR bulk ``companyfacts.zip``: streamed download with a SHA-256 record, and a reader.

The bulk file (about 1.4 GB) holds one ``CIK##########.json`` per filer, including filers that
later delisted, so it is the only practical source for a survivorship-inclusive universe under
SEC's request-rate limit. It is downloaded in chunks straight to disk (never held in memory)
under a dated name, and a JSON sidecar records URL, download time, size and SHA-256 in the same
format as the Track B cache, so a run can name exactly which snapshot it used.
"""

from __future__ import annotations

import hashlib
import json
import time
import zipfile
from collections.abc import Callable, Iterator
from dataclasses import asdict
from pathlib import Path
from typing import Any

import requests

from iam.backtest.track_b.cache import FileRecord
from iam.data.edgar.client import resolve_user_agent

from .errors import TrackADataError

COMPANYFACTS_ZIP_URL = "https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip"
DEFAULT_BULK_DIR = Path(".cache/edgar_bulk")
CHUNK_BYTES = 8 * 1024 * 1024
REQUEST_TIMEOUT_SECONDS = 120


def _record_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".json")


def read_record(path: Path) -> FileRecord | None:
    try:
        return FileRecord(**json.loads(_record_path(path).read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        return None


def download_companyfacts(
    bulk_dir: Path = DEFAULT_BULK_DIR,
    *,
    user_agent: str | None = None,
    session: requests.Session | None = None,
    wall_clock: Callable[[], float] = time.time,
) -> tuple[Path, FileRecord]:
    """Download today's ``companyfacts.zip`` to ``bulk_dir/companyfacts-YYYY-MM-DD.zip``.

    An existing file for the same day with a matching record is reused. The file is written to
    a ``.part`` name and renamed only after the hash is recorded, so an interrupted download never
    looks complete.
    """
    day = time.strftime("%Y-%m-%d", time.gmtime(wall_clock()))
    bulk_dir.mkdir(parents=True, exist_ok=True)
    path = bulk_dir / f"companyfacts-{day}.zip"
    record = read_record(path)
    if path.exists() and record is not None and record.size_bytes == path.stat().st_size:
        return path, record

    sess = session or requests.Session()
    headers = {"User-Agent": resolve_user_agent(user_agent)}
    part = path.with_suffix(".zip.part")
    digest = hashlib.sha256()
    size = 0
    with sess.get(
        COMPANYFACTS_ZIP_URL, headers=headers, stream=True, timeout=REQUEST_TIMEOUT_SECONDS
    ) as resp:
        if resp.status_code != 200:
            raise TrackADataError(f"companyfacts.zip download failed: HTTP {resp.status_code}")
        with part.open("wb") as fh:
            for chunk in resp.iter_content(CHUNK_BYTES):
                fh.write(chunk)
                digest.update(chunk)
                size += len(chunk)
    if size == 0:
        part.unlink(missing_ok=True)
        raise TrackADataError("companyfacts.zip download was empty")
    record = FileRecord(
        key=path.name,
        url=COMPANYFACTS_ZIP_URL,
        sha256=digest.hexdigest(),
        size_bytes=size,
        downloaded_at=wall_clock(),
    )
    _record_path(path).write_text(json.dumps(asdict(record), indent=2), encoding="utf-8")
    part.replace(path)
    return path, record


def verify(path: Path) -> FileRecord:
    """Re-hash a downloaded file against its record; raises if they differ."""
    record = read_record(path)
    if record is None:
        raise TrackADataError(f"no download record for {path}")
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK_BYTES), b""):
            digest.update(chunk)
    if digest.hexdigest() != record.sha256:
        raise TrackADataError(f"{path} does not match its recorded SHA-256")
    return record


def iter_companyfacts(path: Path, ciks: set[int] | None = None) -> Iterator[dict[str, Any]]:
    """Yield one companyfacts document per filer from the bulk zip, optionally only ``ciks``."""
    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            name = info.filename
            if not (name.startswith("CIK") and name.endswith(".json")):
                continue
            if ciks is not None and int(name[3:-5]) not in ciks:
                continue
            with zf.open(info) as fh:
                doc = json.load(fh)
            if doc:
                yield doc
