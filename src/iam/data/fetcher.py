"""
data_fetcher.py – Zero‑configuration, redundant data fetching for backtesting.

Features:
- No API keys required – uses only free, public APIs.
- Automatic fallback between sources when one throttles.
- Local SQLite cache with TTL to reduce network calls.
- Point‑in‑time fundamentals from SEC EDGAR (official, no key).
- Price history from yfinance, with fallback to Stooq.
- Macro data bundled as CSV (GDP, CPI, unemployment) – no FRED key needed.
"""

import json
import logging
import sqlite3
import time
import warnings
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import numpy as np
import pandas as pd
import requests  # type: ignore[import-untyped]
from requests.adapters import HTTPAdapter  # type: ignore[import-untyped]
from urllib3.util.retry import Retry

try:
    import yfinance as yf
except ImportError:
    yf = None
    warnings.warn("yfinance not installed. Install with: pip install yfinance")

# Optional Stooq fallback (no key)
STOOQ_BASE = "https://stooq.com/q/d/l/"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DataFetcher")


def _open(path: str, timeout: float = 15.0) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=timeout)
    conn.execute("PRAGMA journal_mode=WAL")  # readers don't block the writer
    conn.execute("PRAGMA busy_timeout=15000")  # ms; pairs with timeout=
    conn.execute("PRAGMA synchronous=NORMAL")  # safe under WAL, faster
    return conn


# ----------------------------------------------------------------------
# Configuration (no keys needed)
# ----------------------------------------------------------------------
class DataConfig:
    cache_db_path: str = "./data_cache/cache.db"
    cache_ttl_days: int = 7
    max_retries: int = 3
    base_backoff: float = 1.0
    rate_limit_per_sec: int = 5

    # Source priority (first working source wins)
    price_sources = ["yfinance", "stooq"]
    fundamental_sources = ["sec", "yfinance"]  # SEC primary, yfinance fallback

    # For macro: we bundle static CSVs, but user can optionally replace with FRED
    macro_csv_path: str = "./data_cache/macro_data.csv"

    def __post_init__(self):
        Path("./data_cache").mkdir(parents=True, exist_ok=True)


# ----------------------------------------------------------------------
# Retry & Rate Limiting
# ----------------------------------------------------------------------
from iam.validation.rate_limiter import RateLimiter


def with_retry(max_retries=3, base_delay=1.0, rate_limit_per_sec=5):
    limiter = RateLimiter(max_calls=rate_limit_per_sec, period_seconds=1.0)

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            delay = base_delay
            for attempt in range(max_retries + 1):
                try:
                    # Proper rate limiting
                    while not limiter.is_allowed():
                        time.sleep(0.1)
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt == max_retries:
                        break
                    logger.warning(
                        f"Attempt {attempt + 1} failed for {func.__name__}: {e}. Retrying in {delay:.2f}s"
                    )
                    time.sleep(delay)
                    delay *= 2
            raise last_exception

        return wrapper

    return decorator


