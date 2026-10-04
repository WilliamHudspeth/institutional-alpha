"""Shared Security fixture factory for unit tests.

Usage::

    from tests.fixtures.sample_securities import make_security

    sec = make_security(operating_margin=0.35, roic_history=[0.22])
"""

from __future__ import annotations

from iam.data.security import Fundamentals, Security
from iam.valuation.sotp import Segment


def make_security(
    ticker: str = "TEST",
    # Fundamentals kwargs — anything accepted by Fundamentals.__init__
    revenue_ttm: float | None = 50e9,
    operating_margin: float | None = None,
    gross_margin: float | None = None,
    net_income_ttm: float | None = None,
    ebitda_ttm: float | None = None,
    fcf_ttm: float | None = None,
    capex_ttm: float | None = None,
    total_debt: float | None = None,
    cash_and_equivalents: float | None = None,
    roic_history: list[float] | None = None,
    # Security-level kwargs
    sector: str | None = None,
    **extra_fundamentals,
) -> Security:
    """Return a minimal, fully-constructed Security with no network calls.

    All Fundamentals fields default to None (absent) unless explicitly supplied.
    Pass any ``Fundamentals`` field as a keyword argument to override.
    """
    fund = Fundamentals(
        revenue_ttm=revenue_ttm,
        operating_margin=operating_margin,
        gross_margin=gross_margin,
        net_income_ttm=net_income_ttm,
        ebitda_ttm=ebitda_ttm,
        fcf_ttm=fcf_ttm,
        capex_ttm=capex_ttm,
        total_debt=total_debt,
        cash_and_equivalents=cash_and_equivalents,
        roic_history=roic_history or [],
        **extra_fundamentals,
    )
    return Security(ticker=ticker, sector=sector, fundamentals=fund)


def sample_segments() -> list[Segment]:
    """Two illustrative test-only segments for SOTP tests (not real company data)."""
    return [
        Segment(
            "SegmentA",
            revenue=600.0,
            ebit=200.0,
            unlevered_beta=0.8,
            tax_rate=0.21,
            growth_rate=0.03,
            fcfe=150.0,
        ),
        Segment(
            "SegmentB",
            revenue=400.0,
            ebit=100.0,
            unlevered_beta=1.2,
            tax_rate=0.21,
            growth_rate=0.02,
            fcfe=80.0,
        ),
    ]
