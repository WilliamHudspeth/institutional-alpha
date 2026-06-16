"""Portfolio-level verdicts and recommendations.

Synthesizes individual security analysis into portfolio-level guidance:
- Portfolio construction recommendations
- Factor exposure balancing
- Risk-adjusted allocation
- Rebalancing triggers
- Factor rotation signals
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from iam.portfolio.types import Portfolio


class PortfolioVerdict(Enum):
    """High-level portfolio recommendation."""

    OVERWEIGHT = "OVERWEIGHT"  # Bullish on portfolio, increase exposure
    NEUTRAL = "NEUTRAL"  # Fair value, maintain current positioning
    UNDERWEIGHT = "UNDERWEIGHT"  # Bearish, reduce exposure
    RESTRUCTURE = "RESTRUCTURE"  # Rebalance for risk/factor balance


@dataclass
class PortfolioRecommendation:
    """Portfolio-level recommendation."""

    verdict: PortfolioVerdict
    conviction: str  # HIGH, MODERATE, LOW
    portfolio_target_return: float  # Expected return % over period
    portfolio_risk: float  # Expected volatility %
    key_drivers: list[str]  # What's driving the verdict
    actions: list[str]  # Specific recommended actions
    risks: list[str]  # Key risks to monitor
    factor_recommendations: dict[str, str]  # factor -> "OVERWEIGHT" / "NEUTRAL" / "UNDERWEIGHT"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict."""
        return {
            "verdict": self.verdict.value,
            "conviction": self.conviction,
            "expected_return": f"{self.portfolio_target_return:+.1f}%",
            "volatility": f"{self.portfolio_risk:.1f}%",
            "drivers": self.key_drivers,
            "actions": self.actions,
            "risks": self.risks,
            "factors": self.factor_recommendations,
        }


