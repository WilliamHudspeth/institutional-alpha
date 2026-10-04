"""Tests for iam.data.http.safe_urlopen and the autouse Stooq urlopen mock."""

from __future__ import annotations

import urllib.error
import urllib.request
from unittest.mock import MagicMock, patch

import pytest

from iam.data.http import safe_urlopen


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "FILE:///etc/passwd",
        "ftp://example.com/data.csv",
        "http://example.com/data.csv",
        "gopher://example.com/",
        "data:text/plain,hello",
        "javascript:alert(1)",
        "example.com/no-scheme",
        "",
    ],
)
def test_rejects_non_https_schemes(url):
    with patch("urllib.request.urlopen") as urlopen:
        with pytest.raises(ValueError, match="only https"):
            safe_urlopen(url)
        urlopen.assert_not_called()


def test_rejects_non_https_request_object():
    req = urllib.request.Request("file:///etc/passwd")
    with patch("urllib.request.urlopen") as urlopen:
        with pytest.raises(ValueError):
            safe_urlopen(req)
        urlopen.assert_not_called()


def test_allows_https_string_and_forwards_timeout():
    sentinel = MagicMock()
    with patch("urllib.request.urlopen", return_value=sentinel) as urlopen:
        assert safe_urlopen("https://example.com/x", timeout=3) is sentinel
    urlopen.assert_called_once_with("https://example.com/x", timeout=3)


def test_allows_https_request_object():
    req = urllib.request.Request("https://example.com/x", headers={"User-Agent": "t"})
    with patch("urllib.request.urlopen", return_value="ok") as urlopen:
        assert safe_urlopen(req, timeout=5) == "ok"
    urlopen.assert_called_once_with(req, timeout=5)


def test_stooq_autouse_mock_serves_csv(mock_stooq_global):
    """Regression: the conftest mock raised UnboundLocalError (`urllib` shadowed
    by a nested `import urllib.error`) on every call."""
    with safe_urlopen("https://stooq.com/q/d/l/?s=aapl.us&i=d") as resp:
        body = resp.read().decode("utf-8")
    assert body.startswith("Date,Open,High,Low,Close,Volume")


def test_stooq_autouse_mock_fail_all_raises_urlerror(mock_stooq_global):
    mock_stooq_global.fail_all = True
    with pytest.raises(urllib.error.URLError):
        safe_urlopen("https://stooq.com/q/d/l/?s=aapl.us&i=d")
