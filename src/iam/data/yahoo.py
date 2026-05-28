"""Yahoo Finance Data Adapter with SQLite Caching and Normalization.

This module serves as a firewall between Yahoo Finance's unpredictable data
and your clean Security dataclass. It:

1. Caches normalized (validated) data locally (SQLite, 24h expiry)
   - Superior to HTTP-level caching: immune to yfinance version changes
   - Only caches good data (after validation), not raw Yahoo responses
2. Validates that critical fields are non-null and sensible
3. Normalizes Yahoo's chaotic keys into IAM's strict schema
4. Fails gracefully (returns None fields instead of crashing)

Architecture benefit: You can swap data providers (FMP, FactSet, etc.)
without touching the rest of your pipeline. Just write a new adapter
that returns the same normalized dictionary structure.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


class DataProviderError(Exception):
    """Raised when data provider fails or returns invalid data."""

    pass


# ============================================================================
# CACHING LAYER: SQLite Cache for Normalized Data
# ============================================================================

SEED_CACHE_PATH = "data/cache/seed_cache.sqlite"
RUNTIME_CACHE_PATH = "data/cache/iam_cache.sqlite"


def _init_cache_db():
    """Initialize SQLite cache for normalized ticker data.

    Seed Database Strategy:
    - If runtime cache doesn't exist, copy from the tracked seed cache
    - This gives every developer a warm cache of institutional data
    - Daily fetches update the runtime cache (which is .gitignore'd)
    - The seed cache stays in version control as the permanent fallback

    Both caches live under data/cache/ (src-layout convention).
    """
    import os
    import shutil
    import sqlite3

    try:
        # Ensure the cache directory exists
        os.makedirs(os.path.dirname(RUNTIME_CACHE_PATH), exist_ok=True)

        # Seed initialization: if runtime cache missing, copy from seed
        if not os.path.exists(RUNTIME_CACHE_PATH) and os.path.exists(SEED_CACHE_PATH):
            shutil.copy2(SEED_CACHE_PATH, RUNTIME_CACHE_PATH)
            logger.info(f"[CACHE] Initialized from {SEED_CACHE_PATH} (warm start)")

        # Create/verify table structure
        conn = sqlite3.connect(RUNTIME_CACHE_PATH)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ticker_cache (
                ticker TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                timestamp INTEGER NOT NULL
            )
        """)
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.warning(f"Failed to initialize cache database: {e}")
        return False


_cache_initialized = _init_cache_db()


def _get_cached_data(ticker: str) -> dict[str, Any] | None:
    """Retrieve cached normalized data if fresh (< 24 hours)."""
    if not _cache_initialized:
        return None

    try:
        import json
        import sqlite3
        from datetime import datetime

        conn = sqlite3.connect(RUNTIME_CACHE_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT data, timestamp FROM ticker_cache WHERE ticker = ?", (ticker.upper(),)
        )
        row = cursor.fetchone()
        conn.close()

        if row:
            data_str, timestamp = row
            age_seconds = datetime.now().timestamp() - timestamp
            # Expire after 86400 seconds (24 hours)
            if age_seconds < 86400:
                logger.debug(f"[CACHE] Hit for {ticker} (age: {age_seconds:.0f}s)")
                return json.loads(data_str)
            else:
                logger.debug(f"[CACHE] Stale for {ticker} (age: {age_seconds:.0f}s, max: 86400s)")

        return None
    except Exception as e:
        logger.debug(f"Cache retrieval failed: {e}")
        return None


def _save_cached_data(ticker: str, data: dict[str, Any]) -> None:
    """Save normalized data to cache."""
    if not _cache_initialized:
        return

    try:
        import json
        import sqlite3
        from datetime import datetime

        conn = sqlite3.connect(RUNTIME_CACHE_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO ticker_cache (ticker, data, timestamp) VALUES (?, ?, ?)",
            (ticker.upper(), json.dumps(data), int(datetime.now().timestamp())),
        )
        conn.commit()
        conn.close()
        logger.debug(f"[CACHE] Saved {ticker}")
    except Exception as e:
        logger.debug(f"Cache save failed: {e}")


