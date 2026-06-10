"""Build CompanyProfile from Security object using triangulated growth.

Uses multiple growth estimators (implied, historical, sustainable, bottom-up,
sector) and combines them with inverse-variance weighting. Applies margin
trajectory adjustments to catch compression/expansion cases.
"""

from __future__ import annotations

import numpy as np

from iam.data.security import Security
from iam.valuation.adaptive import CompanyProfile
from iam.valuation.growth_triangulator import (
    TriangulatedGrowth,
    detect_margin_trajectory,
    estimate_bottom_up_growth,
    estimate_historical_growth,
    estimate_implied_growth,
    estimate_sector_growth,
    estimate_sustainable_growth,
    triangulate_growth,
)


def _safe_get_history_avg(history: list[float], years: int = 5) -> float | None:
    """Get mean of first N values in a history list."""
    if not history:
        return None
    clean = [v for v in history[:years] if v is not None]
    if not clean:
        return None
    return float(np.mean(clean))


def _compute_revenue_cagr(revenue_history: list[float], years: int = 5) -> float | None:
    """Compute CAGR from revenue history (most-recent-first)."""
    if not revenue_history or len(revenue_history) < 2:
        return None
    clean = [r for r in revenue_history if r is not None and r > 0]
    if len(clean) < 2:
        return None
    n = min(years, len(clean) - 1)
    end_value = clean[0]  # Most recent
    start_value = clean[n]  # N years ago
    if start_value <= 0:
        return None
    return float((end_value / start_value) ** (1.0 / n) - 1.0)


def _compute_eps_volatility(revenue_history: list[float], fcf_history: list[float]) -> float | None:
    """Compute company-specific volatility from EPS/revenue/FCF history.

    Uses FCF if available, else revenue. Returns std dev of year-over-year
    growth rates. This is the company-specific volatility, not sector average.

    Args:
        revenue_history: Most-recent-first revenue
        fcf_history: Most-recent-first FCF

    Returns:
        Annual growth volatility [0.05, 1.0] or None
    """
    series = fcf_history if fcf_history and len(fcf_history) >= 3 else revenue_history
    if not series or len(series) < 3:
        return None

    clean = [x for x in series if x is not None]
    if len(clean) < 3:
        return None

    growth_rates = []
    for i in range(len(clean) - 1):
        if clean[i + 1] != 0:
            g = (clean[i] - clean[i + 1]) / abs(clean[i + 1])
            growth_rates.append(g)

    if len(growth_rates) < 2:
        return None

    vol = float(np.std(growth_rates))
    return max(0.05, min(1.0, vol))


def build_company_profile(
    security: Security,
    sector_growth_table: dict[str, float] | None = None,
    adjacent_growth: float | None = None,
) -> CompanyProfile:
    """Build CompanyProfile using triangulated growth estimation.

    This is the high-precision profile builder. It:
    1. Pulls company-specific data (revenue, FCF, margin, ROIC histories)
    2. Computes 5 independent growth estimates (implied, historical, sustainable, bottom-up, sector)
    3. Triangulates with inverse-variance weighting
    4. Detects margin trajectory and applies adjustment
    5. Uses company-specific volatility (not sector default)

    Args:
        security: Security with fundamentals and market data
        sector_growth_table: Optional sector growth overrides
        adjacent_growth: Optional override for adjacent sector growth

    Returns:
        CompanyProfile ready for adaptive engine
    """
    fundamentals = security.fundamentals
    sector = security.sector or "Technology"

    # --- Compute triangulated growth ---
    triangulation = triangulate_growth_for_security(security, sector_growth_table)
    implied_growth = triangulation.blended_growth

    # --- Historical EPS growth from data ---
    hist_growth_est = estimate_historical_growth(
        revenue_history=fundamentals.revenue_history,
        fcf_history=fundamentals.fcf_history,
    )
    if hist_growth_est is not None:
        hist_eps_growth = hist_growth_est.value
    else:
        # Fallback to sector default
        sector_est = estimate_sector_growth(sector, sector_growth_table)
        hist_eps_growth = sector_est.value

    # --- Company-specific volatility ---
    company_vol = _compute_eps_volatility(fundamentals.revenue_history, fundamentals.fcf_history)
    if company_vol is None:
        company_vol = _sector_volatility_default(sector)

    # --- Sector growth (from Damodaran-style table) ---
    sector_growth_est = estimate_sector_growth(sector, sector_growth_table)
    sector_growth = sector_growth_est.value

    # --- Adjacent sector growth (default: sector + 2%) ---
    if adjacent_growth is None:
        adjacent_growth = min(0.20, sector_growth + 0.02)

    # --- Operating margins ---
    op_margin = fundamentals.operating_margin or 0.10
    op_margin_history = fundamentals.operating_margin_history or []

    # Sector margin baseline by sector
    sector_margin = _sector_margin_default(sector)

    # --- ROE/ROIC ---
    roic_history = fundamentals.roic_history or []
    roe = _safe_get_history_avg(roic_history, years=3) or fundamentals.incremental_roic or 0.12
    roic = _safe_get_history_avg(roic_history, years=5) or fundamentals.incremental_roic or 0.10

    # --- Mid-cycle margin for cyclicals ---
    mid_cycle_margin = _safe_get_history_avg(op_margin_history, years=10) or (op_margin * 0.9)

    return CompanyProfile(
        ticker=security.ticker,
        implied_growth=implied_growth,
        hist_eps_growth=hist_eps_growth,
        hist_volatility=company_vol,
        sector_growth=sector_growth,
        adjacent_growth=adjacent_growth,
        op_margin=op_margin,
        sector_margin=sector_margin,
        roe=roe,
        roic=roic,
        mid_cycle_margin=mid_cycle_margin,
    )


