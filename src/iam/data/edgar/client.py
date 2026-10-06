"""SEC EDGAR HTTP client: declared User-Agent, rate limit, retry, disk cache.

The transport is injectable so tests replay recorded fixtures and never touch the
network. ``requests`` is already a project dependency (see ``iam.data.fetcher``).
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)

# SEC's published fair-access limit is 10 requests/second; stay at half of it so a
# burst of retries cannot cross the line.
MAX_REQUESTS_PER_SECOND = 5
# Retry only statuses the SEC documents as transient (throttling and server errors).
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
MAX_ATTEMPTS = 4
# Exponential backoff: BACKOFF_BASE_SECONDS * 2**attempt (0.5s, 1s, 2s).
BACKOFF_BASE_SECONDS = 0.5
REQUEST_TIMEOUT_SECONDS = 30
DEFAULT_CACHE_DIR = ".cache/edgar"
# SEC requires a descriptive User-Agent with contact info; the same placeholder the
# credentials module documents. The owner sets the real contact via SEC_USER_AGENT.
DEFAULT_USER_AGENT = "institutional-alpha research contact@example.com"
# Submissions / companyfacts / ticker map change as filings land; filing archives never do.
MUTABLE_TTL_SECONDS = 24 * 3600

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_DATA_HOST = "https://data.sec.gov"

# transport(url, headers) -> (status_code, body_bytes)
Transport = Callable[[str, dict[str, str]], tuple[int, bytes]]


class EdgarError(RuntimeError):
    """EDGAR could not supply the requested document."""


def companyfacts_url(cik: int) -> str:
    return f"{_DATA_HOST}/api/xbrl/companyfacts/CIK{int(cik):010d}.json"


def submissions_url(cik: int) -> str:
    return f"{_DATA_HOST}/submissions/CIK{int(cik):010d}.json"


def resolve_user_agent(explicit: str | None = None) -> str:
    """Explicit > configured ``sec_edgar`` contact > the documented placeholder."""
    if explicit:
        return explicit
    from iam.config.credentials import get_key

    return get_key("sec_edgar") or DEFAULT_USER_AGENT


def _requests_transport(session: requests.Session) -> Transport:
    def send(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
        resp = session.get(url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
        return resp.status_code, resp.content

    return send


class EdgarClient:
    """Cached, rate-limited, retrying GET client for SEC EDGAR."""

    def __init__(
        self,
        cache_dir: str | Path = DEFAULT_CACHE_DIR,
        *,
        user_agent: str | None = None,
        transport: Transport | None = None,
        max_requests_per_second: float = MAX_REQUESTS_PER_SECOND,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.user_agent = resolve_user_agent(user_agent)
        self._transport = transport or _requests_transport(requests.Session())
        self._min_interval = 1.0 / max_requests_per_second
        self._sleep = sleep
        self._clock = clock
        self._wall_clock = wall_clock
        self._last_request: float | None = None
        self.network_calls = 0

    # -- cache ---------------------------------------------------------
    def _cache_path(self, url: str) -> Path:
        return self.cache_dir / (hashlib.sha256(url.encode("utf-8")).hexdigest() + ".bin")

    def _read_cache(self, url: str, ttl_seconds: float | None) -> bytes | None:
        path = self._cache_path(url)
        try:
            if not path.is_file():
                return None
            if ttl_seconds is not None and self._wall_clock() - path.stat().st_mtime > ttl_seconds:
                return None
            return path.read_bytes()
        except OSError:
            return None

    def _write_cache(self, url: str, body: bytes) -> None:
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self._cache_path(url).write_bytes(body)
        except OSError as exc:  # a cache write failure must not lose the fetched data
            logger.warning("EDGAR cache write failed for %s: %s", url, exc)

    # -- network -------------------------------------------------------
    def _throttle(self) -> None:
        if self._last_request is not None:
            wait = self._min_interval - (self._clock() - self._last_request)
            if wait > 0:
                self._sleep(wait)
        self._last_request = self._clock()

    def _fetch(self, url: str) -> bytes:
        headers = {"User-Agent": self.user_agent, "Accept-Encoding": "gzip, deflate"}
        last_status: int | None = None
        for attempt in range(MAX_ATTEMPTS):
            self._throttle()
            self.network_calls += 1
            status, body = self._transport(url, headers)
            if status == 200:
                return body
            last_status = status
            if status not in RETRY_STATUSES:
                break
            self._sleep(BACKOFF_BASE_SECONDS * 2**attempt)
        raise EdgarError(f"EDGAR request failed (HTTP {last_status}) for {url}")

    def get_bytes(self, url: str, *, ttl_seconds: float | None = None) -> bytes:
        """GET ``url``. ``ttl_seconds=None`` means cached forever (immutable archives)."""
        cached = self._read_cache(url, ttl_seconds)
        if cached is not None:
            return cached
        body = self._fetch(url)
        self._write_cache(url, body)
        return body

    def get_json(self, url: str, *, ttl_seconds: float | None = MUTABLE_TTL_SECONDS) -> Any:
        """GET and decode JSON; mutable endpoints default to a one-day TTL."""
        return json.loads(self.get_bytes(url, ttl_seconds=ttl_seconds))

    # -- endpoints -----------------------------------------------------
    def company_tickers(self) -> Any:
        return self.get_json(TICKERS_URL)

    def companyfacts(self, cik: int) -> Any:
        return self.get_json(companyfacts_url(cik))

    def submissions(self, cik: int) -> Any:
        return self.get_json(submissions_url(cik))
