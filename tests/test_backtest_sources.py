"""Tests for the pluggable data source layer.

Covers:
- Base DataSource contract (abstract methods)
- YFinanceSource (with mocked yfinance)
- StooqSource (with mocked HTTP)
- CompositeDataSource (fallback chain logic)
- default_chain() builder
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from iam.backtest.sources import (
    CompositeDataSource,
    DataSource,
    DataSourceError,
    StooqSource,
    YFinanceSource,
    default_chain,
)

# -----------------------------------------------------------------------------
# Test fixtures
# -----------------------------------------------------------------------------


class _StubSource(DataSource):
    """Test double for DataSource contract."""

    def __init__(
        self,
        name: str = "stub",
        price: float | None = 100.0,
        debt: float = 1_000_000.0,
        available: bool = True,
        history: pd.DataFrame | None = None,
        raise_on_price: bool = False,
    ):
        self.name = name
        self._price = price
        self._debt = debt
        self._available = available
        self._history = history
        self._raise = raise_on_price
        self.price_calls = 0
        self.debt_calls = 0

    def is_available(self) -> bool:
        return self._available

    def fetch_price(self, ticker, as_of):
        self.price_calls += 1
        if self._raise or self._price is None:
            raise DataSourceError(self.name, ticker, "stub failure")
        return self._price

    def fetch_debt(self, ticker, as_of):
        self.debt_calls += 1
        return self._debt

    def download_history(self, ticker, start, end):
        return self._history


def _fake_history_df(price: float = 100.0) -> pd.DataFrame:
    """Build a yfinance-style history DataFrame indexed by Date."""
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


# -----------------------------------------------------------------------------
# DataSourceError
# -----------------------------------------------------------------------------


class TestDataSourceError:
    def test_error_carries_source_ticker_reason(self):
        err = DataSourceError("yfinance", "AAPL", "rate limited")
        assert err.source == "yfinance"
        assert err.ticker == "AAPL"
        assert err.reason == "rate limited"
        assert "yfinance" in str(err)
        assert "AAPL" in str(err)
        assert "rate limited" in str(err)


# -----------------------------------------------------------------------------
# YFinanceSource
# -----------------------------------------------------------------------------


class TestYFinanceSource:
    def test_name(self):
        assert YFinanceSource().name == "yfinance"

    @patch("iam.backtest.sources.yfinance_source.yf")
    @patch("iam.backtest.sources.yfinance_source.HAS_YFINANCE", True)
    def test_fetch_price_success(self, mock_yf):
        ticker_mock = MagicMock()
        ticker_mock.history.return_value = _fake_history_df(price=150.0)
        mock_yf.Ticker.return_value = ticker_mock

        src = YFinanceSource()
        price = src.fetch_price("AAPL", pd.Timestamp("2024-01-05"))

        assert price == pytest.approx(150.0)
        mock_yf.Ticker.assert_called_once_with("AAPL")

    @patch("iam.backtest.sources.yfinance_source.yf")
    @patch("iam.backtest.sources.yfinance_source.HAS_YFINANCE", True)
    def test_fetch_price_empty_history_raises(self, mock_yf):
        ticker_mock = MagicMock()
        ticker_mock.history.return_value = pd.DataFrame()
        mock_yf.Ticker.return_value = ticker_mock

        src = YFinanceSource()
        with pytest.raises(DataSourceError) as exc_info:
            src.fetch_price("ZZZZ", pd.Timestamp("2024-01-05"))

        assert exc_info.value.source == "yfinance"
        assert exc_info.value.ticker == "ZZZZ"

    @patch("iam.backtest.sources.yfinance_source.yf")
    @patch("iam.backtest.sources.yfinance_source.HAS_YFINANCE", True)
    def test_fetch_price_filters_to_dates_on_or_before_as_of(self, mock_yf):
        ticker_mock = MagicMock()
        # History has Jan 1-5; we ask for as_of=Jan 3
        df = _fake_history_df(price=100.0)
        df.loc[df.index[2], "Close"] = 999.0  # Jan 3 close
        df.loc[df.index[3], "Close"] = 111.0  # Jan 4 (after as_of)
        ticker_mock.history.return_value = df
        mock_yf.Ticker.return_value = ticker_mock

        src = YFinanceSource()
        price = src.fetch_price("AAPL", pd.Timestamp("2024-01-03"))

        # Should pick Jan 3 close, not Jan 4
        assert price == pytest.approx(999.0)

    @patch("iam.backtest.sources.yfinance_source.yf")
    @patch("iam.backtest.sources.yfinance_source.HAS_YFINANCE", True)
    def test_fetch_price_history_raises_wraps_as_datasource_error(self, mock_yf):
        ticker_mock = MagicMock()
        ticker_mock.history.side_effect = RuntimeError("network blip")
        mock_yf.Ticker.return_value = ticker_mock

        src = YFinanceSource()
        with pytest.raises(DataSourceError):
            src.fetch_price("AAPL", pd.Timestamp("2024-01-05"))

    @patch("iam.backtest.sources.yfinance_source.HAS_YFINANCE", False)
    def test_fetch_price_without_yfinance_raises(self):
        src = YFinanceSource()
        with pytest.raises(DataSourceError) as exc_info:
            src.fetch_price("AAPL", pd.Timestamp("2024-01-05"))
        assert "yfinance not installed" in exc_info.value.reason

    @patch("iam.backtest.sources.yfinance_source.HAS_YFINANCE", False)
    def test_is_available_false_when_yfinance_missing(self):
        assert YFinanceSource().is_available() is False

    @patch("iam.backtest.sources.yfinance_source.yf")
    @patch("iam.backtest.sources.yfinance_source.HAS_YFINANCE", True)
    def test_fetch_debt_returns_total_debt_column(self, mock_yf):
        ticker_mock = MagicMock()
        # Mock quarterly balance sheet
        bs = pd.DataFrame(
            {
                pd.Timestamp("2023-12-31"): {"Total Debt": 5_000_000_000.0},
                pd.Timestamp("2023-09-30"): {"Total Debt": 4_500_000_000.0},
            }
        )
        ticker_mock.quarterly_balance_sheet = bs
        mock_yf.Ticker.return_value = ticker_mock

        src = YFinanceSource()
        debt = src.fetch_debt("AAPL", pd.Timestamp("2024-01-15"))

        # Should pick the latest quarterly date on or before as_of
        assert debt == pytest.approx(5_000_000_000.0)

    @patch("iam.backtest.sources.yfinance_source.yf")
    @patch("iam.backtest.sources.yfinance_source.HAS_YFINANCE", True)
    def test_fetch_debt_returns_zero_on_empty_balance_sheet(self, mock_yf):
        ticker_mock = MagicMock()
        ticker_mock.quarterly_balance_sheet = pd.DataFrame()
        mock_yf.Ticker.return_value = ticker_mock

        src = YFinanceSource()
        assert src.fetch_debt("AAPL", pd.Timestamp("2024-01-15")) == 0.0

    @patch("iam.backtest.sources.yfinance_source.yf")
    @patch("iam.backtest.sources.yfinance_source.HAS_YFINANCE", True)
    def test_fetch_debt_returns_zero_on_exception(self, mock_yf):
        ticker_mock = MagicMock()
        # Accessing quarterly_balance_sheet raises
        type(ticker_mock).quarterly_balance_sheet = property(
            lambda _: (_ for _ in ()).throw(RuntimeError("API error"))
        )
        mock_yf.Ticker.return_value = ticker_mock

        src = YFinanceSource()
        assert src.fetch_debt("AAPL", pd.Timestamp("2024-01-15")) == 0.0

    @patch("iam.backtest.sources.yfinance_source.HAS_YFINANCE", False)
    def test_fetch_debt_returns_zero_when_yfinance_missing(self):
        src = YFinanceSource()
        assert src.fetch_debt("AAPL", pd.Timestamp("2024-01-15")) == 0.0


# -----------------------------------------------------------------------------
# StooqSource
# -----------------------------------------------------------------------------


def _urlopen_returning(csv_text: str) -> MagicMock:
    """Build a urllib.request.urlopen mock that yields a response with given CSV bytes."""
    response = MagicMock()
    response.read.return_value = csv_text.encode("utf-8")
    urlopen = MagicMock()
    urlopen.return_value.__enter__.return_value = response
    return urlopen


class TestStooqSource:
    def test_name(self):
        assert StooqSource().name == "stooq"

    def test_is_available_always_true(self):
        # Stooq has no required imports
        assert StooqSource().is_available() is True

    def test_url_format(self):
        src = StooqSource()
        url = src._url("AAPL", "2024-01-01", "2024-01-31")
        assert "aapl.us" in url
        assert "d1=20240101" in url
        assert "d2=20240131" in url
        assert "i=d" in url

    def test_fetch_debt_always_zero(self):
        # Stooq doesn't have balance sheet data
        src = StooqSource()
        assert src.fetch_debt("AAPL", pd.Timestamp("2024-01-15")) == 0.0

    def test_download_history_success(self):
        csv = (
            "Date,Open,High,Low,Close,Volume\n"
            "2024-01-01,100,102,99,101,1000000\n"
            "2024-01-02,101,103,100,102,1100000\n"
            "2024-01-03,102,104,101,103,1200000\n"
        )
        with patch(
            "iam.backtest.sources.stooq_source.urllib.request.urlopen", _urlopen_returning(csv)
        ):
            src = StooqSource()
            result = src.download_history("AAPL", "2024-01-01", "2024-01-31")

        assert result is not None
        assert len(result) == 3
        assert list(result.columns) == ["Date", "Open", "High", "Low", "Close", "Volume"]
        assert pd.api.types.is_datetime64_any_dtype(result["Date"])

    def test_download_history_returns_none_on_empty(self):
        # Header only, no data rows → pd.read_csv returns an empty DataFrame.
        with patch(
            "iam.backtest.sources.stooq_source.urllib.request.urlopen",
            _urlopen_returning("Date,Open,High,Low,Close,Volume\n"),
        ):
            src = StooqSource()
            result = src.download_history("AAPL", "2024-01-01", "2024-01-31")
        assert result is None

    def test_download_history_returns_none_on_missing_columns(self):
        # Missing some required columns
        with patch(
            "iam.backtest.sources.stooq_source.urllib.request.urlopen",
            _urlopen_returning("Date,Close\n2024-01-01,100\n"),
        ):
            src = StooqSource()
            result = src.download_history("AAPL", "2024-01-01", "2024-01-31")
        assert result is None

    def test_download_history_returns_none_on_exception(self):
        urlopen = MagicMock(side_effect=RuntimeError("network blip"))
        with patch("iam.backtest.sources.stooq_source.urllib.request.urlopen", urlopen):
            src = StooqSource()
            result = src.download_history("AAPL", "2024-01-01", "2024-01-31")
        assert result is None

    def test_fetch_price_picks_close_on_or_before_as_of(self):
        csv = (
            "Date,Open,High,Low,Close,Volume\n"
            "2024-01-01,100,102,99,100.5,1\n"
            "2024-01-02,101,103,100,101.5,1\n"
            "2024-01-03,102,104,101,102.5,1\n"
            "2024-01-04,103,105,102,103.5,1\n"
        )
        with patch(
            "iam.backtest.sources.stooq_source.urllib.request.urlopen", _urlopen_returning(csv)
        ):
            src = StooqSource()
            price = src.fetch_price("AAPL", pd.Timestamp("2024-01-02"))
        assert price == pytest.approx(101.5)

    def test_fetch_price_raises_on_no_data(self):
        with patch(
            "iam.backtest.sources.stooq_source.urllib.request.urlopen",
            _urlopen_returning("Date,Open,High,Low,Close,Volume\n"),
        ):
            src = StooqSource()
            with pytest.raises(DataSourceError):
                src.fetch_price("AAPL", pd.Timestamp("2024-01-02"))

    def test_download_history_passes_timeout_to_urlopen(self):
        urlopen = _urlopen_returning("Date,Open,High,Low,Close,Volume\n2024-01-01,1,1,1,1,1\n")
        with patch("iam.backtest.sources.stooq_source.urllib.request.urlopen", urlopen):
            StooqSource(timeout=7.5).download_history("AAPL", "2024-01-01", "2024-01-31")
        # urlopen was called once with timeout kwarg
        assert urlopen.call_args.kwargs["timeout"] == 7.5


# -----------------------------------------------------------------------------
# CompositeDataSource (fallback chain)
# -----------------------------------------------------------------------------


class TestCompositeDataSource:
    def test_requires_at_least_one_source(self):
        with pytest.raises(ValueError):
            CompositeDataSource([])

    def test_returns_first_success(self):
        primary = _StubSource(name="primary", price=100.0)
        fallback = _StubSource(name="fallback", price=200.0)

        chain = CompositeDataSource([primary, fallback])
        price = chain.fetch_price("AAPL", pd.Timestamp("2024-01-05"))

        assert price == pytest.approx(100.0)
        assert primary.price_calls == 1
        assert fallback.price_calls == 0
        assert chain.last_used == "primary"

    def test_falls_back_when_primary_raises(self):
        primary = _StubSource(name="primary", raise_on_price=True)
        fallback = _StubSource(name="fallback", price=200.0)

        chain = CompositeDataSource([primary, fallback])
        price = chain.fetch_price("AAPL", pd.Timestamp("2024-01-05"))

        assert price == pytest.approx(200.0)
        assert primary.price_calls == 1
        assert fallback.price_calls == 1
        assert chain.last_used == "fallback"

    def test_skips_unavailable_sources(self):
        unavailable = _StubSource(name="unavailable", available=False, price=100.0)
        available = _StubSource(name="available", price=200.0)

        chain = CompositeDataSource([unavailable, available])
        price = chain.fetch_price("AAPL", pd.Timestamp("2024-01-05"))

        assert price == pytest.approx(200.0)
        # Unavailable source should not be called
        assert unavailable.price_calls == 0
        assert chain.last_used == "available"

    def test_raises_when_all_sources_fail(self):
        s1 = _StubSource(name="s1", raise_on_price=True)
        s2 = _StubSource(name="s2", raise_on_price=True)

        chain = CompositeDataSource([s1, s2])
        with pytest.raises(DataSourceError) as exc_info:
            chain.fetch_price("AAPL", pd.Timestamp("2024-01-05"))

        assert "all sources failed" in exc_info.value.reason
        assert "s1" in exc_info.value.reason
        assert "s2" in exc_info.value.reason

    def test_unexpected_exception_continues_to_next_source(self):
        broken = _StubSource(name="broken")

        # Replace fetch_price to raise unexpected exception
        def boom(*args, **kwargs):
            raise KeyError("unexpected")

        broken.fetch_price = boom
        good = _StubSource(name="good", price=42.0)

        chain = CompositeDataSource([broken, good])
        price = chain.fetch_price("AAPL", pd.Timestamp("2024-01-05"))
        assert price == 42.0
        assert chain.last_used == "good"

    def test_fetch_debt_returns_first_nonzero(self):
        zero_debt = _StubSource(name="zero", debt=0.0)
        has_debt = _StubSource(name="has", debt=1_000_000.0)

        chain = CompositeDataSource([zero_debt, has_debt])
        debt = chain.fetch_debt("AAPL", pd.Timestamp("2024-01-05"))

        assert debt == pytest.approx(1_000_000.0)

    def test_fetch_debt_returns_zero_if_all_zero(self):
        s1 = _StubSource(name="s1", debt=0.0)
        s2 = _StubSource(name="s2", debt=0.0)

        chain = CompositeDataSource([s1, s2])
        assert chain.fetch_debt("AAPL", pd.Timestamp("2024-01-05")) == 0.0

    def test_fetch_debt_continues_past_exception(self):
        broken = _StubSource(name="broken", debt=0.0)
        broken.fetch_debt = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
        good = _StubSource(name="good", debt=500.0)

        chain = CompositeDataSource([broken, good])
        assert chain.fetch_debt("AAPL", pd.Timestamp("2024-01-05")) == pytest.approx(500.0)

    def test_download_history_returns_first_nonempty(self):
        empty_src = _StubSource(name="empty", history=pd.DataFrame())
        full_src = _StubSource(name="full", history=_fake_history_df())

        chain = CompositeDataSource([empty_src, full_src])
        df = chain.download_history("AAPL", "2024-01-01", "2024-01-31")

        assert df is not None
        assert not df.empty
        assert chain.last_used == "full"

    def test_download_history_returns_none_if_all_fail(self):
        s1 = _StubSource(name="s1", history=None)
        s2 = _StubSource(name="s2", history=pd.DataFrame())

        chain = CompositeDataSource([s1, s2])
        assert chain.download_history("AAPL", "2024-01-01", "2024-01-31") is None

    def test_is_available_true_if_any_source_available(self):
        a = _StubSource(name="a", available=False)
        b = _StubSource(name="b", available=True)
        assert CompositeDataSource([a, b]).is_available() is True

    def test_is_available_false_if_all_sources_unavailable(self):
        a = _StubSource(name="a", available=False)
        b = _StubSource(name="b", available=False)
        assert CompositeDataSource([a, b]).is_available() is False

    def test_repr_shows_chain(self):
        chain = CompositeDataSource([_StubSource(name="primary"), _StubSource(name="fallback")])
        assert "primary" in repr(chain)
        assert "fallback" in repr(chain)
        assert "→" in repr(chain)


# -----------------------------------------------------------------------------
# default_chain builder
# -----------------------------------------------------------------------------


class TestDefaultChain:
    def test_returns_composite_with_yfinance_then_stooq(self):
        chain = default_chain()
        assert isinstance(chain, CompositeDataSource)
        assert len(chain.sources) == 2
        assert chain.sources[0].name == "yfinance"
        assert chain.sources[1].name == "stooq"

    def test_passes_timeouts_to_sources(self):
        chain = default_chain(yfinance_timeout=5.0, stooq_timeout=20.0)
        assert chain.sources[0].timeout == 5.0
        assert chain.sources[1].timeout == 20.0
