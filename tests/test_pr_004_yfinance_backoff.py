from unittest.mock import MagicMock, patch

from iam.data.providers.yfinance_adapter import YFinanceAdapter


def test_yfinance_adapter_backoff(caplog):
    adapter = YFinanceAdapter()

    # We will mock yf.Ticker to fail twice then succeed
    mock_ticker = MagicMock()
    mock_ticker.info = {
        "currentPrice": 150.0,
        "marketCap": 1500000000,
        "totalRevenue": 100000000
    }

    call_count = 0

    def side_effect(ticker):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise Exception("Mock 429 Too Many Requests")
        return mock_ticker

    with patch("iam.data.providers.yfinance_adapter.yf.Ticker", side_effect=side_effect), \
         patch("iam.data.providers.yfinance_adapter.time.sleep") as mock_sleep, \
         patch("iam.data.providers.yfinance_adapter._get_cached_data", return_value=None):

        sec = adapter.fetch("MOCK_TICKER")

        assert call_count == 3
        assert sec.ticker == "MOCK_TICKER"
        assert sec.market.price == 150.0

        # Check that sleep was called twice with increasing delays
        assert mock_sleep.call_count == 2

        # Base delay is 2.0.
        # First retry (attempt 0): delay = 2.0 * (2**0) + jitter = 2.0 + jitter
        # Second retry (attempt 1): delay = 2.0 * (2**1) + jitter = 4.0 + jitter
        call1_delay = mock_sleep.call_args_list[0][0][0]
        call2_delay = mock_sleep.call_args_list[1][0][0]

        assert 2.0 <= call1_delay <= 3.0
        assert 4.0 <= call2_delay <= 5.0
