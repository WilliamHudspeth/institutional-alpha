"""Contract tests for the pluggable data source layer.

Every data source (YFinanceSource, StooqSource, ...) must satisfy the same
`DataSource` ABC contract defined in `iam.backtest.sources.base`. These tests
verify that:

1. Each concrete source is a true subclass of the `DataSource` ABC and
   implements every abstract method with a matching call signature.
2. Sources are interchangeable: any code written against the `DataSource`
   interface behaves identically regardless of which concrete adapter is
   plugged in (aside from source-specific data availability, e.g. Stooq
   never returns debt).

Both sources are mocked with local, per-test patches (matching the pattern
used in tests/test_backtest_sources.py) rather than the autouse
`mock_yf_global` / `mock_stooq_global` fixtures in conftest.py: those global
fixtures only stub `.info` (not `.history()`) for yfinance, and carry a
latent `UnboundLocalError` for Stooq (a nested `import urllib.error` inside
`mock_urlopen` shadows the closed-over `urllib` name), so real contract
coverage needs the same explicit per-module patching the rest of the suite
uses for these two sources.
"""

from __future__ import annotations

import inspect
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from iam.backtest.sources.base import DataSource, DataSourceError
from iam.backtest.sources.stooq_source import StooqSource
from iam.backtest.sources.yfinance_source import YFinanceSource

AS_OF = pd.Timestamp("2024-06-28")
NO_DATA_AS_OF = pd.Timestamp("1990-01-01")  # predates all mocked history

ALL_SOURCE_CLASSES = [YFinanceSource, StooqSource]


def _fake_yf_history_df(price: float = 150.0) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=5, freq="B")
    return pd.DataFrame(
        {
            "Open": [price] * 5,
            "High": [price * 1.01] * 5,
            "Low": [price * 0.99] * 5,
            "Close": [price] * 5,
            "Volume": [1_000_000] * 5,
        },
        index=idx,
    )


def _fake_yf_download_df() -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=50, freq="B")
    dates.name = "Date"
    return pd.DataFrame(
        {
            "Open": [100.0] * 50,
            "High": [101.0] * 50,
            "Low": [99.0] * 50,
            "Close": [100.0] * 50,
            "Volume": [1_000_000] * 50,
        },
        index=dates,
    )


def _fake_stooq_csv() -> str:
    dates = pd.date_range("2024-01-01", periods=100, freq="B")
    lines = ["Date,Open,High,Low,Close,Volume"]
    for i, d in enumerate(dates):
        price = 100.0 + i * 0.5
        lines.append(f"{d.date()},{price},{price + 2},{price - 2},{price},1000000")
    return "\n".join(lines) + "\n"


def _urlopen_returning(csv_text: str) -> MagicMock:
    """Build a urllib.request.urlopen mock yielding a response with given CSV bytes."""
    response = MagicMock()
    response.read.return_value = csv_text.encode("utf-8")
    urlopen = MagicMock()
    urlopen.return_value.__enter__.return_value = response
    return urlopen


def _configure_yf_mock(mock_yf: MagicMock) -> None:
    ticker_mock = MagicMock()
    ticker_mock.history.return_value = _fake_yf_history_df()
    ticker_mock.quarterly_balance_sheet = pd.DataFrame()
    mock_yf.Ticker.return_value = ticker_mock
    mock_yf.download.return_value = _fake_yf_download_df()


@pytest.fixture(params=ALL_SOURCE_CLASSES, ids=[c.__name__ for c in ALL_SOURCE_CLASSES])
def source(request):
    """Parametrized fixture yielding a working instance of each concrete DataSource."""
    cls = request.param
    if cls is YFinanceSource:
        with (
            patch("iam.backtest.sources.yfinance_source.yf") as mock_yf,
            patch("iam.backtest.sources.yfinance_source.HAS_YFINANCE", True),
        ):
            _configure_yf_mock(mock_yf)
            yield cls()
    else:
        with patch(
            "iam.backtest.sources.stooq_source.urllib.request.urlopen",
            _urlopen_returning(_fake_stooq_csv()),
        ):
            yield cls()


