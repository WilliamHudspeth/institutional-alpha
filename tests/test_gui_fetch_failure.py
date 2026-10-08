"""A failed data fetch must stop the GUI valuation, never value an empty Security.

Regression: "The GUI values an empty Security when a fetch fails."
"""

from __future__ import annotations

from unittest.mock import patch

from iam.ui import gui


def test_failed_fetch_returns_no_security_and_a_reason():
    with patch(
        "iam.data.providers.yfinance_adapter.fetch_security",
        side_effect=RuntimeError("HTTP 404"),
    ):
        security, error = gui._load_security("ZZZZ")
    assert security is None
    assert "ZZZZ" in error and "HTTP 404" in error


def test_successful_fetch_is_passed_through():
    sentinel = object()
    with patch("iam.data.providers.yfinance_adapter.fetch_security", return_value=sentinel):
        security, error = gui._load_security("BLK")
    assert security is sentinel and error is None
