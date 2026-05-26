"""Base class shared by all factors and penalties.

Every factor returns a ``FactorContribution`` with:

  - ``value``  : a normalized score, conventionally in [-1, 1] for additive
                 factors and [0, 1] for penalty factors.
  - ``confidence`` : in [0, 1] — how much data was available to compute it.
                     The composite engine uses this to soften the contribution
                     when inputs are sparse.
  - ``components`` : per-sub-component scores, for auditability.

Subclasses implement ``compute(security)``. The base class handles the
normalization and missing-data conventions.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from iam.data.security import Security


@dataclass
class FactorContribution:
    """The output of a single factor or penalty calculation."""

    name: str
    value: float                       # normalized score
    confidence: float = 1.0            # [0, 1]
    components: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def effective(self) -> float:
        """Confidence-weighted contribution."""
        return self.value * self.confidence


class Factor(ABC):
    """Base class for additive (alpha) factors.

    Convention: ``value`` is in [-1, 1] where positive is bullish.
    """

    name: str = "unnamed_factor"
    is_penalty: bool = False

    @abstractmethod
    def compute(self, security: "Security") -> FactorContribution:
        """Compute this factor for the given security.

        Implementations should:
          - Return a value in [-1, 1] (or [0, 1] for penalties).
          - Set ``confidence`` < 1.0 when input data is missing.
          - Populate ``components`` for auditability.
        """
        ...

    @staticmethod
    def clamp(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
        """Clamp a value into [lo, hi]."""
        return max(lo, min(hi, x))

    @staticmethod
    def weighted_average(parts: dict[str, tuple[float, float]]) -> float:
        """Weighted average of (value, weight) pairs, ignoring None values.

        Example:
            parts = {"a": (0.5, 0.6), "b": (0.2, 0.4)}
        """
        total_weight = 0.0
        total = 0.0
        for value, weight in parts.values():
            if value is None:
                continue
            total += value * weight
            total_weight += weight
        if total_weight == 0:
            return 0.0
        return total / total_weight


class PenaltyFactor(Factor):
    """Base class for penalty factors. Convention: ``value`` is in [0, 1]
    where higher means more penalty (subtracted from the composite)."""

    is_penalty: bool = True
