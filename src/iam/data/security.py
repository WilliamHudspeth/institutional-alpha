"""Core data structures for the Institutional Alpha Model.

This module defines the basic inputs required by the factor scoring engine
and the valuation pipeline.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Fundamentals:
    """Core accounting and operating metrics."""
    revenue_ttm: Optional[float] = None
    revenue_history: List[float] = field(default_factory=list)
    fcf_ttm: Optional[float] = None
    shares_outstanding: Optional[float] = None
    net_income_ttm: Optional[float] = None
    ebitda_ttm: Optional[float] = None
    operating_margin: Optional[float] = None
    operating_margin_history: List[float] = field(default_factory=list)
    total_debt: Optional[float] = None
    cash_and_equivalents: Optional[float] = None


@dataclass
class MarketData:
    """Pricing and multiple data."""
    price: Optional[float] = None
    market_cap: Optional[float] = None
    
    pe_ttm: Optional[float] = None
    pe_history: List[float] = field(default_factory=list)
    
    ev_ebitda: Optional[float] = None
    sector_ev_ebitda_median: Optional[float] = None
    
    # NEW: Added for Relative Value factor
    ev_sales: Optional[float] = None
    peer_ev_sales: List[float] = field(default_factory=list)
    
    fcf_yield: Optional[float] = None
    peer_fcf_yields: List[float] = field(default_factory=list)


@dataclass
class Security:
    """A single equity security and its associated data."""
    ticker: str
    name: str = ""
    sector: str = ""
    fundamentals: Fundamentals = field(default_factory=Fundamentals)
    market: MarketData = field(default_factory=MarketData)
    
    # Stores explicit forecasts, macro assumptions, or SOTP segments
    qualitative: Dict[str, Any] = field(default_factory=dict)