class PortfolioVerdictEngine:
    """Generate portfolio-level verdicts and recommendations."""

    @staticmethod
    def generate_verdict(
        portfolio: Portfolio,
        individual_verdicts: dict[str, str],  # ticker -> "BUY" / "HOLD" / "SELL"
        portfolio_metrics: dict[str, float],  # concentration, var, etc.
        factor_exposures: dict[str, float],  # factor -> exposure
        macro_environment: str = "neutral",  # "bullish" / "neutral" / "bearish"
    ) -> PortfolioRecommendation:
        """Generate portfolio-level recommendation.

        Args:
            portfolio: The portfolio
            individual_verdicts: Individual security verdicts
            portfolio_metrics: Risk metrics
            factor_exposures: Current factor exposures
            macro_environment: Macro outlook

        Returns:
            PortfolioRecommendation with verdict and actions
        """
        # Count verdicts
        buy_count = sum(1 for v in individual_verdicts.values() if v == "BUY")
        sell_count = sum(1 for v in individual_verdicts.values() if v == "SELL")

        total = len(individual_verdicts)
        buy_pct = buy_count / total if total > 0 else 0
        sell_pct = sell_count / total if total > 0 else 0

        # Determine portfolio verdict
        if buy_pct > 0.6 and macro_environment != "bearish":
            verdict = PortfolioVerdict.OVERWEIGHT
            conviction = "HIGH" if buy_pct > 0.75 else "MODERATE"
        elif sell_pct > 0.5:
            verdict = PortfolioVerdict.UNDERWEIGHT
            conviction = "HIGH" if sell_pct > 0.75 else "MODERATE"
        elif portfolio_metrics.get("concentration", 0) > 0.25:
            verdict = PortfolioVerdict.RESTRUCTURE
            conviction = "HIGH"
        else:
            verdict = PortfolioVerdict.NEUTRAL
            conviction = "MODERATE"

        # Estimate portfolio returns (weighted average of positions)
        position_return_estimates = []
        for position in portfolio.positions:
            if position.ticker in individual_verdicts:
                # Map verdict to expected return (simplified)
                pos_verdict = individual_verdicts[position.ticker]
                if pos_verdict == "BUY":
                    est_return = 0.15  # 15% expected return for BUYs
                elif pos_verdict == "HOLD":
                    est_return = 0.08  # 8% for HOLDs
                else:  # SELL
                    est_return = -0.05  # -5% for SELLs
                position_return_estimates.append(est_return * position.weight)

        portfolio_return = sum(position_return_estimates) if position_return_estimates else 0.08

        # Risk estimate
        portfolio_risk = portfolio_metrics.get("volatility", 0.15)

        # Generate actions
        actions = PortfolioVerdictEngine._generate_actions(
            portfolio, individual_verdicts, portfolio_metrics
        )

        # Factor recommendations
        factor_recs = PortfolioVerdictEngine._generate_factor_recommendations(factor_exposures)

        # Key drivers
        drivers = PortfolioVerdictEngine._identify_drivers(
            individual_verdicts, portfolio_metrics, macro_environment
        )

        # Risks
        risks = PortfolioVerdictEngine._identify_risks(portfolio_metrics, factor_exposures)

        return PortfolioRecommendation(
            verdict=verdict,
            conviction=conviction,
            portfolio_target_return=portfolio_return * 100,
            portfolio_risk=portfolio_risk * 100,
            key_drivers=drivers,
            actions=actions,
            risks=risks,
            factor_recommendations=factor_recs,
        )

    @staticmethod
    def _generate_actions(
        portfolio: Portfolio,
        verdicts: dict[str, str],
        metrics: dict[str, float],
    ) -> list[str]:
        """Generate specific recommended actions."""
        actions = []

        # Position sizing actions
        buy_count = sum(1 for v in verdicts.values() if v == "BUY")
        if buy_count > len(verdicts) * 0.5:
            actions.append("Shift allocations toward BUY-rated positions")

        # Concentration actions
        concentration = metrics.get("concentration", 0)
        if concentration > 0.25:
            actions.append("Reduce concentration in largest position")
            actions.append("Rebalance to improve diversification")

        largest_pos = metrics.get("largest_position", 0)
        if largest_pos > 0.20:
            actions.append("Trim position exceeding 20% threshold")

        # Rebalancing
        if metrics.get("drift", 0) > 0.02:
            actions.append("Execute quarterly rebalancing")

        # If no actions, suggest monitoring
        if not actions:
            actions.append("Monitor positions for conviction level changes")
            actions.append("Rebalance quarterly or on 2%+ drift")

        return actions

    @staticmethod
    def _generate_factor_recommendations(exposures: dict[str, float]) -> dict[str, str]:
        """Generate factor-level recommendations."""
        recs = {}

        for factor, exposure in exposures.items():
            if exposure > 0.5:
                recs[factor] = "OVERWEIGHT"
            elif exposure < -0.5:
                recs[factor] = "UNDERWEIGHT"
            else:
                recs[factor] = "NEUTRAL"

        return recs

    @staticmethod
    def _identify_drivers(
        verdicts: dict[str, str],
        metrics: dict[str, float],
        macro_env: str,
    ) -> list[str]:
        """Identify key drivers of portfolio verdict."""
        drivers = []

        buy_count = sum(1 for v in verdicts.values() if v == "BUY")
        total = len(verdicts)

        if buy_count > total * 0.5:
            drivers.append(f"Strong individual security signals ({buy_count}/{total} BUYs)")

        if metrics.get("concentration", 0) > 0.25:
            drivers.append("High concentration in core positions")

        if macro_env == "bullish":
            drivers.append("Favorable macro environment")
        elif macro_env == "bearish":
            drivers.append("Challenging macro conditions")

        if not drivers:
            drivers.append("Balanced individual security valuations")

        return drivers

    @staticmethod
    def _identify_risks(metrics: dict[str, float], exposures: dict[str, float]) -> list[str]:
        """Identify key risks to monitor."""
        risks = []

        # Concentration risk
        if metrics.get("concentration", 0) > 0.20:
            risks.append("Concentration risk: Large positions could create volatility")

        largest = metrics.get("largest_position", 0)
        if largest > 0.15:
            risks.append(f"Single position at {largest:.0%} of portfolio")

        # Factor risk
        quality_exp = exposures.get("quality", 0)
        if abs(quality_exp) > 1.5:
            risks.append(f"Extreme quality exposure {quality_exp:+.1f}σ")

        growth_exp = exposures.get("growth", 0)
        if abs(growth_exp) > 1.5:
            risks.append(f"High growth factor exposure {growth_exp:+.1f}σ")

        # Correlation risk
        avg_corr = metrics.get("avg_correlation", 0.3)
        if avg_corr > 0.6:
            risks.append(f"High correlation {avg_corr:.2f} reduces diversification")

        if not risks:
            risks.append("Well-balanced risk profile")

        return risks

    @staticmethod
    def format_recommendation(recommendation: PortfolioRecommendation) -> list[str]:
        """Format recommendation for display."""
        lines = []

        rule = "═" * 75
        lines.append(rule)
        lines.append("PORTFOLIO-LEVEL RECOMMENDATION".ljust(75))
        lines.append(rule)
        lines.append("")

        # Main verdict
        verdict_str = (
            recommendation.verdict.value
            if hasattr(recommendation.verdict, "value")
            else str(recommendation.verdict)
        )
        lines.append(f"Verdict: {verdict_str}")
        lines.append(f"Conviction: {recommendation.conviction}")
        lines.append(
            f"Target Return: {recommendation.portfolio_target_return:+.1f}% | "
            f"Expected Risk: {recommendation.portfolio_risk:.1f}%"
        )
        lines.append("")

        # Drivers
        lines.append("KEY DRIVERS:")
        for driver in recommendation.key_drivers:
            lines.append(f"  • {driver}")
        lines.append("")

        # Actions
        lines.append("RECOMMENDED ACTIONS:")
        for action in recommendation.actions:
            lines.append(f"  ➜ {action}")
        lines.append("")

        # Factor recommendations
        lines.append("FACTOR POSITIONING:")
        for factor, rec in recommendation.factor_recommendations.items():
            emoji = "↑" if rec == "OVERWEIGHT" else "↓" if rec == "UNDERWEIGHT" else "="
            lines.append(f"  {emoji} {factor:<20} {rec}")
        lines.append("")

        # Risks
        lines.append("KEY RISKS:")
        for risk in recommendation.risks:
            lines.append(f"  ⚠ {risk}")
        lines.append("")

        lines.append(rule)

        return lines
