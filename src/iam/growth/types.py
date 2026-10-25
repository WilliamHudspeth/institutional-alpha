"""Data structures for growth estimates, valuation assignments, and profiles.

Each valuation type (DCF, relative multiples, expectations) receives its own
growth rate and uncertainty quantification, following Damodaran (*Investment
Valuation* ch. 11), Mauboussin, Callahan and Majd (*The Base Rate Book*, 2016),
and Chan, Karceski and Lakonishok ("The Level and Persistence of Growth Rates",
JF 2003).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class GrowthEstimate:
    """Single-method growth rate estimate and its standard error."""

    method: str
    value: float | None
    std_error: float | None
    horizon_years: int
    confidence: float
    inputs: dict[str, float] = field(default_factory=dict)
    reason: str | None = None
    notes: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        """Return True when the estimate produced a usable growth value."""
        return self.value is not None


@dataclass(frozen=True)
class GrowthAssignment:
    """Precision-weighted and base-rate-shrunk growth assigned to a valuation."""

    valuation: str
    value: float | None
    std_error: float | None
    sources: tuple[str, ...]
    weights: dict[str, float]
    shrinkage_weight: float | None
    base_rate: float | None
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class GrowthProfile:
    """Complete growth profile separating DCF, relative, and implied rates."""

    estimates: dict[str, GrowthEstimate]
    dcf: GrowthAssignment
    dcf_path: tuple[float, ...]
    terminal_growth: float
    relative_revenue: GrowthAssignment
    relative_eps: GrowthAssignment
    expectations: GrowthAssignment
    expectations_gap: float | None
    expectations_percentile: float | None

    def summary(self) -> str:
        """Return a one-line-per-valuation summary of rates and their sources."""

        def _fmt(val: float | None) -> str:
            return f"{val * 100:.2f}%" if val is not None else "n/a"

        def _src(sources: tuple[str, ...]) -> str:
            return ", ".join(sources) if sources else "base_rate"

        def _ordinal(n: int) -> str:
            if 10 <= (n % 100) <= 20:
                suffix = "th"
            else:
                suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
            return f"{n}{suffix}"

        dcf_line = (
            f"DCF: {_fmt(self.dcf.value)} -> terminal {_fmt(self.terminal_growth)} "
            f"(sources: {_src(self.dcf.sources)})"
        )
        rel_line = (
            f"Relative: revenue g={_fmt(self.relative_revenue.value)} "
            f"(sources: {_src(self.relative_revenue.sources)}), "
            f"EPS gEPS={_fmt(self.relative_eps.value)} "
            f"(sources: {_src(self.relative_eps.sources)})"
        )
        exp_src = ", ".join(self.expectations.sources) if self.expectations.sources else "none"
        exp_line = f"Expectations: {_fmt(self.expectations.value)} (sources: {exp_src})"
        if self.expectations.value is not None and (
            self.expectations_percentile is not None or self.expectations_gap is not None
        ):
            details: list[str] = []
            if self.expectations_percentile is not None:
                pct = round(self.expectations_percentile * 100)
                details.append(f"{_ordinal(pct)} percentile of the base rate")
            if self.expectations_gap is not None:
                pts = abs(self.expectations_gap) * 100
                direction = "above" if self.expectations_gap >= 0 else "below"
                details.append(f"{pts:.1f} points {direction} the DCF rate")
            exp_line += (
                f" — market implies {self.expectations.value * 100:.1f}% " f"({'; '.join(details)})"
            )
        return "\n".join((dcf_line, rel_line, exp_line))
