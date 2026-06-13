import sys
from unittest.mock import patch
import pytest

from tests.fixtures.mock_api import MockYFinance

@pytest.fixture(autouse=True)
def mock_yf_global():
    """Globally mocks yfinance for all tests.
    
    This ensures no live network calls escape to Yahoo Finance during the test suite.
    """
    import yfinance
    yf_mock = MockYFinance()
    with patch.object(yfinance, "Ticker", yf_mock.Ticker), \
         patch.object(yfinance, "download", yf_mock.download):
        yield yf_mock
