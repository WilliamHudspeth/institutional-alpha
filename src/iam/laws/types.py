"""Data contracts for the Damodaran Laws constraint layer.

These mirror the conventions of ``iam.elasticity.types`` and
``iam.valuation.types.ValuationResult``:

  * every check carries ``components`` (the sub-values that fed the
    conclusion, for audit / display) and a plain-English ``narrative``;
  * ``notes`` collects caveats raised while checking;
  * missing inputs never raise — a law that cannot be evaluated reports
    ``LawStatus.NOT_EVALUATED`` so callers can distinguish "passed" from
    "couldn't look".

The layer's job (ROADMAP, "Damodaran Laws — Theory-First Consistency
Checks") is to *flag fragile analyses*, not to invent numbers. A FLAG means
"this combination of assumptions needs an explanation"; a VIOLATION means
"this combination is internally inconsistent with valuation theory".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

# --- Conviction-degradation constants (documented; no silent magic numbers) --

# How much each non-pass check erodes conviction. Violations are first-class
# theory breaks; flags are "needs explanation" and cost a third as much.
VIOLATION_PENALTY = 0.15
FLAG_PENALTY = 0.05
# Floor on the multiplier: even a maximally flagged analysis keeps half its
# conviction — the laws temper a verdict, they do not veto it.
MIN_CONVICTION_MULTIPLIER = 0.50


class LawStatus(str, Enum):
    """Outcome of a single law check."""

    PASS = "pass"
    FLAG = "flag"  # assumptions need an explanation
    VIOLATION = "violation"  # assumptions are internally inconsistent
    NOT_EVALUATED = "not_evaluated"  # inputs too sparse to check


@dataclass
class LawCheck:
    """The result of evaluating one Damodaran law against an analysis."""

    number: int  # 1..5
    name: str  # short snake_case identifier, e.g. "growth_requires_reinvestment"
    status: LawStatus
    narrative: str = ""
    components: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


@dataclass
class LawReport:
    """Aggregate output of :meth:`DamodaranLawRegistry.evaluate`.

    ``conviction_multiplier`` is the hook the verdict layer consumes: it maps
    the count of flags/violations onto a [MIN_CONVICTION_MULTIPLIER, 1.0]
    multiplier that degrades the final confidence band.
    """

    checks: list[LawCheck] = field(default_factory=list)

    @property
    def passes(self) -> list[LawCheck]:
        return [c for c in self.checks if c.status is LawStatus.PASS]

    @property
    def flags(self) -> list[LawCheck]:
        return [c for c in self.checks if c.status is LawStatus.FLAG]

    @property
    def violations(self) -> list[LawCheck]:
        return [c for c in self.checks if c.status is LawStatus.VIOLATION]

    @property
    def not_evaluated(self) -> list[LawCheck]:
        return [c for c in self.checks if c.status is LawStatus.NOT_EVALUATED]

    @property
    def conviction_multiplier(self) -> float:
        """1.0 for a clean report, eroded per flag/violation, floored."""
        multiplier = 1.0 - VIOLATION_PENALTY * len(self.violations) - FLAG_PENALTY * len(self.flags)
        return max(MIN_CONVICTION_MULTIPLIER, multiplier)

    @property
    def narrative(self) -> str:
        """One-line summary for report output."""
        n_checked = len(self.checks) - len(self.not_evaluated)
        if n_checked == 0:
            return "Damodaran laws: insufficient data to evaluate any law."
        parts = [f"{len(self.passes)}/{n_checked} laws pass"]
        if self.violations:
            names = ", ".join(f"LAW {c.number} ({c.name})" for c in self.violations)
            parts.append(f"VIOLATED: {names}")
        if self.flags:
            names = ", ".join(f"LAW {c.number} ({c.name})" for c in self.flags)
            parts.append(f"flagged: {names}")
        if self.not_evaluated:
            parts.append(f"{len(self.not_evaluated)} not evaluable")
        return "Damodaran laws: " + "; ".join(parts) + "."
