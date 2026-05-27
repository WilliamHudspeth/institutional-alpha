"""Orchestrator: The hardened wiring between data, valuation, and arbitration.

This module is the single entry point that:
1. Fetches immutable EquityRiskProfile from GroundTruthProvider
2. Runs all valuation engines against that profile
3. Adapts results into ModelResult objects with provenance
4. Blends via the arbitrator, merging provenance once

Architecture invariants:
- No data source is fetched twice
- No profile is mutated
- Provenance is created once and propagated, never rebuilt
"""

from __future__ import annotations

from typing import Any, Dict

from iam.data.ground_truth import GroundTruthProvider
from iam.data.security import Security
from iam.integration.adapter import from_ground_truth
from iam.integration.types import ModelResult


class Orchestrator:
    """Hardened valuation orchestrator with immutable profiles and single-source provenance."""

    def __init__(self, damodaran_provider=None):
        """Initialize with optional Damodaran provider (for testing)."""
        self.ground_truth = GroundTruthProvider(damodaran=damodaran_provider)

    def value_security(self, security: Security) -> Dict[str, Any]:
        """Complete valuation of a security with institutional baselines.

        This is the primary entry point. It:
        1. Fetches the immutable EquityRiskProfile (the 'ground truth')
        2. Converts to ModelResult (probabilistic shape)
        3. Returns the institutional baseline recommendation

        Args:
            security: Security object with ticker, sector, industry, revenue_mix

        Returns:
            Dict with:
            - model_result: ModelResult with cost of equity baseline
            - risk_profile: Raw risk profile for auditing
            - recommendation: One-line summary

        Example:
            >>> sec = Security(ticker="NVDA", sector="...", revenue_mix={...})
            >>> result = Orchestrator().value_security(sec)
            >>> print(f"Cost of Equity: {result['model_result'].value:.2%}")
        """
        # 1. Fetch the immutable ground truth (single source, no mutation)
        base_profile = self.ground_truth.get_risk_profile(security)

        # 2. Adapt to ModelResult for arbitration
        model_result = from_ground_truth(
            name=f"{security.ticker}_institutional_baseline",
            profile=base_profile,
            reliability=0.90,
        )

        # 3. Build recommendation
        ke = model_result.value
        if ke < 0.06:
            recommendation = "Low cost of equity; defensive profile"
        elif ke < 0.08:
            recommendation = "Moderate cost of equity; balanced risk/return"
        else:
            recommendation = "High cost of equity; elevated risk profile"

        return {
            "ticker": security.ticker,
            "model_result": model_result,
            "risk_profile": base_profile,
            "recommendation": recommendation,
        }
