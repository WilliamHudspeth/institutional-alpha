"""Portfolio UI panels for terminal rendering.

Renders:
- Portfolio holdings table
- Position-level P&L
- Factor exposure heatmap
- Risk metrics summary
- Concentration analysis
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from iam.ui.panels import BasePanel

if TYPE_CHECKING:
    from iam.ui.state import TerminalUIState


class PortfolioHoldingsPanel(BasePanel):
    """Display portfolio holdings as table."""

    def __init__(self, width: int = 80, max_rows: int = 10) -> None:
        super().__init__(width)
        self.max_rows = max_rows

    def render(self, state: TerminalUIState) -> str:
        """Render holdings table."""
        # Placeholder: requires portfolio data in state
        # This will be connected to Portfolio object
        return ""


class PortfolioMetricsPanel(BasePanel):
    """Display portfolio risk and return metrics."""

    def render(self, state: TerminalUIState) -> str:
        """Render portfolio metrics summary."""
        lines = []
        rule = "═" * self.width

        lines.append(rule)
        lines.append("║  [ PORTFOLIO METRICS SUMMARY ]".ljust(self.width - 1) + "║")
        lines.append(rule)

        # Would be populated from portfolio state
        lines.append("   [Portfolio metrics would display here]")

        return "\n".join(lines)


class FactorExposurePanel(BasePanel):
    """Display net factor exposures."""

    def render(self, state: TerminalUIState) -> str:
        """Render factor exposure analysis."""
        lines = []
        rule = "─" * self.width

        lines.append(rule)
        lines.append("FACTOR EXPOSURE PROFILE".ljust(self.width))
        lines.append(rule)

        # Would be populated from portfolio exposures
        lines.append("   [Factor exposure data would display here]")

        return "\n".join(lines)


class ConcentrationPanel(BasePanel):
    """Display concentration metrics and warnings."""

    def render(self, state: TerminalUIState) -> str:
        """Render concentration analysis."""
        lines = []

        lines.append("CONCENTRATION ANALYSIS")
        lines.append("-" * 60)

        # Would be populated from portfolio metrics
        lines.append("   [Concentration metrics would display here]")

        return "\n".join(lines)


def format_holdings_table(
    holdings: list[dict],
    max_rows: int = 15,
    width: int = 80,
) -> str:
    """Format portfolio holdings as ASCII table.

    Args:
        holdings: List of position dicts with ticker, weight, pnl_pct, etc.
        max_rows: Maximum rows to display
        width: Table width

    Returns:
        Formatted ASCII table
    """
    if not holdings:
        return "   [No holdings]"

    lines = []

    # Header
    header = f"{'Ticker':<8} {'Weight':<10} {'Market Value':<15} {'P&L %':<10} {'Conviction':<12}"
    lines.append(header)
    lines.append("-" * min(len(header), width - 4))

    # Rows
    for i, holding in enumerate(holdings[:max_rows]):
        ticker = holding.get("ticker", "—")[:7]
        weight = holding.get("weight", 0.0)
        market_value = holding.get("market_value", 0.0)
        pnl_pct = holding.get("pnl_pct", 0.0)
        conviction = holding.get("conviction", "—")

        lines.append(
            f"{ticker:<8} {weight:>8.1%}  ${market_value:>12,.0f}  "
            f"{pnl_pct:>7.1f}%  {conviction:<12}"
        )

    if len(holdings) > max_rows:
        lines.append(f"... and {len(holdings) - max_rows} more positions")

    return "\n".join("   " + line for line in lines)


def format_factor_exposure_heatmap(
    exposures: dict[str, float],
    crowding: dict[str, float],
) -> str:
    """Format factor exposures as visual heatmap.

    Args:
        exposures: Dict mapping factor -> exposure (z-score)
        crowding: Dict mapping factor -> crowding (%

    Returns:
        Formatted heatmap
    """
    lines = []

    lines.append("FACTOR EXPOSURES (z-score)")
    lines.append("-" * 50)

    for factor, exposure in exposures.items():
        crowd = crowding.get(factor, 0.0)

        # Visual bar
        if exposure > 0:
            bar = "█" * int(abs(exposure) * 10) if exposure > 0 else ""
            label = f"↑ {factor:<15}"
        else:
            bar = "█" * int(abs(exposure) * 10)
            label = f"↓ {factor:<15}"

        crowd_level = "🔴 HIGH" if crowd > 0.75 else "🟡 MOD" if crowd > 0.50 else "🟢 LOW"

        lines.append(f"  {label} {bar:<15} {exposure:>+5.2f}σ  [{crowd_level}]")

    return "\n".join(lines)


def format_concentration_warnings(portfolio_metrics: dict) -> list[str]:
    """Generate concentration warnings.

    Args:
        portfolio_metrics: Dict with concentration metrics

    Returns:
        List of warning strings
    """
    warnings = []

    largest = portfolio_metrics.get("largest_position", 0.0)
    concentration = portfolio_metrics.get("concentration", 0.0)
    num_positions = portfolio_metrics.get("num_positions", 0)

    if largest > 0.20:
        warnings.append(f"⚠️  Largest position {largest:.1%} exceeds 20% threshold")

    if concentration > 0.20:
        warnings.append(
            f"⚠️  Concentration index {concentration:.1%} (1.0 = max, {1.0 / num_positions:.1%} = equal weight)"
        )

    if num_positions < 5:
        warnings.append(f"⚠️  Portfolio has only {num_positions} positions (recommend 8+)")

    return warnings
