"""Tests for the Yahoo Finance data adapter and its math fallbacks."""

import sys
from unittest.mock import MagicMock, patch

import pytest

from iam.data.yahoo import fetch_security


def test_fetch_security_primary_keys_respected(mock_yf_global):
    """Ensures exact keys are used if Yahoo Finance actually provides them."""
    mock_info = {
        "currentPrice": 150.0,
        "marketCap": 15000.0,
        "sharesOutstanding": 100.0,
        "netIncomeToCommon": 1000.0,
        "ebitda": 2000.0,
        "freeCashflow": 1200.0,
    }
    mock_yf_global.set_ticker_info("MOCK", mock_info)

    sec = fetch_security("MOCK")

    assert sec.market.price == 150.0
    assert sec.fundamentals.shares_outstanding == 100.0
    assert sec.fundamentals.net_income_ttm == 1000.0
    assert sec.fundamentals.ebitda_ttm == 2000.0
    assert sec.fundamentals.fcf_ttm == 1200.0


def test_fetch_security_math_fallbacks(mock_yf_global):
    """Ensures missing keys are mathematically derived from available metrics."""
    mock_info = {
        "currentPrice": 150.0,
        "marketCap": 15000.0,
        "trailingPE": 15.0,
        "enterpriseValue": 20000.0,
        "enterpriseToEbitda": 10.0,
        "operatingCashflow": 1500.0,
        # Purposely missing: shares, net income, ebitda, and fcf
    }
    mock_yf_global.set_ticker_info("MOCK", mock_info)

    sec = fetch_security("MOCK")

    assert sec.fundamentals.shares_outstanding == 100.0  # 15000 / 150
    assert sec.fundamentals.net_income_ttm == 1000.0  # 15000 / 15
    assert sec.fundamentals.ebitda_ttm == 2000.0  # 20000 / 10
    assert sec.fundamentals.fcf_ttm == 1200.0  # 1500 * 0.8


def test_fetch_security_ultimate_fcf_fallback(mock_yf_global):
    """Ensures FCF falls all the way back to Net Income if OCF is also missing."""
    mock_info = {"currentPrice": 10.0, "marketCap": 1000.0, "trailingPE": 10.0}
    mock_yf_global.set_ticker_info("MOCK", mock_info)

    sec = fetch_security("MOCK")
    assert sec.fundamentals.fcf_ttm == 100.0  # Falls back to 1000 / 10


def test_fetch_security_mostly_empty_info(mock_yf_global):
    """Ensures that missing fundamental data gracefully results in None fields, not crashes."""
    mock_info = {"currentPrice": 10.0}
    mock_yf_global.set_ticker_info("MOCK", mock_info)

    sec = fetch_security("MOCK")

    assert sec.market.price == 10.0
    assert sec.market.market_cap is None
    assert sec.fundamentals.fcf_ttm is None
    assert sec.fundamentals.shares_outstanding is None


def test_fetch_security_completely_missing_data_raises_error(mock_yf_global):
    """Ensures a RuntimeError is raised if even the price is missing."""
    mock_yf_global.set_ticker_info("MOCK", {})

    with pytest.raises(RuntimeError, match="returned no price data"):
        fetch_security("MOCK")
