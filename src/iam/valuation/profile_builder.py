"""Build CompanyProfile from Security object for adaptive valuation."""

from __future__ import annotations

import numpy as np
from iam.data.security import Security
from iam.valuation.adaptive import CompanyProfile


def compute_reverse_dcf_growth(security: Security) -> float:
    """Compute implied growth rate from current price (reverse DCF).

    Simple approximation: uses dividend discount model or FCF yield assumptions.
    Falls back to sector median if insufficient data.

    Args:
        security: Security object with market and fundamentals data

    Returns:
        Implied annual growth rate [0.0, 1.0]
    """
    if not security.market or not security.market.price:
        return 0.08  # Default fallback

    # Simplified reverse DCF: Price/Book as proxy
    # In production, use full DCF with estimated WACC
    price_to_book = getattr(security.fundamentals, "price_to_book", None) or 1.5
    implied_roe = getattr(security.fundamentals, "roe", 0.12)

    if price_to_book > 0 and implied_roe > 0:
        # Rough estimate: growth ≈ ROE * retention - (1/PB - 1/ROE)
        implied_growth = (implied_roe * 0.6) * price_to_book / max(price_to_book, 1.0)
        return max(0.01, min(0.25, implied_growth))

    return 0.08


def compute_historical_eps_growth(security: Security) -> float:
    """Compute 5-10 year smoothed EPS growth.

    Args:
        security: Security object

    Returns:
        Historical annual EPS growth rate [0.0, 0.5]
    """
    # Try to extract from fundamentals or use default
    hist_growth = getattr(security.fundamentals, "eps_growth_5y", None) or getattr(
        security.fundamentals, "revenue_growth_5y", None
    )

    if hist_growth is not None and 0.0 <= hist_growth <= 0.5:
        return hist_growth

    # Default by sector
    sector = security.sector or "Technology"
    defaults = {
        "Technology": 0.15,
        "Healthcare": 0.10,
        "Financials": 0.05,
        "Consumer": 0.08,
        "Industrials": 0.07,
        "Utilities": 0.03,
        "Energy": 0.05,
    }
    return defaults.get(sector, 0.08)


def compute_eps_volatility(security: Security) -> float:
    """Compute standard deviation of EPS growth.

    Args:
        security: Security object

    Returns:
        Annual EPS growth volatility [0.0, 1.0]
    """
    # Try to extract from fundamentals
    vol = getattr(security.fundamentals, "eps_volatility", None)

    if vol is not None and 0.0 <= vol <= 1.0:
        return vol

    # Default by sector/type
    sector = security.sector or "Technology"
    defaults = {
        "Technology": 0.25,
        "Healthcare": 0.15,
        "Financials": 0.20,
        "Consumer": 0.12,
        "Industrials": 0.18,
        "Utilities": 0.08,
        "Energy": 0.40,
    }
    return defaults.get(sector, 0.15)


def build_company_profile(
    security: Security, sector_growth: float = 0.08, adjacent_growth: float = 0.10
) -> CompanyProfile:
    """Build CompanyProfile from Security object.

    Args:
        security: Security object from IAM data layer
        sector_growth: Sector median growth rate [default: 8%]
        adjacent_growth: Adjacent sector growth [default: 10%]

    Returns:
        CompanyProfile ready for adaptive valuation engine
    """
    implied_growth = compute_reverse_dcf_growth(security)
    hist_eps_growth = compute_historical_eps_growth(security)
    hist_volatility = compute_eps_volatility(security)

    # Operating margin
    op_margin = getattr(security.fundamentals, "operating_margin", 0.10) or 0.10
    sector_margin = 0.10  # Default; ideally pull from sector

    # ROE and ROIC
    roe = getattr(security.fundamentals, "roe", 0.12) or 0.12
    roic = getattr(security.fundamentals, "roic", 0.10) or 0.10

    # Mid-cycle margin (for cyclicals)
    mid_cycle_margin = getattr(
        security.fundamentals, "mid_cycle_margin", op_margin * 0.9
    ) or (op_margin * 0.9)

    return CompanyProfile(
        ticker=security.ticker,
        implied_growth=implied_growth,
        hist_eps_growth=hist_eps_growth,
        hist_volatility=hist_volatility,
        sector_growth=sector_growth,
        adjacent_growth=adjacent_growth,
        op_margin=op_margin,
        sector_margin=sector_margin,
        roe=roe,
        roic=roic,
        mid_cycle_margin=mid_cycle_margin,
    )
