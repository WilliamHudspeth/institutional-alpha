import urllib.request

import pytest


def test_network_access_blocked_for_non_stooq_urls():
    """Verify that urlopen calls to non-Stooq URLs raise RuntimeError."""
    url = "https://example.com"
    with pytest.raises(
        RuntimeError, match=r"Network access blocked in tests: https://example\.com"
    ):
        urllib.request.urlopen(url)


def test_network_access_blocked_for_request_objects():
    """Verify that urlopen calls using Request objects raise RuntimeError."""
    req = urllib.request.Request("https://example.com/api")
    with pytest.raises(
        RuntimeError, match=r"Network access blocked in tests: https://example\.com/api"
    ):
        urllib.request.urlopen(req)


def test_stooq_url_still_allowed_and_mocked():
    """Verify that Stooq URLs continue to be handled by the mock."""
    resp = urllib.request.urlopen("https://stooq.com/q/d/l/?s=aapl.us&i=d")
    content = resp.read().decode("utf-8")
    assert "Date,Open,High,Low,Close,Volume" in content


def test_allow_network_marker_bypasses_guard(request):
    """Verify that allow_network marker bypasses the net guard."""
    request.applymarker("allow_network")
    try:
        urllib.request.urlopen("https://example.com")
    except RuntimeError as exc:
        if "Network access blocked in tests" in str(exc):
            pytest.fail(
                f"Network guard unexpectedly blocked request despite allow_network marker: {exc}"
            )
    except Exception:
        # Real network attempt error (e.g. URLError/HTTPError) is acceptable in offline environment
        pass
