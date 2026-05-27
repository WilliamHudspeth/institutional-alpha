"""Yahoo Finance data adapter.

Fetches live market data for a ticker and maps it onto the IAM Security
data model. Requires yfinance (pip install yfinance).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from iam.data.security import Fundamentals, MarketData, Security


@dataclass
class MarketSnapshot:
    """Raw numbers pulled from Yahoo Finance before mapping to Security."""

    ticker: str
    price: Optional[float]
    market_cap: Optional[float]
    enterprise_value: Optional[float]
    pe_ttm: Optional[float]
    pe_forward: Optional[float]
    ev_ebitda: Optional[float]
    revenue_ttm: Optional[float]
    net_income_ttm: Optional[float]
    ebitda_ttm: Optional[float]
    fcf_ttm: Optional[float]
    total_debt: Optional[float]
    cash: Optional[float]
    shares_outstanding: Optional[float]
    short_interest_pct: Optional[float]
    gross_margin: Optional[float]
    operating_margin: Optional[float]
    name: Optional[str]
    sector: Optional[str]
    industry: Optional[str]


def fetch_security(ticker: str) -> Security:
    """Return a Security populated with live Yahoo Finance data.

    Raises ImportError if yfinance is not installed.
    Raises RuntimeError if Yahoo Finance is unavailable or returns no price.
    """
    try:
        import yfinance as yf
    except ImportError as exc:
        raise ImportError(
            "yfinance is required for live data. Install it with: pip install yfinance"
        ) from exc

    t = yf.Ticker(ticker)
    try:
        info = t.info
    except Exception as exc:
        raise RuntimeError(
            f"Yahoo Finance returned an error for '{ticker}': {exc}"
        ) from exc

    price = _get(info, "currentPrice", "regularMarketPrice", "previousClose")
    if price is None:
        raise RuntimeError(
            f"Yahoo Finance returned no price data for '{ticker}'. "
            "Check the ticker symbol and your internet connection."
        )

    # 1. Extract base fields required for mathematical fallbacks
    market_cap = _get(info, "marketCap")
    pe_ttm = _get(info, "trailingPE")
    ev = _get(info, "enterpriseValue")
    ev_ebitda = _get(info, "enterpriseToEbitda")

    # 2. Fetch primary values with expanded key fallbacks, then use math if keys fail
    shares_outstanding = _get(info, "sharesOutstanding", "impliedSharesOutstanding", "floatShares")
    if shares_outstanding is None and market_cap is not None and price > 0:
        shares_outstanding = market_cap / price

    net_income_ttm = _get(info, "netIncomeToCommon", "trailingNetIncome", "netIncome")
    if net_income_ttm is None and market_cap is not None and pe_ttm is not None and pe_ttm > 0:
        net_income_ttm = market_cap / pe_ttm

    ebitda_ttm = _get(info, "ebitda", "trailingEbitda")
    if ebitda_ttm is None and ev is not None and ev_ebitda is not None and ev_ebitda > 0:
        ebitda_ttm = ev / ev_ebitda

    # 3. Handle Free Cash Flow fallback (critical for DCF stages)
    fcf_ttm = _get(info, "freeCashflow")
    if fcf_ttm is None:
        ocf = _get(info, "operatingCashflow")
        if ocf is not None:
            # Heuristic: FCF is typically ~80% of OCF for mature companies
            fcf_ttm = ocf * 0.80
        else:
            # Ultimate fallback: Use Net Income as an Earnings Power proxy
            fcf_ttm = net_income_ttm

    snap = MarketSnapshot(
        ticker=ticker.upper(),
        price=price,
        market_cap=market_cap,
        enterprise_value=ev,
        pe_ttm=pe_ttm,
        pe_forward=_get(info, "forwardPE"),
        ev_ebitda=ev_ebitda,
        revenue_ttm=_get(info, "totalRevenue"),
        net_income_ttm=net_income_ttm,
        ebitda_ttm=ebitda_ttm,
        fcf_ttm=fcf_ttm,
        total_debt=_get(info, "totalDebt"),
        cash=_get(info, "totalCash"),
        shares_outstanding=shares_outstanding,
        short_interest_pct=_get(info, "shortPercentOfFloat"),
        gross_margin=_get(info, "grossMargins"),
        operating_margin=_get(info, "operatingMargins"),
        name=info.get("longName") or info.get("shortName"),
        sector=info.get("sector"),
        industry=info.get("industryDisp") or info.get("industry"),
    )
    return _to_security(snap)


def _get(info: dict, *keys: str) -> Optional[float]:
    for k in keys:
        v = info.get(k)
        if v is not None and isinstance(v, (int, float)) and v == v:  # NaN guard
            return float(v)
    return None


def _to_security(snap: MarketSnapshot) -> Security:
    return Security(
        ticker=snap.ticker,
        name=snap.name,
        sector=snap.sector,
        industry=snap.industry,
        fundamentals=Fundamentals(
            revenue_ttm=snap.revenue_ttm,
            net_income_ttm=snap.net_income_ttm,
            ebitda_ttm=snap.ebitda_ttm,
            fcf_ttm=snap.fcf_ttm,
            total_debt=snap.total_debt,
            cash_and_equivalents=snap.cash,
            shares_outstanding=snap.shares_outstanding,
            gross_margin=snap.gross_margin,
            operating_margin=snap.operating_margin,
        ),
        market=MarketData(
            price=snap.price,
            market_cap=snap.market_cap,
            enterprise_value=snap.enterprise_value,
            pe_ttm=snap.pe_ttm,
            pe_forward=snap.pe_forward,
            ev_ebitda=snap.ev_ebitda,
            short_interest_pct_float=snap.short_interest_pct,
        ),
    )
