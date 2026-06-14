# Zero-Configuration Data Layer — Reference Implementation

**Status**: Reference implementation (Phase 3 Integration)  
**File**: `scripts/data_fetcher_reference.py`  
**Target Integration**: Phase 3 (Operational Excellence)

---

## What This Is

A complete, production-ready data fetching framework designed to make institutional-alpha work with **zero configuration**:

```bash
# User downloads repo
git clone https://github.com/WilliamHudspeth/institutional-alpha.git
cd institutional-alpha

# One-time prefetch (optional, for offline use)
pip install yfinance pandas requests
python scripts/data_fetcher_reference.py --prefetch

# Backtest now works — no API keys, no setup
python -m iam.backtest.cli backtest
```

---

## Why This Matters

### Current State (v0.4.0)
Users hit API keys, rate limits, missing data. Installing institutional-alpha doesn't immediately "just work."

### Target State (Post-Phase 3)
Download → `--prefetch` (optional) → backtest works offline. Same tool for retail + hedge funds.

---

## Key Features

| Feature | Implementation |
|---|---|
| **No API keys** | yfinance, Stooq (free), SEC EDGAR (public API, no key) |
| **Automatic fallback** | yfinance → Stooq if throttled |
| **Point-in-time fundamentals** | SEC EDGAR XBRL API (official, 20+ years history) |
| **Offline-first** | Prefetch once, backtest works without internet |
| **Persistent cache** | SQLite with TTL (7 days default, configurable) |
| **Rate limiting** | Exponential backoff, respects API limits |
| **Macro data** | Bundled CSV (user can replace with real FRED data) |
| **Community-extensible** | Drop-in data source adapters (Bloomberg, Refinitiv connectors) |

---

## When to Integrate

### Phase 3.1: Zero-Configuration Data Layer (~Week 20-24)

1. **Refactor to production**:
   - Move `scripts/data_fetcher_reference.py` → `src/iam/data/fetcher.py`
   - Add comprehensive error handling + logging
   - Add unit tests (mock API responses)

2. **Integration points**:
   - `src/iam/backtest/snapshots.py` — use fetcher to enrich snapshots with historical fundamentals
   - `src/iam/backtest/prices.py` — use fetcher instead of direct yfinance calls
   - `src/iam/backtest/cli.py` — add `--prefetch` option to backtest command

3. **Testing**:
   - Unit tests: mock SEC EDGAR, yfinance, Stooq responses
   - Integration test: prefetch 5 tickers, verify cache, run backtest
   - Offline test: disconnect network, backtest still works with cached data

4. **Documentation**:
   - Add to README: "Quick Start" section with prefetch example
   - Add user guide: "What is the data fetcher? Why zero-config?"
   - Add API docs: `RedundantDataFetcher` class interface

5. **Release as v0.5.0 feature**

---

## Code Structure

### Classes

**`SQLiteCache`**
- Persistent local cache (TTL-based expiry)
- `get(key, source)` — retrieve cached data
- `set(key, value, source)` — store with timestamp

**`SecEdgarSource`**
- Point-in-time fundamentals from SEC EDGAR XBRL API
- `_load_cik_map()` — ticker → CIK lookup (cached)
- `get_fundamentals(ticker, as_of_date)` — revenue, net income, assets, equity

**`YFinanceSource`**
- Price history + latest fundamentals
- `get_price_history(ticker, start, end)` — daily adjusted close
- `get_fundamentals(ticker, as_of_date)` — market cap, PE, PB, yields

**`StooqSource`**
- Fallback when yfinance throttles
- `get_price_history(ticker, start, end)` — free CSV endpoint

**`MacroSource`**
- Macroeconomic time series (GDP, CPI, unemployment)
- Bundled CSV (user can replace with real FRED data)
- `get_series(series_name, start, end)`

**`RedundantDataFetcher`**
- Main entry point, orchestrates all sources
- `fetch_fundamentals(ticker, as_of_date)` → try SEC, fallback to yfinance
- `fetch_price_history(ticker, start, end)` → try yfinance, fallback to Stooq
- `fetch_macro(series_name, start, end)` → CSV series

### Helpers

**`@with_retry` decorator**
- Exponential backoff: 1s → 2s → 4s → 8s
- Rate limiting: sleep between requests
- Automatic retry on transient failures

**`prefetch_data(universe_file, start_year, end_year)`**
- Download all prices + fundamentals for universe
- Caches to SQLite
- Runs once, enables offline backtest

---

## Usage Examples

### After Integration (Post-Phase 3)

```python
# In src/iam/backtest/cli.py
from iam.data.fetcher import RedundantDataFetcher

@app.command()
def backtest(prefetch: bool = False):
    if prefetch:
        logger.info("Prefetching data...")
        fetcher = RedundantDataFetcher()
        prefetch_data(universe_file="data/universe/sp100.json")
    
    # Then run backtest — fetcher used internally
    run_backtest(...)
```

