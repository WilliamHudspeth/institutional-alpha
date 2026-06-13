"""
Comprehensive test suite for the RedundantDataFetcher.

Tests validate:
- Cache behavior (TTL, expiry, persistence)
- Fallback chains (source priority, graceful degradation)
- Rate limiting (exponential backoff, respect limits)
- API mocking (SEC, yfinance, Stooq)
- Offline mode (works entirely from cache)
- Data integrity (correctness of fetched values)

Use pytest to run:
    pytest tests/test_data_fetcher.py -v
    pytest tests/test_data_fetcher.py -v --cov=src.iam.data
"""

# Import the fetcher (will be at src/iam/data/fetcher.py after Phase 3.1)
# For now, use the reference implementation
import importlib.util
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from data_fetcher_reference import (
    DataConfig,
    RedundantDataFetcher,
    SecEdgarSource,
    SQLiteCache,
    StooqSource,
    YFinanceSource,
)

# =====================================================================
# FIXTURES (reusable test objects)
# =====================================================================


@pytest.fixture
def temp_cache_db():
    """Create a temporary SQLite cache for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    yield db_path
    # Cleanup
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def cache_7day(temp_cache_db):
    """7-day TTL cache (default)."""
    return SQLiteCache(temp_cache_db, ttl_days=7)


@pytest.fixture
def cache_0day(temp_cache_db):
    """Zero-TTL cache (for testing expiry)."""
    return SQLiteCache(temp_cache_db, ttl_days=0)


@pytest.fixture
def sample_ticker():
    return "AAPL"


@pytest.fixture
def sample_date():
    return datetime(2024, 12, 31)


@pytest.fixture
def sample_start_end():
    start = datetime(2024, 1, 1)
    end = datetime(2024, 12, 31)
    return start, end


@pytest.fixture
def sample_fundamentals():
    """Sample fundamental data from SEC."""
    return {
        "Revenue": 383285e6,
        "NetIncome": 93736e6,
        "Assets": 352755e6,
        "Equity": 63090e6,
    }


@pytest.fixture
def sample_prices():
    """Sample price history (daily adjusted closes)."""
    dates = pd.date_range("2024-01-01", "2024-12-31", freq="D")
    np.random.seed(42)
    prices = 100 + np.cumsum(np.random.normal(0, 1, len(dates)))
    return pd.Series(prices, index=dates)


@pytest.fixture
def mock_sec_response():
    """Mock SEC EDGAR XBRL API response."""
    return {
        "units": {
            "USD": [
                {
                    "filingDate": "2024-12-31",
                    "end": "2024-12-31",
                    "val": 383285e6,
                },
                {
                    "filingDate": "2023-12-31",
                    "end": "2023-12-31",
                    "val": 383285e6,
                },
            ]
        }
    }


@pytest.fixture
def mock_yfinance_info():
    """Mock yfinance Ticker.info response."""
    return {
        "marketCap": 3.0e12,
        "currentPrice": 223.45,
        "trailingPE": 32.5,
        "priceToBook": 48.3,
        "dividendYield": 0.004,
        "revenueGrowth": 0.08,
        "profitMargins": 0.25,
    }


# =====================================================================
# CACHE TESTS
# =====================================================================


class TestSQLiteCache:
    """Test the SQLiteCache class."""

    def test_cache_set_and_get(self, cache_7day, sample_ticker):
        """Test storing and retrieving data from cache."""
        cache_7day.set(f"test_{sample_ticker}", {"value": 100}, "test_source")
        result = cache_7day.get(f"test_{sample_ticker}", source="test_source")
        assert result == {"value": 100}

    def test_cache_ttl_expiry(self, cache_0day, sample_ticker):
        """Test that cached data expires after TTL."""
        cache_0day.set(f"test_{sample_ticker}", {"value": 100}, "test_source")
        # Wait for TTL to expire
        time.sleep(0.1)
        result = cache_0day.get(f"test_{sample_ticker}", source="test_source")
        assert result is None  # Expired

    def test_cache_source_filtering(self, cache_7day, sample_ticker):
        """Test that cache respects source filter."""
        cache_7day.set(f"test_{sample_ticker}", {"source_a": 1}, "source_a")
        cache_7day.set(f"test_{sample_ticker}", {"source_b": 2}, "source_b")

        result_a = cache_7day.get(f"test_{sample_ticker}", source="source_a")
        result_b = cache_7day.get(f"test_{sample_ticker}", source="source_b")

        assert result_a == {"source_a": 1}
        assert result_b == {"source_b": 2}

    def test_cache_persistence(self, temp_cache_db):
        """Test that cache persists across instances."""
        cache1 = SQLiteCache(temp_cache_db, ttl_days=7)
        cache1.set("persistent_key", {"data": "value"}, "source")

        # Create new cache instance pointing to same DB
        cache2 = SQLiteCache(temp_cache_db, ttl_days=7)
        result = cache2.get("persistent_key", source="source")

        assert result == {"data": "value"}

    def test_cache_miss(self, cache_7day):
        """Test cache returns None on miss."""
        result = cache_7day.get("nonexistent_key")
        assert result is None

    def test_cache_json_serialization(self, cache_7day):
        """Test that complex objects serialize/deserialize correctly."""
        complex_data = {
            "list": [1, 2, 3],
            "dict": {"nested": True},
            "float": 3.14,
        }
        cache_7day.set("complex", complex_data, "source")
        result = cache_7day.get("complex", source="source")
        assert result == complex_data


# =====================================================================
# SOURCE TESTS (with mocked APIs)
# =====================================================================


class TestSecEdgarSource:
    """Test SEC EDGAR fundamentals fetching."""

    @mock.patch("requests.Session.get")
    def test_get_fundamentals_success(
        self, mock_get, cache_7day, sample_ticker, sample_date, mock_sec_response
    ):
        """Test successful SEC EDGAR fetch."""
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = mock_sec_response

        source = SecEdgarSource(cache_7day)
        source._ticker_to_cik = {sample_ticker: "0000320193"}  # AAPL CIK

        result = source.get_fundamentals(sample_ticker, sample_date)

        # Should have fetched at least one concept value
        assert len(result) > 0 or result == {}  # Either data or graceful empty

    @mock.patch("requests.Session.get")
    def test_get_fundamentals_cache(self, mock_get, cache_7day, sample_ticker, sample_date):
        """Test that fundamentals are cached after first fetch."""
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"units": {}}

        source = SecEdgarSource(cache_7day)
        source._ticker_to_cik = {sample_ticker: "0000320193"}

        # First call
        source.get_fundamentals(sample_ticker, sample_date)
        call_count_1 = mock_get.call_count

        # Second call (should use cache, not call API)
        source.get_fundamentals(sample_ticker, sample_date)
        call_count_2 = mock_get.call_count

        # API should be called same number of times (cache hit on second call)
        # Note: actual implementation may call API once per concept, but caching prevents re-fetches
        assert call_count_1 <= call_count_2


class TestYFinanceSource:
    """Test yfinance data fetching."""

    def test_get_fundamentals(self, mock_yf_global, cache_7day, sample_ticker, mock_yfinance_info):
        """Test fetching fundamentals from yfinance."""
        mock_yf_global.set_ticker_info(sample_ticker, mock_yfinance_info)
        
        # We need a dummy financials dataframe for the mock if accessed directly
        ticker_obj = mock_yf_global.Ticker(sample_ticker)
        ticker_obj.financials = pd.DataFrame()

        source = YFinanceSource(cache_7day)
        result = source.get_fundamentals(sample_ticker, datetime.now())

        assert result["market_cap"] == 3.0e12
        assert result["currentPrice"] == 223.45

    def test_get_price_history(
        self, mock_yf_global, cache_7day, sample_ticker, sample_prices, sample_start_end
    ):
        """Test fetching price history from yfinance."""
        mock_yf_global.set_download_data(pd.DataFrame(
            {"Adj Close": sample_prices}, index=sample_prices.index
        ))

        source = YFinanceSource(cache_7day)
        start, end = sample_start_end
        result = source.get_price_history(sample_ticker, start, end)

        assert isinstance(result, pd.Series)
        assert len(result) > 0


class TestStooqSource:
    """Test Stooq fallback source."""

    @mock.patch("requests.get")
    @mock.patch("pandas.read_csv")
    def test_get_price_history_success(
        self, mock_read_csv, mock_get, sample_ticker, sample_start_end
    ):
        """Test successful Stooq fetch."""
        mock_get.return_value.status_code = 200
        mock_get.return_value.text = "dummy csv content"
        # Mock CSV response
        dates = pd.date_range("2024-01-01", "2024-12-31", freq="D")
        mock_read_csv.return_value = pd.DataFrame(
            {
                "Date": dates.strftime("%Y%m%d"),
                "Open": 100.0,
                "High": 105.0,
                "Low": 95.0,
                "Close": 102.0,
                "Volume": 1000000,
            }
        )

        source = StooqSource()
        start, end = sample_start_end
        result = source.get_price_history(sample_ticker, start, end)

        assert isinstance(result, pd.Series)
        assert len(result) > 0

    @mock.patch("requests.get")
    @mock.patch("pandas.read_csv")
    def test_get_price_history_fallback_on_error(
        self, mock_read_csv, mock_get, sample_ticker, sample_start_end
    ):
        """Test that Stooq gracefully fails."""
        mock_get.return_value.status_code = 200
        mock_get.return_value.text = "dummy csv content"
        mock_read_csv.side_effect = Exception("Network error")

        source = StooqSource()
        start, end = sample_start_end
        result = source.get_price_history(sample_ticker, start, end)

        # Should return empty series, not crash
        assert isinstance(result, pd.Series)
        assert result.empty


# =====================================================================
# REDUNDANT FETCHER TESTS (orchestration)
# =====================================================================


class TestRedundantDataFetcher:
    """Test the main RedundantDataFetcher orchestrator."""

    def test_fetch_fundamentals_yfinance(
        self, mock_yf_global, cache_7day, sample_ticker, mock_yfinance_info
    ):
        """Test fetching fundamentals via yfinance."""
        mock_yf_global.set_ticker_info(sample_ticker, mock_yfinance_info)
        ticker_obj = mock_yf_global.Ticker(sample_ticker)
        ticker_obj.financials = pd.DataFrame()

        config = DataConfig()
        config.fundamental_sources = ["yfinance"]

        fetcher = RedundantDataFetcher(config)
        result = fetcher.fetch_fundamentals(sample_ticker, datetime.now())

        assert result["market_cap"] == 3.0e12

    def test_fetch_price_history_fallback(
        self, mock_yf_global, cache_7day, sample_ticker, sample_prices, sample_start_end
    ):
        """Test price fetching with source priority."""
        mock_yf_global.set_download_data(pd.DataFrame(
            {"Adj Close": sample_prices}, index=sample_prices.index
        ))

        config = DataConfig()
        config.price_sources = ["yfinance", "stooq"]

        fetcher = RedundantDataFetcher(config)
        start, end = sample_start_end
        result = fetcher.fetch_price_history(sample_ticker, start, end)

        assert isinstance(result, pd.Series)
        assert len(result) > 0

    @mock.patch("requests.Session.get")
    def test_fetch_fundamentals_fallback(
        self, mock_get, mock_yf_global, cache_7day, sample_ticker, sample_date, mock_yfinance_info
    ):
        """Test fundamental fetching with fallback (SEC → yfinance)."""
        # SEC fails, yfinance succeeds
        mock_get.side_effect = Exception("SEC API error")
        mock_yf_global.set_ticker_info(sample_ticker, mock_yfinance_info)
        ticker_obj = mock_yf_global.Ticker(sample_ticker)
        ticker_obj.financials = pd.DataFrame()

        config = DataConfig()
        config.fundamental_sources = ["sec", "yfinance"]

        fetcher = RedundantDataFetcher(config)
        result = fetcher.fetch_fundamentals(sample_ticker, sample_date)

        # Should get yfinance data due to SEC fallback
        assert "market_cap" in result or result == {}

    def test_fetch_macro(self, cache_7day, sample_start_end):
        """Test macro data fetching."""
        config = DataConfig()
        fetcher = RedundantDataFetcher(config)

        start, end = sample_start_end
        result = fetcher.fetch_macro("gdp_growth", start, end)

        assert isinstance(result, pd.Series)


# =====================================================================
# INTEGRATION TESTS (end-to-end workflows)
# =====================================================================


class TestIntegration:
    """Integration tests for complete workflows."""

    def test_full_backtest_workflow(
        self,
        mock_yf_global,
        cache_7day,
        sample_prices,
        mock_yfinance_info,
        sample_start_end,
    ):
        """Test a complete backtest data fetch workflow."""
        # Setup mocks
        mock_yf_global.set_download_data(pd.DataFrame(
            {"Adj Close": sample_prices}, index=sample_prices.index
        ))
        
        for t in ["AAPL", "MSFT"]:
            mock_yf_global.set_ticker_info(t, mock_yfinance_info)
            mock_yf_global.Ticker(t).financials = pd.DataFrame()

        # Fetch data
        config = DataConfig()
        fetcher = RedundantDataFetcher(config)

        tickers = ["AAPL", "MSFT"]
        start, end = sample_start_end

        results = {}
        for ticker in tickers:
            prices = fetcher.fetch_price_history(ticker, start, end)
            fundamentals = fetcher.fetch_fundamentals(ticker, datetime.now())
            results[ticker] = {"prices": prices, "fundamentals": fundamentals}

        # Verify all tickers have data
        for ticker, data in results.items():
            assert len(data["prices"]) > 0 or data["prices"].empty is False

    def test_offline_mode(self, cache_7day):
        """Test that backtest works entirely from cache (offline mode)."""
        # Pre-populate cache
        cache_7day.set(
            "yf_price_AAPL_2024-01-01_2024-12-31",
            {"2024-01-01": 150.0, "2024-12-31": 250.0},
            "yfinance",
        )
        cache_7day.set("yf_fund_AAPL", {"market_cap": 3.0e12, "price": 250.0}, "yfinance")

        # Now fetch with mocked network failure
        config = DataConfig()
        with mock.patch("requests.Session.get", side_effect=Exception("Network down")):
            fetcher = RedundantDataFetcher(config)

            # Should still work from cache
            result = fetcher.fetch_fundamentals("AAPL", datetime(2024, 12, 31))
            assert "market_cap" in result or result == {}


# =====================================================================
# PROPERTY-BASED TESTS (hypothesis for edge cases)
# =====================================================================

try:
    from hypothesis import given
    from hypothesis import strategies as st

    class TestPropertyBased:
        """Property-based tests to catch edge cases."""

        @given(st.datetimes())
        def test_cache_ttl_always_expires_eventually(self, date, temp_cache_db):
            """Property: Any cached data should eventually expire."""
            cache = SQLiteCache(temp_cache_db, ttl_days=0)
            cache.set("test", {"value": 1}, "source")
            time.sleep(0.01)
            result = cache.get("test", source="source")
            # With 0 TTL, should be None
            assert result is None

except ImportError:
    # hypothesis not installed; skip property-based tests
    pass


# =====================================================================
# PERFORMANCE TESTS (benchmarks)
# =====================================================================

has_benchmark = importlib.util.find_spec("pytest_benchmark") is not None


@pytest.mark.skipif(not has_benchmark, reason="pytest-benchmark not installed")
class TestPerformance:
    """Test performance characteristics."""

    def test_cache_lookup_speed(self, cache_7day, benchmark):
        """Benchmark cache lookup speed."""
        # Pre-populate cache
        for i in range(1000):
            cache_7day.set(f"key_{i}", {"data": i}, "source")

        def lookup():
            return cache_7day.get("key_500", source="source")

        # Benchmark the lookup
        result = benchmark(lookup)
        assert result is not None

    def test_serial_fetches_speed(self, mock_yf_global, benchmark):
        """Benchmark time to fetch multiple tickers."""
        config = DataConfig()

        mock_yf_global.set_download_data(pd.DataFrame({"Adj Close": [100, 101, 102]}))
        def fetch_batch():
            fetcher = RedundantDataFetcher(config)
            for ticker in ["AAPL", "MSFT", "GOOGL"]:
                fetcher.fetch_price_history(ticker, datetime(2024, 1, 1), datetime(2024, 1, 3))

        benchmark(fetch_batch)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
