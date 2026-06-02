"""Typed model results for arbitration and orchestration.

ModelResult is the canonical shape that all evidence sources (DCF, multiples,
Bayesian scenarios) must produce. This ensures the arbitrator has a consistent
interface for blending disparate signals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ModelResult:
    """A single valuation signal with full provenance and uncertainty metadata.

    Every evidence source (DCF engine, multiples analyzer, Bayesian updater)
    produces one of these. The arbitrator blends them using reliability weights
    and merges provenance metadata.

    Attributes:
        name: Model identifier (e.g., "dcf_base", "multiples", "bayesian_bull")
        value: Point estimate (e.g., 0.0786 for 7.86% cost of equity)
        reliability: Confidence in this signal [0, 1]. Used for weighting.
        provenance: Dict with source, version, vintage, and stale flag
        distribution: Shape of uncertainty {"mean": X, "std": Y} or None
        meta: Additional metadata (e.g., erp_breakdown for GroundTruth)
    """

    name: str
    value: float
    reliability: float = 0.70
    provenance: dict[str, Any] = field(default_factory=dict)
    distribution: dict[str, float] | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not (0.0 <= self.reliability <= 1.0):
            raise ValueError(f"reliability must be in [0, 1], got {self.reliability}")