```python
# In snapshot building
from iam.data.fetcher import RedundantDataFetcher

fetcher = RedundantDataFetcher()
fundamentals = fetcher.fetch_fundamentals("AAPL", datetime(2024, 12, 31))
# Returns: {'Revenue': 1e11, 'NetIncome': 3e10, ...}

price_history = fetcher.fetch_price_history("AAPL", start, end)
# Returns: pandas.Series with daily adjusted closes
```

### For End Users

```bash
# Download repo
git clone https://github.com/WilliamHudspeth/institutional-alpha.git
cd institutional-alpha

# Install dependencies
pip install yfinance pandas requests

# Optional: Download 20 years of data for SP500 (takes ~1 hour, one-time)
python -m iam.data.fetcher --prefetch

# Run backtest — uses cached data, works offline
python -m iam.backtest.cli backtest
```

---

## Design Decisions

### Why SEC EDGAR for Fundamentals?
- **Official**: Direct from SEC filings, not a vendor estimate
- **Point-in-time**: Exactly as reported on filing date
- **No key required**: Public API, no sign-up
- **Audit trail**: Transparent, reproducible

### Why Prefetch Script?
- **Offline-first**: After prefetch, backtest works without internet
- **Reproducibility**: Exact historical data is cached and versioned
- **User control**: Users can prefetch once, never fetch again
- **Network resilience**: One-time up-front, then no rate-limit issues

### Why SQLite Cache?
- **Lightweight**: Zero external dependencies (sqlite3 is built-in)
- **TTL-based**: Old data automatically expires, fresh data fetched
- **Persistent**: Survives process restarts
- **Query**: Can inspect cache easily

### Why Redundant Sources?
- **Resilience**: If yfinance 429s, fall back to Stooq
- **Complementary**: yfinance = market cap + latest, SEC = point-in-time
- **Community-extensible**: Easy to add Bloomberg, Refinitiv adapters

---

## Testing Strategy (When Integrated)

```python
# tests/test_data_fetcher.py

def test_sqlite_cache_ttl():
    cache = SQLiteCache(":memory:", ttl_days=0)
    cache.set("key", "value", "source")
    time.sleep(1)
    assert cache.get("key") is None  # Expired

def test_redundant_fallback():
    # Mock yfinance to fail
    with mock.patch('yfinance.Ticker') as mock_yf:
        mock_yf.side_effect = Exception("Throttled")
        # Should fall back to Stooq
        fetcher = RedundantDataFetcher()
        prices = fetcher.fetch_price_history("AAPL", start, end)
        assert not prices.empty  # Got data from Stooq

def test_sec_edgar_fundamentals():
    # Mock SEC API
    with mock.patch('requests.Session.get') as mock_get:
        mock_get.return_value.json.return_value = {
            'units': {'USD': [
                {'filingDate': '2024-12-31', 'end': '2024-12-31', 'val': 1e11}
            ]}
        }
        fetcher = RedundantDataFetcher()
        fundamentals = fetcher.fetch_fundamentals("AAPL", datetime(2024, 12, 31))
        assert fundamentals['Revenue'] == 1e11

def test_prefetch_offline():
    # Prefetch to cache
    prefetch_data(universe_file="test_tickers.csv")
    
    # Disconnect network (mock)
    with mock.patch('requests.Session.get', side_effect=ConnectionError):
        # Should still work from cache
        fetcher = RedundantDataFetcher()
        prices = fetcher.fetch_price_history("AAPL", start, end)
        assert not prices.empty
```

---

## Extending: Community Data Adapters

Once integrated, community can contribute adapters:

```python
# Example: Bloomberg adapter (for institutional users)
# src/iam/data/adapters/bloomberg.py

class BloombergSource:
    """Optional Bloomberg adapter for institutional users."""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
    
    def get_price_history(self, ticker: str, start: datetime, end: datetime) -> pd.Series:
        # Call Bloomberg API
        ...
    
    def get_fundamentals(self, ticker: str, as_of_date: datetime) -> Dict:
        # Call Bloomberg API
        ...

# Register with fetcher:
# config.price_sources = ['bloomberg', 'yfinance', 'stooq']
# config.fundamental_sources = ['bloomberg', 'sec', 'yfinance']
```

---

## Migration Path

### Now (v0.4.0)
- Keep existing `src/iam/backtest/` data loading as-is
- Reference implementation lives in `scripts/data_fetcher_reference.py`

### Phase 3.1 (v0.5.0)
- Refactor to `src/iam/data/fetcher.py`
- Integrate with backtest CLI (`--prefetch` option)
- Update snapshots + prices modules to use fetcher
- Add tests + docs

### Post-Phase 3 (v1.0.0)
- Default data loading uses fetcher
- Community contributes adapters
- Institutional users plug in Bloomberg/Refinitiv keys
- Retail users enjoy zero-config prefetch workflow

---

## Questions?

See `ROADMAP.md` Phase 3.1 "Zero-Configuration Data Layer" for timeline.  
This reference implementation demonstrates the design; refactoring will happen in Phase 3.1.
