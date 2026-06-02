"""Macro regime detection and dynamic factor weighting.

Detects macroeconomic regimes and dynamically reweights factors based on environment.

Regimes:
- Inflationary: High inflation, rising rates → value, energy, commodities outperform
- Disinflationary: Falling inflation, dovish CB → growth, tech, bonds outperform
- Recessionary: Economic contraction → defensive, quality, low-volatility outperform
- Expansionary: Strong growth → cyclical, small-cap, momentum outperform
- Risk-off: Liquidity stress → flight-to-quality, bonds outperform
- Risk-on: Strong credit conditions → risky assets outperform

Dynamic reweighting example:
  Base weights: quality=1.0, growth=0.8, momentum=0.6
  Inflationary regime: quality=1.4, growth=0.5, momentum=0.3
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class MacroRegime(Enum):
    """Macroeconomic regime classification."""

    EXPANSIONARY = "expansionary"  # Strong growth, rising rates
    DISINFLATIONARY = "disinflationary"  # Falling inflation, stable/falling rates
    INFLATIONARY = "inflationary"  # Rising inflation, rising rates
    RECESSIONARY = "recessionary"  # Economic contraction
    RISK_OFF = "risk_off"  # Liquidity stress, flight to quality
    RISK_ON = "risk_on"  # Risk appetite, credit spreads tight


@dataclass
class RegimeIndicators:
    """Macro indicators used for regime detection."""

    inflation_rate: float  # YoY inflation %
    inflation_trend: str  # "rising", "stable", "falling"
    real_rates: float  # 10Y real rate %
    rate_trend: str  # "rising", "stable", "falling"
    unemployment: float  # Unemployment rate %
    gdp_growth: float  # YoY GDP growth %
    credit_spreads: float  # High-yield OAS bp (higher = risk-off)
    equity_vix: float  # VIX level (higher = risk-off)
    earnings_revisions: float  # Net revisions %
    earnings_trend: str  # "improving", "stable", "deteriorating"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict."""
        return {
            "inflation": f"{self.inflation_rate:.1f}%",
            "inflation_trend": self.inflation_trend,
            "real_rates": f"{self.real_rates:.2f}%",
            "rate_trend": self.rate_trend,
            "unemployment": f"{self.unemployment:.1f}%",
            "gdp_growth": f"{self.gdp_growth:.1f}%",
            "credit_spreads": f"{self.credit_spreads:.0f}bp",
            "vix": f"{self.equity_vix:.1f}",
            "earnings_revisions": f"{self.earnings_revisions:.1f}%",
            "earnings_trend": self.earnings_trend,
        }


@dataclass
class RegimeWeights:
    """Factor weight adjustments for a regime."""

    regime: MacroRegime
    quality_mult: float = 1.0  # Multiplier on quality weight
    growth_mult: float = 1.0  # Multiplier on growth weight
    value_mult: float = 1.0  # Multiplier on value weight
    momentum_mult: float = 1.0  # Multiplier on momentum weight
    sentiment_mult: float = 1.0  # Multiplier on sentiment weight
    capital_alloc_mult: float = 1.0  # Multiplier on capital allocation weight
    earnings_quality_mult: float = 1.0  # Multiplier on earnings quality weight
    relative_value_mult: float = 1.0  # Multiplier on relative value weight
    macro_regime_mult: float = 1.0  # Multiplier on macro regime factor

    def apply_to_weights(self, base_weights: dict[str, float]) -> dict[str, float]:
        """Apply regime adjustments to base factor weights."""
        adjusted = {}

        mapping = {
            "quality": self.quality_mult,
            "growth": self.growth_mult,
            "value": self.value_mult,
            "momentum": self.momentum_mult,
            "sentiment": self.sentiment_mult,
            "capital_allocation": self.capital_alloc_mult,
            "earnings_quality": self.earnings_quality_mult,
            "relative_value": self.relative_value_mult,
            "macro_regime": self.macro_regime_mult,
        }

        for factor_name, base_weight in base_weights.items():
            mult = mapping.get(factor_name, 1.0)
            adjusted[factor_name] = base_weight * mult

        # Renormalize so weights sum to original sum
        original_sum = sum(base_weights.values())
        adjusted_sum = sum(adjusted.values())

        if adjusted_sum > 0:
            normalization_factor = original_sum / adjusted_sum
            adjusted = {k: v * normalization_factor for k, v in adjusted.items()}

        return adjusted

    def format_summary(self) -> str:
        """Format weight adjustments for display."""
        lines = []
        lines.append(f"Regime: {self.regime.value.upper()}")
        lines.append("")

        weights = {
            "Quality": self.quality_mult,
            "Growth": self.growth_mult,
            "Value": self.value_mult,
            "Momentum": self.momentum_mult,
            "Sentiment": self.sentiment_mult,
            "Capital Allocation": self.capital_alloc_mult,
        }

        for name, mult in weights.items():
            change = (mult - 1.0) * 100
            direction = "↑" if change > 0 else "↓" if change < 0 else "="
            lines.append(f"  {direction} {name:<20} {mult:.2f}x ({change:+.0f}%)")

        return "\n".join(lines)


