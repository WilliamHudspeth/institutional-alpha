"""Portfolio data types and structures.

Defines:
- Position: Single holding
- Portfolio: Collection of positions with aggregated metrics
- PortfolioMetrics: Risk/return statistics
- ExposureProfile: Factor and sector exposure analysis
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Position:
    """Single portfolio holding."""

    ticker: str
    name: str
    quantity: float  # Shares held
    entry_price: float  # Average entry price
    current_price: float  # Current market price
    weight: float  # Portfolio weight (0-1)
    sector: str | None = None
    conviction: str = "MODERATE"  # HIGH, MODERATE, LOW

    @property
    def market_value(self) -> float:
        """Current position value."""
        return self.quantity * self.current_price

    @property
    def entry_value(self) -> float:
        """Entry position value."""
        return self.quantity * self.entry_price

    @property
    def pnl_dollar(self) -> float:
        """Unrealized P&L in dollars."""
        return self.market_value - self.entry_value

    @property
    def pnl_pct(self) -> float:
        """Unrealized P&L as percentage."""
        if self.entry_value == 0:
            return 0.0
        return (self.pnl_dollar / self.entry_value) * 100

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict."""
        return {
            "ticker": self.ticker,
            "name": self.name,
            "quantity": self.quantity,
            "entry_price": self.entry_price,
            "current_price": self.current_price,
            "weight": self.weight,
            "market_value": self.market_value,
            "pnl_dollar": self.pnl_dollar,
            "pnl_pct": self.pnl_pct,
            "sector": self.sector,
            "conviction": self.conviction,
        }


@dataclass
class PortfolioMetrics:
    """Risk and return metrics for portfolio."""

    total_value: float  # Total portfolio value
    gross_exposure: float  # Sum of long positions
    net_exposure: float  # Net long/short exposure
    cash: float  # Cash position
    num_positions: int  # Number of holdings

    # Return metrics
    ytd_return: float = 0.0  # YTD return %
    mtd_return: float = 0.0  # Month-to-date return %
    volatility: float = 0.0  # Portfolio volatility (annual %)

    # Risk metrics
    var_95: float = 0.0  # Value at Risk (95% confidence)
    expected_shortfall: float = 0.0  # Expected shortfall
    max_drawdown: float = 0.0  # Historical max drawdown
    sharpe_ratio: float = 0.0  # Risk-adjusted return

    # Concentration
    largest_position: float = 0.0  # Weight of largest position
    herfindahl_index: float = 0.0  # Concentration measure (0-1)

    # Factor exposures
    net_quality: float = 0.0
    net_growth: float = 0.0
    net_value: float = 0.0
    net_momentum: float = 0.0

    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict."""
        return {
            "total_value": f"${self.total_value:,.0f}",
            "gross_exposure": f"{self.gross_exposure:.1%}",
            "net_exposure": f"{self.net_exposure:.1%}",
            "cash": f"${self.cash:,.0f}",
            "positions": self.num_positions,
            "ytd_return": f"{self.ytd_return:+.2f}%",
            "volatility": f"{self.volatility:.1f}%",
            "var_95": f"${self.var_95:,.0f}",
            "max_drawdown": f"{self.max_drawdown:.1f}%",
            "sharpe": f"{self.sharpe_ratio:.2f}",
            "concentration": f"{self.herfindahl_index:.1%}",
        }


@dataclass
class ExposureProfile:
    """Factor and sector exposure analysis."""

    # Factor exposures (z-scores)
    quality_exposure: float = 0.0
    growth_exposure: float = 0.0
    value_exposure: float = 0.0
    momentum_exposure: float = 0.0
    sentiment_exposure: float = 0.0

    # Sector exposures (weights)
    sector_weights: dict[str, float] = field(default_factory=dict)

    # Factor crowding (percentile vs universe)
    factor_crowding: dict[str, float] = field(default_factory=dict)

    # Correlation metrics
    average_correlation: float = 0.0  # Average position correlation
    concentration_risk: float = 0.0  # Risk from concentration

    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def net_factor_exposure(self) -> dict[str, float]:
        """Net exposure to all factors."""
        return {
            "quality": self.quality_exposure,
            "growth": self.growth_exposure,
            "value": self.value_exposure,
            "momentum": self.momentum_exposure,
            "sentiment": self.sentiment_exposure,
        }

    def is_crowded(self, factor: str, threshold: float = 0.75) -> bool:
        """Check if portfolio is crowded in a factor.

        Crowded = high percentile (most positions exposed to same factor).
        """
        crowding = self.factor_crowding.get(factor, 0.0)
        return crowding > threshold


@dataclass
class Portfolio:
    """Complete portfolio with positions and analytics."""

    positions: list[Position] = field(default_factory=list)
    metrics: PortfolioMetrics | None = None
    exposures: ExposureProfile | None = None
    benchmark_weight: dict[str, float] | None = None  # For tracking vs benchmark
    created_at: datetime = field(default_factory=datetime.now)

    @property
    def total_value(self) -> float:
        """Sum of all position values."""
        return sum(p.market_value for p in self.positions)

    @property
    def by_ticker(self) -> dict[str, Position]:
        """Positions indexed by ticker."""
        return {p.ticker: p for p in self.positions}

    @property
    def sorted_by_weight(self) -> list[Position]:
        """Positions sorted by weight descending."""
        return sorted(self.positions, key=lambda p: p.weight, reverse=True)

    @property
    def sorted_by_return(self) -> list[Position]:
        """Positions sorted by P&L % descending."""
        return sorted(self.positions, key=lambda p: p.pnl_pct, reverse=True)

    def get_position(self, ticker: str) -> Position | None:
        """Get position by ticker."""
        return self.by_ticker.get(ticker)

    def total_pnl_dollar(self) -> float:
        """Total unrealized P&L."""
        return sum(p.pnl_dollar for p in self.positions)

    def total_pnl_pct(self) -> float:
        """Total unrealized P&L %."""
        total_entry = sum(p.entry_value for p in self.positions)
        if total_entry == 0:
            return 0.0
        return (self.total_pnl_dollar() / total_entry) * 100

    def gross_exposure(self) -> float:
        """Sum of long positions."""
        return sum(p.weight for p in self.positions if p.weight > 0)

    def net_exposure(self) -> float:
        """Net long/short exposure."""
        return sum(p.weight for p in self.positions)

    def concentration_herfindahl(self) -> float:
        """Herfindahl index: sum of squared weights.

        0 = perfectly diversified
        1 = fully concentrated (one position)
        """
        return sum(w**2 for w in [p.weight for p in self.positions])

    def largest_position_weight(self) -> float:
        """Weight of largest holding."""
        if not self.positions:
            return 0.0
        return max(p.weight for p in self.positions)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict."""
        return {
            "total_value": self.total_value,
            "num_positions": len(self.positions),
            "gross_exposure": self.gross_exposure(),
            "net_exposure": self.net_exposure(),
            "concentration": self.concentration_herfindahl(),
            "largest_position": self.largest_position_weight(),
            "total_pnl_dollar": self.total_pnl_dollar(),
            "total_pnl_pct": self.total_pnl_pct(),
            "positions": [p.to_dict() for p in self.positions],
        }
