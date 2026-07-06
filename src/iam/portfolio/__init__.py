"""Portfolio composition and analytics.

Provides:
- Position and portfolio data structures
- Factor exposure analysis
- Concentration and diversification metrics
- Position sizing and rebalancing
- Risk decomposition and VaR
- Kelly criterion sizing
- Risk parity (equal risk contribution)
- Sector rotation framework
- Macro hedge recommendations

Usage:
    from iam.portfolio import Portfolio, Position, PortfolioAnalyzer

    # Create positions
    positions = [
        Position(ticker="MSFT", name="Microsoft", quantity=100, entry_price=400, current_price=450),
        Position(ticker="AAPL", name="Apple", quantity=50, entry_price=150, current_price=175),
    ]

    # Create portfolio
    portfolio = Portfolio(positions=positions)

    # Analyze
    exposures = PortfolioAnalyzer.compute_factor_exposures(portfolio, factor_scores)
    print(f"Quality exposure: {exposures.quality_exposure:+.2f}σ")
"""

from iam.portfolio.analytics import PortfolioAnalyzer
from iam.portfolio.macro_hedge import HedgeRecommendation, MacroHedgeEngine
from iam.portfolio.optimizer import (
    FactorBalancer,
    OptimizationConstraints,
    PositionSizer,
    Rebalancer,
)
from iam.portfolio.sector_rotation import SectorRotationEngine
from iam.portfolio.types import (
    ExposureProfile,
    Portfolio,
    PortfolioMetrics,
    Position,
)
from iam.portfolio.ui import (
    ConcentrationPanel,
    FactorExposurePanel,
    PortfolioHoldingsPanel,
    PortfolioMetricsPanel,
    format_concentration_warnings,
    format_factor_exposure_heatmap,
    format_holdings_table,
)
from iam.portfolio.verdicts import (
    PortfolioRecommendation,
    PortfolioVerdict,
    PortfolioVerdictEngine,
)

__all__ = [
    # Data structures
    "Position",
    "Portfolio",
    "PortfolioMetrics",
    "ExposureProfile",
    # Analytics
    "PortfolioAnalyzer",
    # Optimization
    "PositionSizer",
    "Rebalancer",
    "FactorBalancer",
    "OptimizationConstraints",
    # Sector rotation
    "SectorRotationEngine",
    # Macro hedge
    "MacroHedgeEngine",
    "HedgeRecommendation",
    # Verdicts
    "PortfolioVerdict",
    "PortfolioRecommendation",
    "PortfolioVerdictEngine",
    # UI
    "PortfolioHoldingsPanel",
    "PortfolioMetricsPanel",
    "FactorExposurePanel",
    "ConcentrationPanel",
    "format_holdings_table",
    "format_factor_exposure_heatmap",
    "format_concentration_warnings",
]
