"""Factor attribution decomposition engine.

Decomposes composite alpha scores into additive contributions from each factor.
Enables institutional-grade attribution analysis showing which factors drive the signal.

Example output:
  Composite Alpha: +4.2%
  ├─ Quality: +4.2% (68% contribution)
  ├─ Capital Allocation: +2.8% (45%)
  ├─ Margin Structure: +1.5% (24%)
  ├─ Expectations Risk: -0.9% (-14%)
  └─ Macro Beta: -1.2% (-19%)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class FactorContribution:
    """Attribution of a single factor to composite score."""

    factor_name: str
    raw_score: float  # Raw factor score (e.g., z-score)
    contribution: float  # This factor's contribution to composite
    weight: float  # Weight applied to this factor
    confidence: float  # Confidence in this factor (0-1)
    direction: str  # "bullish" or "bearish"
    percentile: float  # Factor's percentile rank (0-100)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for display."""
        return {
            "factor": self.factor_name,
            "score": f"{self.raw_score:+.2f}",
            "contribution": f"{self.contribution:+.2f}%",
            "weight": f"{self.weight:.1%}",
            "confidence": f"{self.confidence:.0%}",
            "direction": self.direction.upper(),
            "percentile": f"{self.percentile:.0f}th",
        }


@dataclass
class AttributionAnalysis:
    """Complete attribution decomposition of a security."""

    ticker: str
    composite_alpha: float  # Total composite score
    total_alpha_decomposed: float  # Sum of contributions (should approximate composite)
    contributions: list[FactorContribution]  # Factor-by-factor breakdown
    residual_alpha: float  # Unexplained alpha

    @property
    def bullish_drivers(self) -> list[FactorContribution]:
        """Factors with bullish contribution."""
        return [c for c in self.contributions if c.direction == "bullish"]

    @property
    def bearish_drivers(self) -> list[FactorContribution]:
        """Factors with bearish contribution."""
        return [c for c in self.contributions if c.direction == "bearish"]

    @property
    def top_driver(self) -> FactorContribution | None:
        """Factor with largest absolute contribution."""
        if not self.contributions:
            return None
        return max(self.contributions, key=lambda x: abs(x.contribution))

    def format_summary(self) -> str:
        """Format attribution as institutional summary."""
        lines = []

        lines.append(f"Composite Alpha: {self.composite_alpha:+.2f}%")
        lines.append("")

        # Sort by absolute contribution
        sorted_contribs = sorted(
            self.contributions, key=lambda x: abs(x.contribution), reverse=True
        )

        for contrib in sorted_contribs:
            pct_of_alpha = (
                (contrib.contribution / abs(self.composite_alpha) * 100)
                if self.composite_alpha
                else 0
            )
            direction = "↑" if contrib.contribution > 0 else "↓"
            lines.append(
                f"  {direction} {contrib.factor_name:<25} {contrib.contribution:+6.2f}% "
                f"({pct_of_alpha:+5.0f}% of total)"
            )

        if self.residual_alpha != 0:
            lines.append(f"  ? Residual/Other            {self.residual_alpha:+6.2f}%")

        return "\n".join(lines)


class AttributionEngine:
    """Compute factor attribution for securities."""

    @staticmethod
    def decompose(
        ticker: str,
        factor_scores: dict[str, float],
        factor_weights: dict[str, float],
        factor_confidences: dict[str, float] | None = None,
        composite_score: float | None = None,
    ) -> AttributionAnalysis:
        """Decompose composite score into factor contributions.

        Args:
            ticker: Security identifier
            factor_scores: Raw factor z-scores
            factor_weights: Weights applied to each factor
            factor_confidences: Optional confidence scores per factor
            composite_score: Overall composite score (if None, computed from weighted factors)

        Returns:
            AttributionAnalysis with full decomposition
        """
        if factor_confidences is None:
            factor_confidences = {name: 1.0 for name in factor_scores}

        contributions = []
        total_weighted = 0.0

        # Compute each factor's contribution
        for factor_name, score in factor_scores.items():
            weight = factor_weights.get(factor_name, 0.0)
            confidence = factor_confidences.get(factor_name, 1.0)

            # Contribution = normalized score × weight × confidence
            contribution = score * weight * confidence
            total_weighted += contribution

            # Determine direction
            direction = "bullish" if contribution > 0 else "bearish"

            # Percentile (normalize z-score to percentile)
            percentile = _zscore_to_percentile(score)

            contributions.append(
                FactorContribution(
                    factor_name=factor_name,
                    raw_score=score,
                    contribution=contribution * 100,  # Convert to percentage
                    weight=weight,
                    confidence=confidence,
                    direction=direction,
                    percentile=percentile,
                )
            )

        # Use computed or provided composite
        if composite_score is None:
            composite_score = total_weighted * 100
        else:
            composite_score = composite_score * 100

        residual = composite_score - (total_weighted * 100)

        return AttributionAnalysis(
            ticker=ticker,
            composite_alpha=composite_score,
            total_alpha_decomposed=total_weighted * 100,
            contributions=contributions,
            residual_alpha=residual,
        )

    @staticmethod
    def format_for_display(analysis: AttributionAnalysis) -> list[str]:
        """Format attribution for institutional UI display."""
        lines = []

        rule = "─" * 75
        lines.append(rule)
        lines.append(f"FACTOR ATTRIBUTION ANALYSIS | {analysis.ticker}".ljust(75))
        lines.append(rule)
        lines.append("")

        lines.append(f"Composite Alpha Score: {analysis.composite_alpha:+7.2f}%")
        lines.append("")

        # Bullish drivers
        bullish = analysis.bullish_drivers
        if bullish:
            lines.append("BULLISH DRIVERS:")
            for contrib in sorted(bullish, key=lambda x: x.contribution, reverse=True):
                lines.append(
                    f"  + {contrib.factor_name:<30} {contrib.contribution:+7.2f}%  "
                    f"(confidence: {contrib.confidence:.0%}, weight: {contrib.weight:.1%})"
                )
            lines.append("")

        # Bearish drivers
        bearish = analysis.bearish_drivers
        if bearish:
            lines.append("BEARISH DRIVERS:")
            for contrib in sorted(bearish, key=lambda x: x.contribution):
                lines.append(
                    f"  − {contrib.factor_name:<30} {contrib.contribution:+7.2f}%  "
                    f"(confidence: {contrib.confidence:.0%}, weight: {contrib.weight:.1%})"
                )
            lines.append("")

        if analysis.residual_alpha != 0:
            lines.append(f"Unexplained Residual: {analysis.residual_alpha:+7.2f}%")

        lines.append(rule)

        return lines


def _zscore_to_percentile(z: float) -> float:
    """Convert z-score to percentile rank (0-100)."""
    import math

    # Use normal CDF approximation
    try:
        # Approximation of normal CDF
        if z < -6:
            return 0.0
        if z > 6:
            return 100.0

        # Abramowitz and Stegun approximation
        a1 = 0.254829592
        a2 = -0.284496736
        a3 = 1.421413741
        a4 = -1.453152027
        a5 = 1.061405429
        p = 0.3275911

        abs_z = abs(z)
        t = 1.0 / (1.0 + p * abs_z)
        y = 1.0 - (((((a5 * t + a4) * t + a3) * t + a2) * t + a1) * t) * math.exp(-(z * z) / 2.0)

        if z < 0:
            return (1.0 - y) * 100.0
        return y * 100.0
    except Exception:
        return 50.0  # Fallback to median