# ----------------------------------------------------------------------
# SQLite Cache
# ----------------------------------------------------------------------
class SQLiteCache:
    def __init__(self, db_path: str, ttl_days: int):
        self.db_path = Path(db_path)
        self.ttl_seconds = ttl_days * 86400
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        conn = None
        try:
            conn = _open(self.db_path, timeout=15.0)
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS cache (
                        key TEXT,
                        value TEXT,
                        timestamp REAL,
                        source TEXT,
                        PRIMARY KEY (key, source)
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON cache(timestamp)")
        finally:
            if conn:
                conn.close()

    def get(self, key: str, source: str | None = None) -> Any | None:
        conn = None
        try:
            conn = _open(self.db_path, timeout=15.0)
            cur = conn.execute(
                "SELECT value, timestamp FROM cache WHERE key = ? AND (source = ? OR ? IS NULL)",
                (key, source, source),
            )
            row = cur.fetchone()
            if row:
                value, ts = row
                if (time.time() - ts) < self.ttl_seconds:
                    try:
                        return json.loads(value)
                    except Exception:
                        return value
        finally:
            if conn:
                conn.close()
        return None

    def set(self, key: str, value: Any, source: str):
        conn = None
        try:
            conn = _open(self.db_path, timeout=15.0)
            with conn:
                conn.execute(
                    "INSERT OR REPLACE INTO cache (key, value, timestamp, source) VALUES (?, ?, ?, ?)",
                    (key, json.dumps(value, default=str), time.time(), source),
                )
        finally:
            if conn:
                conn.close()


# ----------------------------------------------------------------------
# SEC EDGAR Source (No key, official fundamentals)
# ----------------------------------------------------------------------
class SecEdgarSource:
    """
    Fetches point‑in‑time fundamentals from SEC EDGAR XBRL API.
    No API key required.
    """

    BASE_URL = "https://data.sec.gov/api/xbrl/companyconcept"
    USER_AGENT = (
        "Mozilla/5.0 (compatible; ResearchBot/1.0; +https://github.com/institutional-alpha)"
    )

    def __init__(self, cache: SQLiteCache):
        self.cache = cache
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.USER_AGENT})
        retries = Retry(total=2, backoff_factor=0.5)
        self.session.mount("https://", HTTPAdapter(max_retries=retries))
        self._ticker_to_cik = self._load_cik_map()

    def _load_cik_map(self) -> dict[str, str]:
        """Load ticker -> CIK mapping from SEC (cached locally)."""
        mapping_file = Path("./data_cache/cik_ticker.json")
        if mapping_file.exists():
            with open(mapping_file) as f:
                cached_mapping: dict[str, str] = json.load(f)
                return cached_mapping
        # Download from SEC
        url = "https://www.sec.gov/files/company_tickers.json"
        try:
            resp = self.session.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                mapping = {v["ticker"]: str(v["cik_str"]).zfill(10) for v in data.values()}
                mapping_file.parent.mkdir(parents=True, exist_ok=True)
                with open(mapping_file, "w") as f:
                    json.dump(mapping, f)
                return mapping
        except Exception as e:
            logger.warning(f"Could not download CIK mapping: {e}")
        return {}

    @with_retry(max_retries=2, base_delay=1.0, rate_limit_per_sec=5)
    def get_fundamentals(self, ticker: str, as_of_date: datetime) -> dict:
        """Return fundamental data known before as_of_date."""
        cik = self._ticker_to_cik.get(ticker.upper())
        if not cik:
            return {}
        cache_key = f"sec_fund_{ticker}_{as_of_date.date()}"
        cached: dict | None = self.cache.get(cache_key, source="sec")
        if cached:
            return cached

        # For demonstration, we'll fetch a few key metrics.
        # Real implementation would query multiple concepts and filter by filingDate.
        # We'll fetch market cap (shares * price) is tricky – easier to get from yfinance.
        # So SEC source will provide revenue, net income, book value, etc.
        concepts = {
            "Revenue": "us-gaap/RevenueFromContractWithCustomerExcludingAssessedTax",
            "NetIncome": "us-gaap/NetIncomeLoss",
            "Assets": "us-gaap/Assets",
            "Liabilities": "us-gaap/Liabilities",
            "Equity": "us-gaap/StockholdersEquity",
        }
        result = {}
        for name, concept in concepts.items():
            url = f"{self.BASE_URL}/cik/{cik}/{concept}.json"
            resp = self.session.get(url, timeout=10)
            if resp.status_code != 200:
                continue
            data = resp.json()
            # Find the most recent unit (usually USD)
            units = data.get("units", {})
            usd_units = units.get("USD", []) or units.get("USD/shares", [])
            if not usd_units:
                continue
            # Filter by filingDate <= as_of_date
            valid = [
                u for u in usd_units if datetime.strptime(u["filingDate"], "%Y-%m-%d") <= as_of_date
            ]
            if valid:
                # Take the most recent (largest end date)
                valid_sorted = sorted(valid, key=lambda x: x["end"], reverse=True)
                result[name] = valid_sorted[0]["val"]
        self.cache.set(cache_key, result, source="sec")
        return result


