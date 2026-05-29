"""Diagnostic lens wrapping the Business Reality Engine.

This adapts :class:`iam.reasoning.business_reality.BusinessRealityEngine` into
the standard :class:`LensResult` shape so it plugs into the existing multi-lens
machinery (``run.py`` lens gathering, ``synthesize_lenses``).

It is a **diagnostic** lens: it sets ``fair_value_low``/``fair_value_high``/
``implied_move_pct`` to ``None`` so :func:`iam.lenses.synthesis.synthesize_lenses`
skips it when computing the weighted price target. The lens exists to surface
the durability/fragility reasoning (and to expose the structured assessment via
``assumptions``) — not to vote on fair value.
"""

from __future__ import annotations

from iam.data.security import Security
from iam.lenses.base import BaseLens, LensResult
from iam.reasoning.business_reality import BusinessRealityEngine


class BusinessRealityLens(BaseLens):
    """Surfaces Business Reality reasoning as a diagnostic lens."""

    name = "business_reality"

    def __init__(self) -> None:
        self._engine = BusinessRealityEngine()

    def compute(self, security: Security) -> LensResult:
        br = self._engine.assess(security)
        return LensResult(
            lens_name=self.name,
            fair_value_low=None,  # diagnostic only
            fair_value_high=None,
            implied_move_pct=None,
            confidence=br.confidence,
            narrative=br.narrative,
            assumptions={
                "cashflow_durability": br.cashflow_durability,
                "growth_quality": br.growth_quality,
                "capital_allocation": br.capital_allocation,
                "roic_durability": br.roic_durability,
                "fragility": br.fragility,
                "robustness": br.robustness,
            },
            notes=[*br.notes, f"revenue_quality={br.revenue_quality.value}"],
        )