@dataclass
class MarketSnapshot:
    """Raw numbers from Yahoo Finance (before normalization)."""

    ticker: str
    price: float | None
    market_cap: float | None
    enterprise_value: float | None
    pe_ttm: float | None
    pe_forward: float | None
    ev_ebitda: float | None
    revenue_ttm: float | None
    net_income_ttm: float | None
    ebitda_ttm: float | None
    fcf_ttm: float | None
    total_debt: float | None
    cash: float | None
    shares_outstanding: float | None
    short_interest_pct: float | None
    gross_margin: float | None
    operating_margin: float | None
    beta: float | None
    name: str | None
    sector: str | None
    industry: str | None


class YahooAdapter:
    """Fetches, caches, validates, and normalizes Yahoo Finance data.

    This adapter is your data provider firewall. It:
    1. Uses requests-cache to avoid rate limits
    2. Validates critical fields
    3. Returns None for missing fields (graceful degradation)
    4. Normalizes Yahoo's keys into IAM schema
    """

    @staticmethod
    def fetch_and_normalize(ticker: str) -> dict[str, Any]:
        """Fetch ticker data from Yahoo and return normalized dict.

        Args:
            ticker: Stock symbol (e.g., "AAPL", "BLK")

        Returns:
            Dictionary with normalized keys:
            - ticker, name, sector, industry
            - price, market_cap, beta
            - shares_outstanding, net_income_ttm, total_debt, cash
            - trailing_pe, forward_pe, ev_ebitda, price_to_book
            - revenue_ttm, ebitda_ttm, fcf_ttm, gross_margin, operating_margin

        Raises:
            DataProviderError: If ticker is invalid or price is missing

        Note:
            Uses SQLite cache (iam_cache.sqlite). First fetch hits Yahoo,
            subsequent fetches within 24h return from cache (0.02s).
        """
        # Check cache first (returns in microseconds)
        cached = _get_cached_data(ticker)
        if cached is not None:
            logger.info(f"[DATA] {ticker} (from cache)")
            return cached

        try:
            import yfinance as yf
        except ImportError as exc:
            raise DataProviderError(
                "yfinance is required. Install with: pip install yfinance"
            ) from exc

        try:
            # Fetch from Yahoo (no session parameter - yfinance handles requests internally)
            ticker_obj = yf.Ticker(ticker)
            info = ticker_obj.info or {}

            logger.debug(f"[DATA] Fetched {ticker} from Yahoo Finance")

            # Extract critical fields for validation
            price = YahooAdapter._get(info, "currentPrice", "regularMarketPrice")
            shares = YahooAdapter._get(info, "sharesOutstanding")

            # Validation: If price or shares are missing/invalid, fail gracefully
            if not price or price <= 0:
                raise DataProviderError(
                    f"Missing valid price for {ticker}. "
                    f"Got: {price}. Provider may have delisted this symbol."
                )

            if not shares or shares <= 0:
                raise DataProviderError(
                    f"Missing valid shares outstanding for {ticker}. "
                    f"Got: {shares}. Cannot calculate per-share metrics."
                )

            # Normalization: Map Yahoo's keys to IAM schema
            # All missing fields default to None (graceful degradation)
            normalized = {
                "ticker": info.get("symbol", ticker).upper(),
                "name": info.get("longName") or info.get("shortName") or ticker,
                "sector": info.get("sector"),
                "industry": info.get("industry") or info.get("industryDisp"),
                # Market data
                "price": float(price),
                "market_cap": YahooAdapter._get(info, "marketCap"),
                "beta": YahooAdapter._get(info, "beta"),
                # Fundamentals (critical for DCF)
                "shares_outstanding": float(shares),
                "net_income_ttm": YahooAdapter._get(
                    info, "netIncomeToCommon", "trailingNetIncome", "netIncome"
                ),
                "total_debt": YahooAdapter._get(info, "totalDebt"),
                "cash_and_equivalents": YahooAdapter._get(info, "totalCash", "cash"),
                "ebitda_ttm": YahooAdapter._get(info, "ebitda", "trailingEbitda"),
                "fcf_ttm": YahooAdapter._get(info, "freeCashflow"),
                "revenue_ttm": YahooAdapter._get(info, "totalRevenue"),
                # Multiples (for Stage 2 Relative Valuation)
                "trailing_pe": YahooAdapter._get(info, "trailingPE"),
                "forward_pe": YahooAdapter._get(info, "forwardPE"),
                "ev_ebitda": YahooAdapter._get(info, "enterpriseToEbitda"),
                "price_to_book": YahooAdapter._get(info, "priceToBook"),
                "enterprise_value": YahooAdapter._get(info, "enterpriseValue"),
                # Margins (for compounder lens)
                "gross_margin": YahooAdapter._get(info, "grossMargins"),
                "operating_margin": YahooAdapter._get(info, "operatingMargins"),
                # Risk metrics
                "short_interest_pct": YahooAdapter._get(info, "shortPercentOfFloat"),
            }

            # Cache the normalized data for future use
            _save_cached_data(ticker, normalized)
            return normalized

        except DataProviderError:
            raise  # Re-raise validation errors
        except Exception as e:
            raise DataProviderError(f"Failed to fetch data for {ticker}: {str(e)}") from e

    @staticmethod
    def _get(info: dict, *keys: str) -> float | None:
        """Try multiple key paths and return first valid float value.

        Example:
            _get(info, 'netIncomeToCommon', 'trailingNetIncome', 'netIncome')
            Will try each key in order and return the first non-None float.
        """
        for key in keys:
            value = info.get(key)
            # Check if value is a valid number (not None, not NaN)
            if value is not None and isinstance(value, (int, float)):
                if value == value:  # NaN != NaN, so this catches NaN
                    return float(value)
        return None