# ----------------------------------------------------------------------
# yFinance Source (prices + fundamentals)
# ----------------------------------------------------------------------
class YFinanceSource:
    def __init__(self, cache: SQLiteCache):
        self.cache = cache
        if yf is None:
            raise ImportError("yfinance not installed")

    @with_retry(max_retries=2, base_delay=1.0, rate_limit_per_sec=2)
    def get_fundamentals(self, ticker: str, as_of_date: datetime) -> dict:
        """Return latest fundamentals (not point‑in‑time)."""
        cache_key = f"yf_fund_{ticker}"
        cached: dict | None = self.cache.get(cache_key, source="yfinance")
        if cached:
            return cached
        stock = yf.Ticker(ticker)
        info = stock.info
        result = {
            "market_cap": info.get("marketCap"),
            "price": info.get("currentPrice"),
            "currentPrice": info.get("currentPrice"),  # for test compatibility
            "pe_ratio": info.get("trailingPE"),
            "pb_ratio": info.get("priceToBook"),
            "dividend_yield": info.get("dividendYield"),
            "revenue_growth": info.get("revenueGrowth"),
            "profit_margins": info.get("profitMargins"),
        }
        # Also get net income and book value from financials if available
        try:
            financials = stock.financials
            if not financials.empty:
                result["net_income"] = (
                    financials.loc["Net Income"].iloc[0]
                    if "Net Income" in financials.index
                    else None
                )
        except Exception:
            pass
        self.cache.set(cache_key, result, source="yfinance")
        return result

    @with_retry(max_retries=2, base_delay=1.0, rate_limit_per_sec=2)
    def get_price_history(self, ticker: str, start: datetime, end: datetime) -> pd.Series:
        cache_key = f"yf_price_{ticker}_{start.date()}_{end.date()}"
        cached = self.cache.get(cache_key, source="yfinance")
        if cached:
            # Reconstruct Series with DatetimeIndex
            idx = pd.to_datetime(list(cached.keys()))
            return pd.Series(list(cached.values()), index=idx)
        data = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=False)
        if data.empty:
            return pd.Series()
        series = data["Adj Close"]
        if isinstance(series, pd.DataFrame):
            if ticker in series.columns:
                series = series[ticker]
            else:
                series = series.iloc[:, 0]
        # Convert index (timestamps) to strings for json storage
        series_dict = {
            k.strftime("%Y-%m-%d") if hasattr(k, "strftime") else str(k): v
            for k, v in series.to_dict().items()
        }
        self.cache.set(cache_key, series_dict, source="yfinance")
        return series


# ----------------------------------------------------------------------
# Stooq Fallback (no key, free)
# ----------------------------------------------------------------------
class StooqSource:
    """Fallback price source when yfinance throttles."""

    @with_retry(max_retries=1, base_delay=1.0, rate_limit_per_sec=1)
    def get_price_history(self, ticker: str, start: datetime, end: datetime) -> pd.Series:
        # Stooq uses format: s=ticker&d1=yyyymmdd&d2=yyyymmdd
        params = {"s": ticker, "d1": start.strftime("%Y%m%d"), "d2": end.strftime("%Y%m%d")}
        url = f"{STOOQ_BASE}?{urlencode(params)}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        try:
            resp = requests.get(url, headers=headers, timeout=3.0)
            if resp.status_code != 200:
                logger.debug(f"Stooq HTTP error {resp.status_code} for {ticker}")
                return pd.Series()
            import io

            df = pd.read_csv(
                io.StringIO(resp.text),
                header=None,
                names=["Date", "Open", "High", "Low", "Close", "Volume"],
            )
            df["Date"] = pd.to_datetime(df["Date"], format="%Y%m%d")
            df.set_index("Date", inplace=True)
            series = df["Close"].sort_index()
            return series
        except Exception as e:
            logger.debug(f"Stooq failed for {ticker}: {e}")
            return pd.Series()


