"""Theory-first reasoning modules (Seven-Engine architecture).

These modules reason about *business reality* rather than producing fair-value
numbers. They are surfaced as diagnostic lenses and as structured inputs to
downstream conviction/drift reasoning.
"""

from iam.reasoning.business_reality import (
    BusinessReality,
    BusinessRealityEngine,
    RevenueQuality,
)

__all__ = [
    "BusinessReality",
    "BusinessRealityEngine",
    "RevenueQuality",
]