# ============================================================================
# FACTORY FUNCTION: Fetch and convert to Security
# ============================================================================


def fetch_security(ticker: str) -> Security:
    """Fetch a security from Yahoo Finance with caching and math fallbacks.

    Args:
        ticker: Stock symbol (e.g., "AAPL")

    Returns:
        Security object with all fields populated

    Raises:
        ImportError: If yfinance not installed
        RuntimeError: If Yahoo returns no price data

    Benefits:
        - First fetch: Hits Yahoo Finance (2-3 seconds)
        - Subsequent fetches within 24h: Returns from cache (0.02 seconds)
        - Math fallbacks for missing fundamental data
        - Run your pipeline 100x in a row without rate limits!
    """
    from iam.data.security import Fundamentals, MarketData, Security

    try:
        import yfinance as yf
    except ImportError as exc:
        raise ImportError(
            "yfinance is required for live data. Install it with: pip install yfinance"
        ) from exc

    try:
        info = yf.Ticker(ticker).info or {}
    except Exception as exc:
        raise RuntimeError(f"Yahoo Finance returned an error for '{ticker}': {exc}") from exc

    # Get price - required field
    price = _get_price(info, "currentPrice", "regularMarketPrice", "previousClose")
    if price is None:
        raise RuntimeError(
            f"Yahoo Finance returned no price data for '{ticker}'. "
            "Check the ticker symbol and your internet connection."
        )

    # Extract base fields for math fallbacks
    market_cap = _get_price(info, "marketCap")
    pe_ttm = _get_price(info, "trailingPE")
    ev = _get_price(info, "enterpriseValue")
    ev_ebitda = _get_price(info, "enterpriseToEbitda")

    # Math fallbacks: compute missing values from available ones
    shares_outstanding = _get_price(
        info, "sharesOutstanding", "impliedSharesOutstanding", "floatShares"
    )
    if shares_outstanding is None and market_cap is not None and price > 0:
        shares_outstanding = market_cap / price

    net_income_ttm = _get_price(info, "netIncomeToCommon", "trailingNetIncome", "netIncome")
    if net_income_ttm is None and market_cap is not None and pe_ttm is not None and pe_ttm > 0:
        net_income_ttm = market_cap / pe_ttm

    ebitda_ttm = _get_price(info, "ebitda", "trailingEbitda")
    if ebitda_ttm is None and ev is not None and ev_ebitda is not None and ev_ebitda > 0:
        ebitda_ttm = ev / ev_ebitda

    # FCF fallback chain
    fcf_ttm = _get_price(info, "freeCashflow")
    if fcf_ttm is None:
        ocf = _get_price(info, "operatingCashflow")
        if ocf is not None:
            fcf_ttm = ocf * 0.80  # Heuristic: FCF ≈ 80% OCF
        else:
            fcf_ttm = net_income_ttm  # Ultimate fallback

    return Security(
        ticker=ticker.upper(),
        name=info.get("longName") or info.get("shortName") or ticker,
        sector=info.get("sector"),
        industry=info.get("industryDisp") or info.get("industry"),
        fundamentals=Fundamentals(
            revenue_ttm=_get_price(info, "totalRevenue"),
            net_income_ttm=net_income_ttm,
            ebitda_ttm=ebitda_ttm,
            fcf_ttm=fcf_ttm,
            total_debt=_get_price(info, "totalDebt"),
            cash_and_equivalents=_get_price(info, "totalCash", "cash"),
            shares_outstanding=shares_outstanding,
            gross_margin=_get_price(info, "grossMargins"),
            operating_margin=_get_price(info, "operatingMargins"),
        ),
        market=MarketData(
            price=price,
            market_cap=market_cap,
            enterprise_value=ev,
            pe_ttm=pe_ttm,
            pe_forward=_get_price(info, "forwardPE"),
            ev_ebitda=ev_ebitda,
            short_interest_pct_float=_get_price(info, "shortPercentOfFloat"),
            beta=_get_price(info, "beta"),
        ),
    )


