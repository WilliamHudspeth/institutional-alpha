"""Durability + Elasticity Scoring Layer (v0.5 Engine #6).

This package is the foundation of the platform's *theory-first stress testing*
direction. The existing macro overlay (``iam.pipeline.macro``) applies uniform
rate/growth shocks and gates on the size of the move. It does not reason about
*why* a specific business is fragile. This layer fixes that.

The theory (see ROADMAP.md, "The Core Enhancement: Theory-First Stress
Testing"):

  * **Durability** (0..1) — what fraction of cash flows persist if growth
    stalls? Recurring, sticky revenue is durable; transactional/cyclical
    revenue is not.
  * **Growth elasticity** (0..2) — how hard does FCFE contract when growth
    drops? Fixed-cost-heavy businesses have high operating leverage, so their
    cash flows collapse faster than revenue. (Damodaran's "operating
    leverage"; Mauboussin's "reflexivity".)
  * **Rate elasticity** (0..3) — how much does value swing per 50bps rate
    move? Long-duration cash flows are rate-sensitive; short-lived flows are
    not.

The ``DurabilityStressEngine`` combines these three response functions to
*re-price* a valuation under a named stress scenario and estimate how far
conviction should drift.

Status: fully implemented and wired into the pipeline. The macro overlay
(``iam.pipeline.macro.MacroOverlay``) scales raw macro shocks by the measured
rate/growth elasticity before gating and re-pricing, and attaches the
resulting :class:`StressResponse` (including conviction drift) to the
``PipelineReport`` for the Stage 7 verdict. ``tests/test_elasticity.py``
encodes each method's spec as assertions; do not change the public type
signatures without updating the tests.
"""

from __future__ import annotations

from iam.elasticity.durability import DurabilityScorer
from iam.elasticity.elasticity import ElasticityScorer
from iam.elasticity.stress import DurabilityStressEngine
from iam.elasticity.types import (
    DurabilityScore,
    ElasticityProfile,
    StressResponse,
    StressScenario,
)

__all__ = [
    "DurabilityScore",
    "ElasticityProfile",
    "StressScenario",
    "StressResponse",
    "DurabilityScorer",
    "ElasticityScorer",
    "DurabilityStressEngine",
]
