"""Yahoo Finance Data Adapter with SQLite Caching and Normalization.

This module serves as the primary yfinance provider for the IAM framework.
It integrates local caching (SQLite, 24h expiry) and robust data validation/normalization
with math fallbacks.
"""

from __future__ import annotations

import json
import logging
import os
import random
import shutil
import sqlite3
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

import pandas as pd
import yfinance as yf

from iam.data.security import Fundamentals, MarketData, Security

if TYPE_CHECKING:
    from iam.valuation.multiples_regression import Region, RegressionInputs

logger = logging.getLogger(__name__)

# Cache paths relative to the project root
SEED_CACHE_PATH = "data/cache/seed_cache.sqlite"
RUNTIME_CACHE_PATH = "data/cache/iam_cache.sqlite"


class DataProviderError(Exception):
    """Raised when data provider fails or returns invalid data."""

    pass


def _init_cache_db() -> bool:
    """Initialize SQLite cache database for normalized security data."""
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
                cached_data: dict[str, Any] = json.loads(data_str)
                return cached_data
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


def _serialize_security(security: Security) -> dict[str, Any]:
    """Serialize Security object to a JSON-compatible dict."""
    return {
        "ticker": security.ticker,
        "name": security.name,
        "sector": security.sector,
        "industry": security.industry,
        "fundamentals": {k: v for k, v in security.fundamentals.__dict__.items()},
        "market": {k: v for k, v in security.market.__dict__.items()},
        "qualitative": security.qualitative,
    }


def _deserialize_security(data: dict[str, Any]) -> Security:
    """Reconstruct Security object from a serialized dict."""
    fundamentals_data = data.get("fundamentals", {})
    market_data = data.get("market", {})
    return Security(
        ticker=data["ticker"],
        name=data.get("name"),
        sector=data.get("sector"),
        industry=data.get("industry"),
        fundamentals=Fundamentals(**fundamentals_data),
        market=MarketData(**market_data),
        qualitative=data.get("qualitative", {}),
    )