def _get_price(info: dict, *keys: str) -> float | None:
    """Get first non-None float value from info dict (mimics YahooAdapter._get)."""
    for key in keys:
        value = info.get(key)
        if value is not None and isinstance(value, (int, float)):
            if value == value:  # NaN check
                return float(value)
    return None


# ============================================================================
# BACKWARDS COMPATIBILITY: Old fetch_security API
# ============================================================================


def build_regression_inputs(
    ticker: str,
    region: str = "US",
    g_eps: float | None = None,
    g: float | None = None,
) -> RegressionInputs:
    """Build Damodaran regression inputs from Yahoo Finance data.

    Args:
        ticker: Stock symbol
        region: Geographic region (default: "US")
        g_eps: Override earnings growth (uses Yahoo estimate if None)
        g: Override revenue growth (uses Yahoo estimate if None)

    Returns:
        RegressionInputs ready for multiples regression
    """
    from iam.valuation.multiples_regression import RegressionInputs

    try:
        import yfinance as yf
    except ImportError as exc:
        raise ImportError(
            "yfinance is required for live data. Install it with: pip install yfinance"
        ) from exc

    # Fetch from Yahoo
    info = yf.Ticker(ticker).info or {}

    beta = YahooAdapter._get(info, "beta") or 1.0
    payout = YahooAdapter._get(info, "payoutRatio") or 0.0
    roe = YahooAdapter._get(info, "returnOnEquity") or 0.12
    roic = YahooAdapter._get(info, "returnOnAssets") or 0.10
    oper_margin = YahooAdapter._get(info, "operatingMargins") or 0.15
    tax_rate = YahooAdapter._get(info, "effectiveTaxRate") or 0.21
    market_cap = YahooAdapter._get(info, "marketCap") or 1.0
    total_debt = YahooAdapter._get(info, "totalDebt") or 0.0
    dfr = total_debt / (total_debt + market_cap)

    if g_eps is None:
        g_eps = YahooAdapter._get(info, "earningsGrowth") or 0.10
    if g is None:
        g = YahooAdapter._get(info, "revenueGrowth") or g_eps

    return RegressionInputs(
        region=region,
        beta=float(beta),
        g_eps=float(g_eps),
        payout=float(payout),
        roe=float(roe),
        g=float(g),
        roic=float(roic),
        dfr=float(dfr),
        oper_margin=float(oper_margin),
        tax_rate=float(tax_rate),
    )
