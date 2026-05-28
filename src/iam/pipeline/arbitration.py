"""Master Arbitration Layer (Consensus Engine) for resolving conflicting valuation signals."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ArbitrationResult:
    """Output of the consensus arbitration process."""

    blended_upside: float
    rating: str
    pipeline_weight_used: float
    synthesis_weight_used: float
    confidence_regime: str


class ConsensusEngine:
    """Institutional-grade arbitration layer for multi-lens valuation synthesis.

    Resolves tension between traditional DCF pipeline and multi-lens synthesis
    by dynamically weighting each based on confidence. This is how sophisticated
    quant platforms (BlackRock, Citadel) handle conflicting alpha signals.
    """

    @staticmethod
    def arbitrate_verdict(
        pipeline_upside: float,
        synthesis_upside: float | None = None,
        primary_confidence: float = 0.70,
    ) -> ArbitrationResult:
        """Blend traditional DCF pipeline with multi-lens synthesis into institutional rating.

        Args:
            pipeline_upside: The triangulated upside from Stages 1-4 (e.g., -0.382 for -38.2%)
            synthesis_upside: The weighted upside from multi-lens synthesis (e.g., +0.115 for +11.5%)
                If None, defaults to pipeline_upside (single-lens mode).
            primary_confidence: Confidence in the traditional pipeline (0.0-1.0).
                Drives the dynamic weighting scheme.

        Returns:
            ArbitrationResult with blended rating, upside, and confidence metadata.
        """
        if synthesis_upside is None:
            synthesis_upside = pipeline_upside

        # Dynamic weighting: low confidence in pipeline → lean on synthesis
        if primary_confidence < 0.60:
            pipeline_weight = 0.30
            confidence_regime = "LOW"
        elif primary_confidence < 0.80:
            pipeline_weight = 0.40
            confidence_regime = "MODERATE"
        else:
            pipeline_weight = 0.60
            confidence_regime = "HIGH"

        synthesis_weight = 1.0 - pipeline_weight

        # Blend the two signals
        blended_upside = (pipeline_upside * pipeline_weight) + (synthesis_upside * synthesis_weight)

        # Institutional Rating Tiers (based on implied move %)
        if blended_upside > 0.20:
            rating = "STRONG BUY"
        elif blended_upside > 0.10:
            rating = "BUY"
        elif blended_upside > 0.05:
            rating = "MODEST BUY"
        elif blended_upside >= -0.05:
            rating = "HOLD / NEUTRAL"
        elif blended_upside >= -0.15:
            rating = "MIXED (REDUCED EXPECTED RETURN)"
        elif blended_upside >= -0.30:
            rating = "SELL"
        else:
            rating = "HIGH RISK SELL"

        return ArbitrationResult(
            blended_upside=blended_upside,
            rating=rating,
            pipeline_weight_used=pipeline_weight,
            synthesis_weight_used=synthesis_weight,
            confidence_regime=confidence_regime,
        )