@pytest.fixture
def all_sources():
    """All concrete sources constructed simultaneously, for swap tests."""
    with (
        patch("iam.backtest.sources.yfinance_source.yf") as mock_yf,
        patch("iam.backtest.sources.yfinance_source.HAS_YFINANCE", True),
        patch(
            "iam.backtest.sources.stooq_source.urllib.request.urlopen",
            _urlopen_returning(_fake_stooq_csv()),
        ),
    ):
        _configure_yf_mock(mock_yf)
        yield {cls.__name__: cls() for cls in ALL_SOURCE_CLASSES}


# --------------------------------------------------------------------------- #
# Structural contract: subclassing + method signatures
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("cls", ALL_SOURCE_CLASSES, ids=[c.__name__ for c in ALL_SOURCE_CLASSES])
def test_source_is_datasource_subclass(cls):
    assert issubclass(cls, DataSource)


@pytest.mark.parametrize("cls", ALL_SOURCE_CLASSES, ids=[c.__name__ for c in ALL_SOURCE_CLASSES])
def test_source_cannot_skip_abstract_methods(cls):
    """DataSource is an ABC; every concrete subclass must implement all
    abstract methods or Python itself would refuse to instantiate it."""
    instance = cls()
    assert isinstance(instance, DataSource)


@pytest.mark.parametrize("cls", ALL_SOURCE_CLASSES, ids=[c.__name__ for c in ALL_SOURCE_CLASSES])
def test_source_has_name_attribute(cls):
    instance = cls()
    assert isinstance(instance.name, str)
    assert instance.name


@pytest.mark.parametrize(
    "method_name,expected_params",
    [
        ("fetch_price", ["ticker", "as_of"]),
        ("fetch_debt", ["ticker", "as_of"]),
        ("download_history", ["ticker", "start", "end"]),
    ],
)
@pytest.mark.parametrize("cls", ALL_SOURCE_CLASSES, ids=[c.__name__ for c in ALL_SOURCE_CLASSES])
def test_source_method_signatures_match_contract(cls, method_name, expected_params):
    """Every source must expose the same parameter names for each contract
    method, so callers can swap adapters without touching call sites."""
    method = getattr(cls, method_name)
    sig = inspect.signature(method)
    params = [p for p in sig.parameters if p != "self"]
    assert params == expected_params


def test_source_is_available_returns_bool(source):
    assert isinstance(source.is_available(), bool)


# --------------------------------------------------------------------------- #
# Behavioral contract: interchangeability
# --------------------------------------------------------------------------- #


def _run_against_interface(src: DataSource, ticker: str = "AAPL") -> float:
    """Example of code written purely against the DataSource interface.

    Any conforming adapter must be usable here without special-casing.
    """
    return src.fetch_price(ticker, AS_OF)


def test_all_sources_are_swappable_through_the_same_call_site(source):
    """The same calling code must work against every adapter."""
    price = _run_against_interface(source)
    assert isinstance(price, float)
    assert price > 0


def test_all_sources_raise_datasourceerror_when_no_data_available(source):
    """Every source must fail the same way (DataSourceError), never a raw
    exception type specific to its own transport, so composite/fallback
    logic can catch one exception class regardless of adapter."""
    with pytest.raises(DataSourceError):
        source.fetch_price("AAPL", NO_DATA_AS_OF)


def test_all_sources_return_float_for_debt(source):
    """fetch_debt must always return a float (0.0 if unsupported/unavailable,
    e.g. StooqSource has no balance-sheet data)."""
    debt = source.fetch_debt("AAPL", AS_OF)
    assert isinstance(debt, float)
    assert debt >= 0.0


def test_all_sources_download_history_returns_dataframe_or_none(source):
    result = source.download_history("AAPL", "2024-01-01", "2024-06-01")
    assert result is None or isinstance(result, pd.DataFrame)
    if result is not None:
        for col in ("Date", "Open", "High", "Low", "Close", "Volume"):
            assert col in result.columns


def test_sources_are_drop_in_replacements_in_a_generic_function(all_sources):
    """Construct a small pipeline function that only knows about the
    DataSource ABC, then run it against every concrete adapter in turn."""

    def get_latest_close(src: DataSource, ticker: str) -> float:
        return src.fetch_price(ticker, AS_OF)

    results = {name: get_latest_close(src, "AAPL") for name, src in all_sources.items()}
    assert all(isinstance(v, float) and v > 0 for v in results.values())