def triangulate_growth_for_security(
    security: Security,
    sector_growth_table: dict[str, float] | None = None,
) -> TriangulatedGrowth:
    """Run full growth triangulation for a security.

    Args:
        security: Security with fundamentals and market data
        sector_growth_table: Optional sector growth overrides

    Returns:
        TriangulatedGrowth with blended estimate and audit trail
    """
    fundamentals = security.fundamentals
    market = security.market
    sector = security.sector or "Technology"

    # --- Estimator 1: Implied growth (reverse DCF) ---
    price = market.price if market else None
    implied_est = estimate_implied_growth(
        price=price,
        fcf_ttm=fundamentals.fcf_ttm,
        shares_outstanding=fundamentals.shares_outstanding,
        wacc=0.09,
        terminal_growth=0.025,
    )

    # --- Estimator 2: Historical CAGR ---
    historical_est = estimate_historical_growth(
        revenue_history=fundamentals.revenue_history,
        fcf_history=fundamentals.fcf_history,
    )

    # --- Estimator 3: Sustainable growth (ROE-based, critical for financials) ---
    roe = _safe_get_history_avg(fundamentals.roic_history, years=3)
    if roe is None:
        roe = fundamentals.incremental_roic
    sustainable_est = estimate_sustainable_growth(
        roe=roe,
        payout_ratio=None,  # Could be derived from dividend data
        roic_history=fundamentals.roic_history,
    )

    # --- Estimator 4: Bottom-up build ---
    rev_growth_5y = _compute_revenue_cagr(fundamentals.revenue_history, years=5)
    op_margin_5y_avg = _safe_get_history_avg(fundamentals.operating_margin_history, years=5)
    bottom_up_est = estimate_bottom_up_growth(
        revenue_growth_5y=rev_growth_5y,
        operating_margin=fundamentals.operating_margin,
        operating_margin_5y_avg=op_margin_5y_avg,
    )

    # --- Estimator 5: Sector median (always provided as prior) ---
    sector_est = estimate_sector_growth(sector, sector_growth_table)

    # --- Margin trajectory detection ---
    margin_info = detect_margin_trajectory(
        operating_margin=fundamentals.operating_margin,
        operating_margin_history=fundamentals.operating_margin_history,
    )
    margin_adjustment = margin_info["adjustment"]

    # --- Triangulate ---
    return triangulate_growth(
        estimates=[
            implied_est,
            historical_est,
            sustainable_est,
            bottom_up_est,
            sector_est,
        ],
        margin_adjustment=margin_adjustment,
    )


def _sector_volatility_default(sector: str) -> float:
    """Default volatility by sector when no company history available."""
    defaults = {
        "Technology": 0.25,
        "Healthcare": 0.15,
        "Financials": 0.20,
        "Consumer": 0.12,
        "Consumer Discretionary": 0.18,
        "Consumer Staples": 0.08,
        "Industrials": 0.18,
        "Utilities": 0.08,
        "Energy": 0.40,
        "Materials": 0.25,
        "Real Estate": 0.15,
        "Communication Services": 0.20,
    }
    return defaults.get(sector, 0.15)


def _sector_margin_default(sector: str) -> float:
    """Default sector median operating margin."""
    defaults = {
        "Technology": 0.22,
        "Healthcare": 0.15,
        "Financials": 0.30,
        "Consumer": 0.10,
        "Consumer Discretionary": 0.08,
        "Consumer Staples": 0.12,
        "Industrials": 0.10,
        "Utilities": 0.18,
        "Energy": 0.08,
        "Materials": 0.10,
        "Real Estate": 0.20,
        "Communication Services": 0.18,
    }
    return defaults.get(sector, 0.10)
