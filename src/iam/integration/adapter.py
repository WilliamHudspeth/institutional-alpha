"""Adapters that convert deterministic ground truth into probabilistic model results.

This module bridges the immutable EquityRiskProfile from GroundTruthProvider
into ModelResult objects that the arbitrator can blend and weight.
"""

from __future__ import annotations

import math
from typing import Any, Dict

from iam.integration.types import ModelResult


def from_ground_truth(
    name: str,
    profile: Dict[str, Any],
    reliability: float = 0.85,
) -> ModelResult:
    """Convert GroundTruthProvider.get_risk_profile() output into a ModelResult.

    The GroundTruthProvider returns a dict with cost_of_equity and erp_breakdown.
    This adapter wraps it into a ModelResult with:
    - value = cost_of_equity
    - distribution derived from erp_breakdown variance
    - reliability dampened by vintage staleness

    Args:
        name: Model identifier (e.g., "ground_truth_base")
        profile: Output from GroundTruthProvider.get_risk_profile()
        reliability: Base reliability [0, 1]. Dampened by vintage.

    Returns:
        ModelResult with cost_of_equity as value and variance as distribution std.

    Example:
        >>> profile = GroundTruthProvider().get_risk_profile(security)
        >>> result = from_ground_truth("institutional_baseline", profile, reliability=0.90)
        >>> print(f"Ke: {result.value:.2%} ± {result.distribution['std']:.2%}")
    """
    # Dampen reliability if profile is stale (vintage check)
    prov = profile.get("_provenance", {})
    stale_flag = prov.get("stale", False)
    dampened_rel = reliability * (0.7 if stale_flag else 1.0)

    # Extract ERP breakdown for variance calculation
    erp_breakdown = profile.get("erp_breakdown", {})

    # Calculate variance of blended ERP from regional dispersion
    weights = [v.get("weight", 0) for v in erp_breakdown.values()]
    erps = [v.get("erp", 0) for v in erp_breakdown.values()]

    if weights and erps:
        blended_erp = sum(w * e for w, e in zip(weights, erps))
        variance = sum(w * (e - blended_erp) ** 2 for w, e in zip(weights, erps))
        erp_std = math.sqrt(variance)
    else:
        erp_std = 0.0

    # Cost of Equity std dev = erp_std * levered_beta
    levered_beta = profile.get("levered_beta", 1.0)
    ke_std = erp_std * levered_beta

    return ModelResult(
        name=name,
        value=profile.get("cost_of_equity", 0.0),
        reliability=dampened_rel,
        provenance=prov,
        distribution={
            "mean": profile.get("cost_of_equity", 0.0),
            "std": ke_std,
        },
        meta={
            "erp_breakdown": erp_breakdown,
            "levered_beta": profile.get("levered_beta", 0),
            "industry_unlevered_beta": profile.get("industry_unlevered_beta", 0),
        },
    )
