"""Yahoo Finance Data Adapter with SQLite Caching and Normalization.

This module serves as the primary yfinance provider for the IAM framework.
It integrates local caching (SQLite, 24h expiry) and robust data validation/normalization
with math fallbacks.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sqlite3
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, cast

import pandas as pd
import yfinance as yf

from iam.data.rd import capitalise_rd
from iam.data.retry import retry_call
from iam.data.security import Fundamentals, MarketData, Security

if TYPE_CHECKING:
    from iam.data.edgar.client import EdgarClient
    from iam.data.edgar.geography import GeographicMixResult
    from iam.valuation.multiples_regression import RegressionInputs

logger = logging.getLogger(__name__)

# Cache paths relative to the project root
SEED_CACHE_PATH = "data/cache/seed_cache.sqlite"
RUNTIME_CACHE_PATH = "data/cache/iam_cache.sqlite"


def _open(path: str, timeout: float = 15.0) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=timeout)
    conn.execute("PRAGMA journal_mode=WAL")  # readers don't block the writer
    conn.execute("PRAGMA busy_timeout=15000")  # ms; pairs with timeout=
    conn.execute("PRAGMA synchronous=NORMAL")  # safe under WAL, faster
    return conn


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
        conn = _open(RUNTIME_CACHE_PATH, timeout=15.0)
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
        conn = _open(RUNTIME_CACHE_PATH, timeout=15.0)
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
        conn = _open(RUNTIME_CACHE_PATH, timeout=15.0)
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
        "revenue_mix": security.revenue_mix,
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
        revenue_mix=data.get("revenue_mix", {}),
    )


# Income-statement row labels yfinance uses for the effective tax rate.
_TAX_ROWS = ("Tax Provision", "Income Tax Expense")
_PRETAX_ROWS = ("Pretax Income",)
MAX_EFFECTIVE_TAX_RATE = 0.60  # a ratio above this is a one-off, not a tax rate


def _latest_value(financials: Any, labels: tuple[str, ...]) -> float | None:
    """Latest-fiscal-year value of the first row in ``labels`` that has one; None otherwise."""
    for label in labels:
        if label not in financials.index:
            continue
        row = financials.loc[label]
        try:  # columns are period-end dates, normally newest first; do not rely on it
            col = max(row.index)
            value = row[col]
        except (TypeError, ValueError):
            value = row.iloc[0]
        if pd.notnull(value):
            return float(value)
        # NaN in this row's latest year: try the next candidate label.
    return None


def effective_tax_rate_from_statement(financials: Any) -> tuple[float | None, str | None]:
    """Effective tax rate (tax provision / pretax income, latest fiscal year) and why not.

    Returns ``(rate, None)`` or ``(None, reason)``. None when either input is missing,
    pretax income is not positive, or the ratio is outside [0, 0.6]. Never invented.
    """
    if financials is None or getattr(financials, "empty", True):
        return None, "no income statement"
    tax = _latest_value(financials, _TAX_ROWS)
    if tax is None:
        return None, "no tax provision in the latest fiscal year"
    pretax = _latest_value(financials, _PRETAX_ROWS)
    if pretax is None:
        return None, "no pretax income in the latest fiscal year"
    if pretax <= 0:
        return None, f"pretax income {pretax:g} <= 0"
    rate = tax / pretax
    if not 0.0 <= rate <= MAX_EFFECTIVE_TAX_RATE:
        return None, f"ratio {rate:.1%} outside [0%, {MAX_EFFECTIVE_TAX_RATE:.0%}]"
    return rate, None


def _edgar_revenue_mix(
    ticker: str, as_of: date, client: EdgarClient | None = None
) -> GeographicMixResult:
    """The geographic revenue mix of the latest 10-K filed by ``as_of`` (SEC EDGAR).

    A module-level seam: tests patch this function, so no test reaches the network.
    """
    from iam.data.edgar.geography import geographic_mix_as_of

    return geographic_mix_as_of(ticker, as_of, client)


def _live_revenue_mix(ticker: str) -> tuple[dict[str, float], str]:
    """``(revenue_mix, source)``: the 10-K mix, or ``({}, reason)``. Never raises."""
    try:
        result = _edgar_revenue_mix(ticker, date.today())
    except Exception as exc:  # EDGAR trouble must never fail a fetch; the reason is recorded
        logger.warning("EDGAR revenue mix failed for %s: %s", ticker, exc)
        return {}, f"EDGAR geographic mix unavailable: {type(exc).__name__}: {exc}"
    if result.mix is None:
        reason = result.reason or "no mix and no reason returned"
        return {}, f"EDGAR geographic mix unavailable: {reason}"
    return dict(result.mix.mix), result.mix.source()


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

        def _fetch_info() -> tuple[Any, dict[str, Any]]:
            t = yf.Ticker(ticker)
            return t, (t.info or {})

        try:
            yt, info = retry_call(
                _fetch_info,
                attempts=max_retries,
                base_delay=base_delay,
                jitter=1.0,
                description=f"yfinance fetch for {ticker}",
            )
        except Exception as exc:
            raise RuntimeError(
                f"Yahoo Finance returned an error for '{ticker}' after {max_retries} attempts: {exc}"
            ) from exc

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
        if yt is None:
            raise RuntimeError(f"Failed to initialize yfinance ticker for {ticker}")

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
            payout_ratio=self._get_numeric(info, "payoutRatio"),
        )

        # Extract book equity from balance sheet
        bs = cf = None
        try:
            bs = yt.balance_sheet
            if bs is not None and not bs.empty:
                for eq_label in (
                    "Stockholders Equity",
                    "Common Stock Equity",
                    "Total Equity Gross Minority Interest",
                ):
                    if eq_label in bs.index:
                        eq_val = bs.loc[eq_label].iloc[0]
                        if pd.notnull(eq_val):
                            f.book_equity = float(eq_val)
                            break
        except Exception as e:
            logger.warning(f"Failed to parse balance sheet for {ticker}: {e}")

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

        effective, why_not = effective_tax_rate_from_statement(financials)
        f.effective_tax_rate = effective
        try:
            for name, values in annual_histories(financials, bs, cf, effective).items():
                setattr(f, name, values)
        except Exception as e:
            logger.warning(f"Failed to parse annual histories for {ticker}: {e}")

        qualitative: dict[str, Any] = {
            "payout": f.payout_ratio,
            "roe": self._get_numeric(info, "returnOnEquity"),
            "roa": self._get_numeric(info, "returnOnAssets"),
            "roic": estimate_roic(f),
        }
        qualitative["defaulted_inputs"] = (
            [] if effective is not None else [f"effective_tax_rate: {why_not}"]
        )

        security = Security(
            ticker=ticker.upper(),
            name=info.get("longName") or info.get("shortName") or ticker.upper(),
            sector=info.get("sector"),
            industry=info.get("industryDisp") or info.get("industry"),
            fundamentals=f,
            market=m,
            qualitative=qualitative,
        )
        # Geographic revenue mix from the latest 10-K (SEC EDGAR); empty, with the reason
        # recorded, when EDGAR has none. Set before the marginal tax below reads it.
        security.revenue_mix, security.qualitative["revenue_mix_source"] = _live_revenue_mix(
            ticker.upper()
        )
        # MARGINAL rate (Damodaran statutory, revenue-weighted once a mix is known): the
        # rate beta relevering (valuation.beta) and the cost of debt read. The effective
        # rate above never replaces it there.
        from iam.valuation.country_tax import company_marginal_tax

        marginal, marginal_source = company_marginal_tax(security)
        security.qualitative["tax_rate"] = marginal
        security.qualitative["tax_rate_source"] = marginal_source

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
        roic: float | None = None,
    ) -> RegressionInputs:
        """Build Damodaran regression inputs from Yahoo Finance data."""
        from iam.valuation.multiples_regression import Region, RegressionInputs

        # Try to use caching via fetch
        defaulted: list[str] = []
        fetched_roic: float | None = None
        try:
            security = self.fetch(ticker)
            market_cap = security.market.market_cap
            total_debt = security.fundamentals.total_debt
            beta = security.market.beta
            oper_margin = security.fundamentals.operating_margin
            payout = security.qualitative.get("payout")
            roe = security.qualitative.get("roe")
            fetched_roic = security.qualitative.get("roic")
            tax_rate = security.fundamentals.effective_tax_rate
            tax_security = security
        except Exception:
            # Fallback if fetch fails
            yt = yf.Ticker(ticker)
            info = yt.info or {}
            market_cap = self._get_numeric(info, "marketCap")
            total_debt = self._get_numeric(info, "totalDebt")
            beta = self._get_numeric(info, "beta")
            oper_margin = self._get_numeric(info, "operatingMargins")
            payout = self._get_numeric(info, "payoutRatio")
            roe = self._get_numeric(info, "returnOnEquity")
            fetched_roic = None
            try:
                tax_rate = effective_tax_rate_from_statement(yt.financials)[0]
            except Exception:
                tax_rate = None
            tax_security = Security(ticker=ticker.upper())

        roic_used = roic if roic is not None else fetched_roic

        if tax_rate is None:
            # No effective rate: fall back to the MARGINAL rate, labelled with its source.
            from iam.valuation.country_tax import company_marginal_tax

            tax_rate, tax_source = company_marginal_tax(tax_security)
            defaulted.append(f"tax_rate: marginal rate {tax_rate:.2%} ({tax_source})")

        if market_cap is not None and total_debt is not None and (total_debt + market_cap) > 0:
            dfr = total_debt / (total_debt + market_cap)
        else:
            dfr = None

        if g is None and g_eps is not None:
            g = g_eps

        return RegressionInputs(
            region=cast(Region, region),
            beta=float(beta) if beta is not None else None,
            g_eps=float(g_eps) if g_eps is not None else None,
            payout=float(payout) if payout is not None else None,
            roe=float(roe) if roe is not None else None,
            g=float(g) if g is not None else None,
            roic=float(roic_used) if roic_used is not None else None,
            dfr=float(dfr) if dfr is not None else None,
            oper_margin=float(oper_margin) if oper_margin is not None else None,
            tax_rate=float(tax_rate) if tax_rate is not None else None,
            defaulted_inputs=defaulted,
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
    roic: float | None = None,
) -> RegressionInputs:
    """Build regression inputs for valuation models."""
    return YFinanceAdapter().build_regression_inputs(ticker, region, g_eps, g, roic=roic)


def estimate_roic(f: Fundamentals) -> float | None:
    """Estimate TTM return on invested capital (NOPAT / invested capital)."""
    if f.revenue_ttm is None or f.operating_margin is None or f.book_equity is None:
        return None
    tax = (
        min(max(float(f.effective_tax_rate), 0.0), 0.35)
        if f.effective_tax_rate is not None
        else 0.21
    )
    nopat = f.revenue_ttm * f.operating_margin * (1.0 - tax)
    invested_capital = f.book_equity + (f.total_debt or 0.0) - (f.cash_and_equivalents or 0.0)
    if nopat <= 0 or invested_capital <= 0:
        return None
    return nopat / invested_capital


def annual_histories(
    financials: Any,
    balance_sheet: Any,
    cashflow: Any,
    tax_fallback: float | None = None,
) -> dict[str, list[float]]:
    """Aligned fiscal-year histories (most-recent-first, capped at 6) from yfinance frames."""
    out: dict[str, list[float]] = {
        "nopat_history": [],
        "reinvestment_history": [],
        "invested_capital_history": [],
        "net_income_history": [],
        "equity_payout_history": [],
        "book_equity_history": [],
    }

    def _cols(df: Any) -> list[Any]:
        if df is None or getattr(df, "empty", True):
            return []
        try:
            return sorted(df.columns, reverse=True)
        except Exception:
            return list(df.columns)

    def _cell(df: Any, col: Any, *labels: str) -> float | None:
        if df is None or getattr(df, "empty", True) or col not in df.columns:
            return None
        for label in labels:
            if label in df.index:
                val = df.loc[label, col]
                if pd.notnull(val):
                    return float(val)
        return None

    fin_cols = _cols(financials)
    fallback = (
        float(tax_fallback)
        if tax_fallback is not None and 0.0 <= tax_fallback <= MAX_EFFECTIVE_TAX_RATE
        else 0.21
    )

    for col in fin_cols:
        if len(out["nopat_history"]) >= 6:
            break
        oi = _cell(financials, col, "Operating Income")
        capex = _cell(cashflow, col, "Capital Expenditure")
        da = _cell(cashflow, col, "Depreciation And Amortization")
        eq = _cell(
            balance_sheet,
            col,
            "Stockholders Equity",
            "Common Stock Equity",
            "Total Equity Gross Minority Interest",
        )
        debt = _cell(balance_sheet, col, "Total Debt")
        cash = _cell(balance_sheet, col, "Cash And Cash Equivalents")
        if None in (oi, capex, da, eq, debt, cash):
            break
        tr = _cell(financials, col, "Tax Rate For Calcs")
        tax = tr if tr is not None and 0.0 <= tr <= MAX_EFFECTIVE_TAX_RATE else fallback
        acq = abs(_cell(cashflow, col, "Purchase Of Business") or 0.0)
        wc = -(_cell(cashflow, col, "Change In Working Capital") or 0.0)
        out["nopat_history"].append(float(oi) * (1.0 - tax))  # type: ignore[arg-type]
        out["reinvestment_history"].append(abs(float(capex)) - float(da) + acq + wc)  # type: ignore[arg-type]
        out["invested_capital_history"].append(float(eq) + float(debt) - float(cash))  # type: ignore[arg-type]

    # Capitalise R&D (iam.data.rd). yfinance has about four fiscal years, so the earliest
    # years' amortisation sees fewer prior years and the asset is understated there.
    rd = [_cell(financials, col, "Research And Development") or 0.0 for col in fin_cols]
    if any(rd):
        for i, (delta, asset) in enumerate(capitalise_rd(rd)[: len(out["nopat_history"])]):
            out["nopat_history"][i] += delta
            out["reinvestment_history"][i] += delta
            out["invested_capital_history"][i] += asset

    for col in fin_cols:
        if len(out["net_income_history"]) >= 6:
            break
        ni = _cell(financials, col, "Net Income")
        eq = _cell(
            balance_sheet,
            col,
            "Stockholders Equity",
            "Common Stock Equity",
            "Total Equity Gross Minority Interest",
        )
        if ni is None or eq is None:
            break
        div = abs(_cell(cashflow, col, "Cash Dividends Paid") or 0.0)
        bb = abs(_cell(cashflow, col, "Repurchase Of Capital Stock") or 0.0)
        out["net_income_history"].append(float(ni))
        out["equity_payout_history"].append(div + bb)
        out["book_equity_history"].append(float(eq))

    return out