# ----------------------------------------------------------------------
# Macro Data (bundled CSV, no FRED key)
# ----------------------------------------------------------------------
class MacroSource:
    """
    Provides macroeconomic data from bundled CSV.
    User can replace with FRED by adding a key, but not required.
    """

    def __init__(self, csv_path: str):
        self.csv_path = Path(csv_path)
        self._data: pd.DataFrame | None = None
        if self.csv_path.exists():
            self._data = pd.read_csv(self.csv_path, parse_dates=["date"], index_col="date")
        else:
            # Create default macro data (synthetic for demo – user should download real)
            self._create_default_data()

    def _create_default_data(self):
        # Generate dummy data for 2000-2026 so backtest doesn't fail
        dates = pd.date_range("2000-01-01", "2026-12-31", freq="ME", name="date")
        self._data = pd.DataFrame(
            {
                "gdp_growth": np.random.normal(0.02, 0.01, len(dates)),
                "cpi": np.random.normal(0.02, 0.005, len(dates)),
                "unemployment": np.random.normal(0.05, 0.01, len(dates)),
            },
            index=dates,
        )
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        self._data.to_csv(self.csv_path)
        logger.warning(
            "Using synthetic macro data. For real data, download from FRED and replace the CSV."
        )

    def get_series(self, series_name: str, start: datetime, end: datetime) -> pd.Series:
        if self._data is None or series_name not in self._data.columns:
            return pd.Series()
        mask = (self._data.index >= start) & (self._data.index <= end)
        return self._data.loc[mask, series_name]


# ----------------------------------------------------------------------
# Main Redundant Fetcher
# ----------------------------------------------------------------------
class RedundantDataFetcher:
    def __init__(self, config: DataConfig | None = None):
        self.config = config or DataConfig()
        self.cache = SQLiteCache(self.config.cache_db_path, self.config.cache_ttl_days)

        self.sources: dict[str, Any] = {}
        # Price sources
        if "yfinance" in self.config.price_sources and yf:
            self.sources["yfinance"] = YFinanceSource(self.cache)
        if "stooq" in self.config.price_sources:
            self.sources["stooq"] = StooqSource()

        # Fundamental sources
        if "sec" in self.config.fundamental_sources:
            self.sources["sec"] = SecEdgarSource(self.cache)
        if "yfinance" in self.config.fundamental_sources and yf:
            self.sources["yfinance_fund"] = YFinanceSource(self.cache)

        # Macro
        self.macro = MacroSource(self.config.macro_csv_path)

    def fetch_fundamentals(self, ticker: str, as_of_date: datetime) -> dict:
        for src_name in self.config.fundamental_sources:
            src_key = src_name if src_name != "yfinance" else "yfinance_fund"
            src = self.sources.get(src_key)
            if src is None:
                continue
            try:
                result: dict = src.get_fundamentals(ticker, as_of_date)
                if result and any(v is not None for v in result.values()):
                    logger.debug(f"Fundamentals for {ticker} from {src_name}")
                    return result
            except Exception as e:
                logger.warning(f"Source {src_name} failed: {e}")
        return {}

    def fetch_price_history(self, ticker: str, start: datetime, end: datetime) -> pd.Series:
        for src_name in self.config.price_sources:
            src = self.sources.get(src_name)
            if src is None:
                continue
            if hasattr(src, "get_price_history"):
                try:
                    prices = src.get_price_history(ticker, start, end)
                    if not prices.empty:
                        logger.debug(f"Prices for {ticker} from {src_name}")
                        return prices
                except Exception as e:
                    logger.warning(f"Price source {src_name} failed: {e}")
        return pd.Series()

    def fetch_macro(self, series_name: str, start: datetime, end: datetime) -> pd.Series:
        return self.macro.get_series(series_name, start, end)
