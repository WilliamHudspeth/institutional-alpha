from unittest.mock import patch

import pytest

from tests.fixtures.mock_api import MockStooq, MockYFinance


@pytest.fixture(autouse=True)
def mock_yf_global():
    """Globally mocks yfinance for all tests.

    This ensures no live network calls escape to Yahoo Finance during the test suite.
    """
    import yfinance

    yf_mock = MockYFinance()
    with (
        patch.object(yfinance, "Ticker", yf_mock.Ticker),
        patch.object(yfinance, "download", yf_mock.download),
    ):
        yield yf_mock


@pytest.fixture(autouse=True)
def mock_stooq_global():
    """Globally mocks Stooq for all tests.

    This ensures no live network calls escape to Stooq during the test suite.
    """
    import urllib.request

    stooq_mock = MockStooq()

    original_urlopen = urllib.request.urlopen

    def mock_urlopen(url, *args, **kwargs):
        if isinstance(url, urllib.request.Request):
            url_str = url.full_url
        else:
            url_str = url

        if "stooq.com" in url_str:
            if stooq_mock.fail_all:
                import urllib.error

                raise urllib.error.URLError("Mock network failure")

            import numpy as np
            import pandas as pd

            dates = pd.date_range("2024-01-01", periods=100, freq="B")
            df = pd.DataFrame(
                {
                    "Date": dates.strftime("%Y-%m-%d"),
                    "Open": np.linspace(100, 150, 100),
                    "High": np.linspace(100, 150, 100) + 2,
                    "Low": np.linspace(100, 150, 100) - 2,
                    "Close": np.linspace(100, 150, 100),
                    "Volume": np.random.randint(1000000, 5000000, 100),
                }
            )
            csv_str = df.to_csv(index=False)

            # mock response object
            class MockResponse:
                def read(self):
                    return csv_str.encode("utf-8")

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    pass

            return MockResponse()

        return original_urlopen(url, *args, **kwargs)

    with patch.object(urllib.request, "urlopen", side_effect=mock_urlopen):
        yield stooq_mock
