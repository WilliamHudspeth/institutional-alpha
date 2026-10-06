"""EdgarClient: User-Agent, rate limit, retry/backoff, disk cache, injectable transport."""

from __future__ import annotations

import json
import time

import pytest

from iam.data.edgar import client as ec
from iam.data.edgar.client import EdgarClient, EdgarError
from tests.edgar.helpers import FixtureTransport

URL = "https://data.sec.gov/submissions/CIK0000000001.json"


class Clock:
    """Fake monotonic clock whose ``sleep`` advances time (no real waiting)."""

    def __init__(self) -> None:
        self.now = 100.0
        self.sleeps: list[float] = []

    def sleep(self, s: float) -> None:
        self.sleeps.append(s)
        self.now += s

    def __call__(self) -> float:
        return self.now


def make(tmp_path, transport, clock=None, **kw):
    clock = clock or Clock()
    client = EdgarClient(
        tmp_path / "cache", transport=transport, sleep=clock.sleep, clock=clock, **kw
    )
    return client, clock


def test_user_agent_default_is_the_documented_placeholder(tmp_path, monkeypatch):
    monkeypatch.setenv("IAM_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    assert ec.resolve_user_agent() == "institutional-alpha research contact@example.com"


def test_user_agent_uses_configured_sec_edgar_key(tmp_path, monkeypatch):
    monkeypatch.setenv("IAM_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("SEC_USER_AGENT", "Jane Doe jane@corp.test")
    assert ec.resolve_user_agent() == "Jane Doe jane@corp.test"


def test_user_agent_header_is_sent(tmp_path):
    seen = {}

    def transport(url, headers):
        seen.update(headers)
        return 200, b"{}"

    client, _ = make(tmp_path, transport, user_agent="Test Agent t@t.test")
    client.get_json(URL)
    assert seen["User-Agent"] == "Test Agent t@t.test"


def test_rate_limit_is_below_sec_ceiling():
    assert ec.MAX_REQUESTS_PER_SECOND < 10


def test_requests_are_spaced_by_the_rate_limit(tmp_path):
    client, clock = make(tmp_path, lambda u, h: (200, b"{}"))
    for i in range(3):
        client.get_json(f"{URL}?n={i}")
    interval = 1 / ec.MAX_REQUESTS_PER_SECOND
    assert len(clock.sleeps) == 2
    assert all(s <= interval + 1e-9 for s in clock.sleeps)
    # three requests cannot fit inside fewer than two minimum intervals
    assert clock.now - 100.0 >= 2 * interval - 1e-9


@pytest.mark.parametrize("bad", [429, 500, 503])
def test_retries_transient_status_with_backoff_then_succeeds(tmp_path, bad):
    responses = [(bad, b""), (bad, b""), (200, b'{"ok": 1}')]

    def transport(url, headers):
        return responses.pop(0)

    client, clock = make(tmp_path, transport)
    assert client.get_json(URL) == {"ok": 1}
    backoffs = [s for s in clock.sleeps if s >= ec.BACKOFF_BASE_SECONDS]
    assert backoffs == [ec.BACKOFF_BASE_SECONDS, ec.BACKOFF_BASE_SECONDS * 2]
    assert client.network_calls == 3


def test_gives_up_after_max_attempts(tmp_path):
    client, _ = make(tmp_path, lambda u, h: (503, b""))
    with pytest.raises(EdgarError, match="503"):
        client.get_json(URL)
    assert client.network_calls == ec.MAX_ATTEMPTS


def test_non_retryable_status_fails_immediately(tmp_path):
    client, _ = make(tmp_path, lambda u, h: (404, b""))
    with pytest.raises(EdgarError, match="404"):
        client.get_json(URL)
    assert client.network_calls == 1


def test_cache_serves_second_call_without_transport(tmp_path):
    transport = FixtureTransport({URL: json.dumps({"a": 1}).encode()})
    client, _ = make(tmp_path, transport)
    assert client.get_json(URL) == {"a": 1}
    assert client.get_json(URL) == {"a": 1}
    assert transport.calls == [URL]
    assert any((tmp_path / "cache").iterdir())


def test_cache_persists_across_client_instances(tmp_path):
    first = FixtureTransport({URL: b'{"a": 1}'})
    make(tmp_path, first)[0].get_json(URL)
    second = FixtureTransport({})
    assert make(tmp_path, second)[0].get_json(URL) == {"a": 1}
    assert second.calls == []


def test_ttl_expiry_refetches(tmp_path):
    bodies = [b'{"v": 1}', b'{"v": 2}']
    now = [0.0]
    client = EdgarClient(
        tmp_path / "cache",
        transport=lambda u, h: (200, bodies.pop(0)),
        sleep=lambda s: None,
        wall_clock=lambda: now[0],
    )
    # the file's mtime is real time; a wall clock far in the past/future brackets the TTL
    now[0] = time.time()
    assert client.get_json(URL, ttl_seconds=60) == {"v": 1}
    assert client.get_json(URL, ttl_seconds=60) == {"v": 1}  # fresh: from cache
    now[0] += 3600
    assert client.get_json(URL, ttl_seconds=60) == {"v": 2}  # stale: refetched


def test_immutable_documents_never_expire(tmp_path):
    now = [time.time()]
    client = EdgarClient(
        tmp_path / "cache",
        transport=lambda u, h: (200, b'{"v": 1}'),
        sleep=lambda s: None,
        wall_clock=lambda: now[0],
    )
    client.get_bytes(URL, ttl_seconds=None)
    now[0] += 10**9
    assert client.get_bytes(URL, ttl_seconds=None) == b'{"v": 1}'
    assert client.network_calls == 1


def test_default_transport_cannot_reach_the_network_in_tests(tmp_path):
    client = EdgarClient(tmp_path / "cache", sleep=lambda s: None)
    with pytest.raises(AssertionError, match="live network call"):
        client.get_json(URL)


def test_endpoint_urls_are_zero_padded_to_ten_digits():
    assert ec.companyfacts_url(320193).endswith("/api/xbrl/companyfacts/CIK0000320193.json")
    assert ec.submissions_url(1364742).endswith("/submissions/CIK0001364742.json")