class YFinanceAdapter:
    """Fetches data from Yahoo Finance, caches locally, and normalizes inputs."""

    def fetch(self, ticker: str) -> Security:
        """Fetch data for a ticker with caching and math fallbacks."""
        # 1. Check cache first
        cached = _get_cached_data(ticker)
        if cached is not None:
            logger.info(f"[DATA] {ticker} (from cache)")
            return _deserialize_security(cached)

        # 2. Cache miss -> fetch live
        logger.info(f"Fetching live data for {ticker} via yfinance...")

        max_retries = 3
        base_delay = 2.0

        info = {}
        yt = None
        for attempt in range(max_retries):
            try:
                yt = yf.Ticker(ticker)
                info = yt.info or {}
                break
            except Exception as exc:
                if attempt == max_retries - 1:
                    raise RuntimeError(f"Yahoo Finance returned an error for '{ticker}' after {max_retries} attempts: {exc}") from exc

                delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                logger.warning(f"yfinance fetch failed for {ticker}. Retrying in {delay:.1f}s (Attempt {attempt+1}/{max_retries})... Error: {exc}")
                time.sleep(delay)

        # Extract price - required field
        price = self._get_numeric(info, "currentPrice", "regularMarketPrice", "previousClose")
        if price is None:
            raise RuntimeError(
                f"Yahoo Finance returned no price data for '{ticker}'. "
                "Check the ticker symbol and network connection."
            )

        # Extract base fields for math fallbacks
        market_cap = self._get_numeric(info, "marketCap")
        pe_ttm = self._get_numeric(info, "trailingPE")
        ev = self._get_numeric(info, "enterpriseValue")
        ev_ebitda = self._get_numeric(info, "enterpriseToEbitda")

        # Math fallbacks: compute missing values from available ones
        shares_outstanding = self._get_numeric(
            info, "sharesOutstanding", "impliedSharesOutstanding", "floatShares"
        )
        if shares_outstanding is None and market_cap is not None and price > 0:
            shares_outstanding = market_cap / price

        net_income_ttm = self._get_numeric(
            info, "netIncomeToCommon", "trailingNetIncome", "netIncome"
        )
        if net_income_ttm is None and market_cap is not None and pe_ttm is not None and pe_ttm > 0:
            net_income_ttm = market_cap / pe_ttm

        ebitda_ttm = self._get_numeric(info, "ebitda", "trailingEbitda")
        if ebitda_ttm is None and ev is not None and ev_ebitda is not None and ev_ebitda > 0:
            ebitda_ttm = ev / ev_ebitda

        # FCF fallback chain
        fcf_ttm = self._get_numeric(info, "freeCashflow")
        if fcf_ttm is None:
            ocf = self._get_numeric(info, "operatingCashflow")
            if ocf is not None:
                fcf_ttm = ocf * 0.80  # Heuristic: FCF ≈ 80% OCF
            else:
                fcf_ttm = net_income_ttm  # Ultimate fallback

        # Fetch financials for historical series
        try:
            financials = yt.financials
        except Exception:
            financials = pd.DataFrame()

        # Build fundamentals
        f = Fundamentals(
            revenue_ttm=self._get_numeric(info, "totalRevenue"),
            net_income_ttm=net_income_ttm,
            ebitda_ttm=ebitda_ttm,
            fcf_ttm=fcf_ttm,
            total_debt=self._get_numeric(info, "totalDebt"),
            cash_and_equivalents=self._get_numeric(info, "totalCash", "cash"),
            shares_outstanding=shares_outstanding,
            gross_margin=self._get_numeric(info, "grossMargins"),
            operating_margin=self._get_numeric(info, "operatingMargins"),
        )

        # Extract cash flow statements (Working Capital, SBC, Capex)
        try:
            cf = yt.cashflow
            if cf is not None and not cf.empty:
                if "Change In Working Capital" in cf.index:
                    wc_val = cf.loc["Change In Working Capital"].iloc[0]
                    f.change_in_working_capital = float(wc_val) if pd.notnull(wc_val) else None

                if "Stock Based Compensation" in cf.index:
                    sbc_val = cf.loc["Stock Based Compensation"].iloc[0]
                    f.sbc_ttm = float(sbc_val) if pd.notnull(sbc_val) else 0.0

                if "Capital Expenditure" in cf.index:
                    capex_val = cf.loc["Capital Expenditure"].iloc[0]
                    f.capex_ttm = abs(float(capex_val)) if pd.notnull(capex_val) else None

                if f.net_income_ttm and f.fcf_ttm and f.revenue_ttm:
                    f.accruals_ratio = (f.net_income_ttm - f.fcf_ttm) / f.revenue_ttm
        except Exception as e:
            logger.warning(f"Failed to parse cash flow statement for {ticker}: {e}")

        # Parse History
        if not financials.empty:
            try:
                if "Total Revenue" in financials.index:
                    rev_series = financials.loc["Total Revenue"].dropna()
                    f.revenue_history = rev_series.tolist()

                if "Operating Income" in financials.index and "Total Revenue" in financials.index:
                    op_inc = financials.loc["Operating Income"]
                    rev = financials.loc["Total Revenue"]
                    margins = (op_inc / rev).dropna()
                    f.operating_margin_history = margins.tolist()
            except Exception as e:
                logger.warning(f"Failed to parse historical financials for {ticker}: {e}")

        # Build market data
        m = MarketData(
            price=price,
            market_cap=market_cap,
            enterprise_value=ev,
            pe_ttm=pe_ttm,
            pe_forward=self._get_numeric(info, "forwardPE"),
            ev_ebitda=ev_ebitda,
            ev_sales=self._get_numeric(info, "enterpriseToRevenue"),
            short_interest_pct_float=self._get_numeric(info, "shortPercentOfFloat"),
            beta=self._get_numeric(info, "beta"),
        )

        # Free Cash Flow Yield calculation
        if f.fcf_ttm is not None and m.market_cap is not None and m.market_cap > 0:
            m.fcf_yield = f.fcf_ttm / m.market_cap

        security = Security(
            ticker=ticker.upper(),
            name=info.get("longName") or info.get("shortName") or ticker.upper(),
            sector=info.get("sector"),
            industry=info.get("industryDisp") or info.get("industry"),
            fundamentals=f,
            market=m,
            qualitative={},
        )

        # Cache the result
        try:
            _save_cached_data(ticker, _serialize_security(security))
        except Exception as e:
            logger.warning(f"Failed to cache security data for {ticker}: {e}")

        return security

    def build_regression_inputs(
        self,
        ticker: str,
        region: str = "US",
        g_eps: float | None = None,
        g: float | None = None,
    ) -> RegressionInputs:
        """Build Damodaran regression inputs from Yahoo Finance data."""
        from iam.valuation.multiples_regression import RegressionInputs

        # Try to use caching via fetch
        try:
            security = self.fetch(ticker)
            market_cap = security.market.market_cap or 1.0
            total_debt = security.fundamentals.total_debt or 0.0
            beta = security.market.beta or 1.0
            oper_margin = security.fundamentals.operating_margin or 0.15
            # Fallbacks for regression
            payout = 0.0
            roe = 0.12
            roic = 0.10
            tax_rate = 0.21
        except Exception:
            # Fallback if fetch fails
            yt = yf.Ticker(ticker)
            info = yt.info or {}
            self._get_numeric(info, "currentPrice", "regularMarketPrice") or 1.0
            market_cap = self._get_numeric(info, "marketCap") or 1.0
            total_debt = self._get_numeric(info, "totalDebt") or 0.0
            beta = self._get_numeric(info, "beta") or 1.0
            oper_margin = self._get_numeric(info, "operatingMargins") or 0.15
            payout = self._get_numeric(info, "payoutRatio") or 0.0
            roe = self._get_numeric(info, "returnOnEquity") or 0.12
            roic = self._get_numeric(info, "returnOnAssets") or 0.10
            tax_rate = self._get_numeric(info, "effectiveTaxRate") or 0.21

        dfr = total_debt / (total_debt + market_cap)

        if g_eps is None:
            g_eps = 0.10
        if g is None:
            g = g_eps

        return RegressionInputs(
            region=cast(Region, region),
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

    def _get_numeric(self, info: dict, *keys: str) -> float | None:
        """Get first non-None numeric value from info dictionary."""
        for key in keys:
            value = info.get(key)
            if value is not None and isinstance(value, int | float):
                if value == value:  # NaN check
                    return float(value)
        return None


# ============================================================================
# Compatibility functions
# ============================================================================


def fetch_security(ticker: str) -> Security:
    """Fetch security from Yahoo Finance with caching."""
    return YFinanceAdapter().fetch(ticker)


def build_regression_inputs(
    ticker: str,
    region: str = "US",
    g_eps: float | None = None,
    g: float | None = None,
) -> RegressionInputs:
    """Build regression inputs for valuation models."""
    return YFinanceAdapter().build_regression_inputs(ticker, region, g_eps, g)
