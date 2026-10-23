"""Download cache for Track B files, with a SHA-256 record per file.

Every loader in this package fetches through :class:`DownloadCache`. A file is
downloaded once, stored under ``cache_dir`` and described by a JSON sidecar
(URL, download time, size, SHA-256). ``provenance()`` returns those records so a
backtest manifest can show exactly which file versions a run used, and a run can
be repeated against the same bytes if the publisher later revises a file.

The transport is injectable so tests never touch the network.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from iam.data.http import safe_urlopen

logger = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = ".cache/track_b"
# Published factor files change at most monthly; re-download after 30 days.
DEFAULT_TTL_SECONDS = 30 * 24 * 3600
REQUEST_TIMEOUT_SECONDS = 120
USER_AGENT = "institutional-alpha research (Track B factor data)"

# transport(url) -> body bytes; raises on failure.
Transport = Callable[[str], bytes]


class TrackBDataError(RuntimeError):
    """A Track B file could not be downloaded or did not have the expected layout."""


@dataclass(frozen=True)
class FileRecord:
    """Provenance of one cached file."""

    key: str
    url: str
    sha256: str
    size_bytes: int
    downloaded_at: float  # Unix time


def _urllib_transport(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with safe_urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
        return bytes(resp.read())


def _safe_key(key: str) -> str:
    """File-system safe cache key (JKP names contain brackets)."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", key).strip("_")


class DownloadCache:
    """Fetch-once disk cache keyed by a caller-chosen name."""

    def __init__(
        self,
        cache_dir: str | Path = DEFAULT_CACHE_DIR,
        *,
        transport: Transport | None = None,
        ttl_seconds: float | None = DEFAULT_TTL_SECONDS,
        wall_clock: Callable[[], float] = time.time,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self._transport = transport or _urllib_transport
        self.ttl_seconds = ttl_seconds
        self._wall_clock = wall_clock
        self.network_calls = 0
        self._used: dict[str, FileRecord] = {}

    def _paths(self, key: str) -> tuple[Path, Path]:
        safe = _safe_key(key)
        return self.cache_dir / safe, self.cache_dir / (safe + ".json")

    def _read_record(self, meta_path: Path) -> FileRecord | None:
        try:
            return FileRecord(**json.loads(meta_path.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError):
            return None

    def _fresh(self, record: FileRecord) -> bool:
        if self.ttl_seconds is None:
            return True
        return self._wall_clock() - record.downloaded_at < self.ttl_seconds

    def fetch(self, key: str, url: str | Callable[[], str], *, refresh: bool = False) -> bytes:
        """Return the bytes for ``key``, downloading ``url`` if the cache is missing or stale.

        ``url`` may be a callable for sources whose download link has to be looked
        up (OSAP's Google Drive files); it is only called when a download is needed,
        and a fresh cached copy is then accepted whatever URL it came from. A cached
        file whose bytes no longer match its recorded SHA-256 is treated as missing.
        If a refresh fails and an older copy exists, the older copy is used and a
        warning is logged rather than failing the run.
        """
        lazy = callable(url)
        data_path, meta_path = self._paths(key)
        record = self._read_record(meta_path) if meta_path.exists() else None
        cached: bytes | None = None
        if record is not None and data_path.exists():
            cached = data_path.read_bytes()
            if hashlib.sha256(cached).hexdigest() != record.sha256:
                logger.warning("Track B cache for %s failed its hash check; re-downloading", key)
                cached, record = None, None
        if cached is not None and record is not None and (lazy or record.url == url):
            if not refresh and self._fresh(record):
                self._used[key] = record
                return cached

        try:
            resolved = url() if callable(url) else url
            self.network_calls += 1
            body = self._transport(resolved)
        except Exception as exc:  # noqa: BLE001 - any transport failure
            if cached is not None and record is not None:
                logger.warning("Could not refresh %s (%s); using cached copy", key, exc)
                self._used[key] = record
                return cached
            raise TrackBDataError(f"download failed for {key}: {exc}") from exc
        if not body:
            raise TrackBDataError(f"empty response for {key} from {resolved}")

        record = FileRecord(
            key=key,
            url=resolved,
            sha256=hashlib.sha256(body).hexdigest(),
            size_bytes=len(body),
            downloaded_at=self._wall_clock(),
        )
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        data_path.write_bytes(body)
        meta_path.write_text(json.dumps(asdict(record), indent=2), encoding="utf-8")
        self._used[key] = record
        return body

    def provenance(self) -> list[dict]:
        """Records of every file served in this session, for the run manifest."""
        return [asdict(r) for r in self._used.values()]