class RegimeDetector:
    """Detects macroeconomic regimes from indicators."""

    @staticmethod
    def detect(indicators: RegimeIndicators) -> MacroRegime:
        """Classify regime from indicators.

        Classification logic:
        1. Check if credit stressed → risk-off
        2. Check if inflation rising & rates rising → inflationary
        3. Check if inflation falling & rates falling → disinflationary
        4. Check if recession warning signs → recessionary
        5. Check if strong growth → expansionary
        6. Default to risk-on
        """
        # Risk-off if credit spreads wide or VIX elevated
        if indicators.credit_spreads > 400 or indicators.equity_vix > 25:
            return MacroRegime.RISK_OFF

        # Inflationary if inflation rising
        if (
            indicators.inflation_trend == "rising"
            and indicators.rate_trend == "rising"
            and indicators.inflation_rate > 3.0
        ):
            return MacroRegime.INFLATIONARY

        # Disinflationary if inflation falling
        if indicators.inflation_trend == "falling" and indicators.rate_trend in (
            "falling",
            "stable",
        ):
            return MacroRegime.DISINFLATIONARY

        # Recessionary if negative growth or deteriorating earnings
        if (
            indicators.gdp_growth < 0
            or indicators.unemployment > 5.5
            or indicators.earnings_trend == "deteriorating"
        ):
            return MacroRegime.RECESSIONARY

        # Expansionary if strong growth
        if (
            indicators.gdp_growth > 3.0
            and indicators.unemployment < 4.5
            and indicators.earnings_trend == "improving"
        ):
            return MacroRegime.EXPANSIONARY

        # Default: risk-on
        return MacroRegime.RISK_ON

    @staticmethod
    def get_regime_weights(regime: MacroRegime) -> RegimeWeights:
        """Get factor weight adjustments for a regime.

        Based on historical factor performance in each regime.
        """
        if regime == MacroRegime.INFLATIONARY:
            return RegimeWeights(
                regime=regime,
                quality_mult=1.4,  # Defensive
                growth_mult=0.5,  # Hurt by rates
                value_mult=1.2,  # Relative beneficiary
                momentum_mult=0.6,  # Reversions
                sentiment_mult=0.8,
                capital_alloc_mult=0.7,
                earnings_quality_mult=1.3,
                relative_value_mult=1.1,
                macro_regime_mult=1.5,  # Strong signal
            )

        elif regime == MacroRegime.DISINFLATIONARY:
            return RegimeWeights(
                regime=regime,
                quality_mult=1.0,
                growth_mult=1.5,  # Benefit from lower rates
                value_mult=0.7,  # Underperform
                momentum_mult=1.3,  # Trends extend
                sentiment_mult=1.2,
                capital_alloc_mult=1.0,
                earnings_quality_mult=1.0,
                relative_value_mult=0.8,
                macro_regime_mult=1.3,
            )

        elif regime == MacroRegime.RECESSIONARY:
            return RegimeWeights(
                regime=regime,
                quality_mult=1.6,  # Flight to quality
                growth_mult=0.4,  # Hurt badly
                value_mult=0.5,  # Value trap risk
                momentum_mult=0.3,  # Reversions
                sentiment_mult=0.2,  # Panic selling
                capital_alloc_mult=1.4,  # Conservative companies
                earnings_quality_mult=1.5,  # Earnings matter most
                relative_value_mult=0.6,  # Valuation spreads wide
                macro_regime_mult=1.8,  # Dominant signal
            )

        elif regime == MacroRegime.EXPANSIONARY:
            return RegimeWeights(
                regime=regime,
                quality_mult=0.8,  # Less defensive
                growth_mult=1.5,  # Outperform
                value_mult=0.9,  # Slight underperform
                momentum_mult=1.4,  # Trends strong
                sentiment_mult=1.3,  # Risk appetite
                capital_alloc_mult=1.0,
                earnings_quality_mult=0.9,
                relative_value_mult=1.2,
                macro_regime_mult=1.0,
            )

        elif regime == MacroRegime.RISK_OFF:
            return RegimeWeights(
                regime=regime,
                quality_mult=1.8,  # Huge premium
                growth_mult=0.3,  # Avoid
                value_mult=0.2,  # Value traps
                momentum_mult=0.1,  # Reversions strong
                sentiment_mult=0.2,  # Fear dominates
                capital_alloc_mult=1.6,  # Conservative
                earnings_quality_mult=1.7,
                relative_value_mult=0.4,
                macro_regime_mult=2.0,  # Max signal
            )

        else:  # RISK_ON
            return RegimeWeights(
                regime=regime,
                quality_mult=0.9,
                growth_mult=1.3,
                value_mult=1.1,
                momentum_mult=1.2,
                sentiment_mult=1.4,
                capital_alloc_mult=0.9,
                earnings_quality_mult=0.8,
                relative_value_mult=1.1,
                macro_regime_mult=0.7,
            )


class RegimeAnalyzer:
    """Analyze and display regime environment."""

    def __init__(self, indicators: RegimeIndicators) -> None:
        self.indicators = indicators
        self.regime = RegimeDetector.detect(indicators)
        self.weights = RegimeDetector.get_regime_weights(self.regime)

    def format_summary(self) -> list[str]:
        """Format regime analysis for display."""
        lines = []

        rule = "─" * 75
        lines.append(rule)
        lines.append(f"MACROECONOMIC REGIME ANALYSIS".ljust(75))
        lines.append(rule)
        lines.append("")

        lines.append(f"Current Regime: {self.regime.value.upper()}")
        lines.append("")

        lines.append("Key Indicators:")
        for key, value in self.indicators.to_dict().items():
            lines.append(f"  • {key.replace('_', ' ').title():<25} {value:>15}")
        lines.append("")

        lines.append("Factor Weight Adjustments:")
        for line in self.weights.format_summary().split("\n"):
            lines.append("  " + line)
        lines.append("")

        lines.append(rule)

        return lines
