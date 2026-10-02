"""Thesis Drift Detection.

Monitors whether a security's *current* fundamentals still satisfy the bounds
that the active thesis was registered on. A breach degrades the verdict's
confidence band — it never silently changes a fair value.

Design choices, and why:

1. **Hard constraints, not Bayesian updates.** This is a deliberately separate
   mechanism from `iam.thesis.bayesian` (which does soft posterior updating on
   evidence). To avoid double-counting the same fact, a breach has exactly ONE
   canonical effect: it degrades the verdict band via the existing
   `iam.pipeline.verdict._downgrade_band` helper, mirroring the Damodaran-law
   and elasticity-stress hooks already in `VerdictGenerator.generate`. Feeding a
   breach into the Bayesian engine as well is possible but must be a separate,
   explicitly-labelled path — not the default.

2. **Point-in-time, not live.** `DriftDetector.evaluate` consumes an already-
   built `BusinessReality` + `Fundamentals` snapshot. It does NOT fetch. This
   keeps drift checks reproducible and lets a constraint file be hashed into
   the run `manifest.json`, exactly like the backtest config.

3. **Explicit metric registry, no magic.** The set of metrics a constraint may
   reference is a closed, documented dict (`METRIC_RESOLVERS`). Adding a metric
   is a one-line, reviewable change. A constraint naming an unknown metric
   fails loudly at load time rather than silently passing.

4. **Stdlib core.** Constraints are plain dataclasses; YAML is imported lazily
   only inside `load_constraints` so the core package keeps its numpy/pandas-
   only footprint. PyYAML is already present via `iam.config.settings`.

Registration format: one YAML file per ticker (git-diffable, manifest-hashable,
human-auditable) — see `thesis/constraints/AAPL.example.yml`.
"""

from __future__ import annotations

import operator
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------- #
# Metric registry — the closed set of things a constraint may test.
# Each resolver takes (BusinessReality | None, Fundamentals | None) and returns
# a float, or None if the data needed to evaluate it is unavailable.
# Keep this list explicit and reviewed; do not resolve arbitrary attributes.
# --------------------------------------------------------------------------- #
MetricResolver = Callable[[Any, Any], float | None]


def _safe_div(num: float | None, den: float | None) -> float | None:
    if num is None or den is None or den == 0:
        return None
    return num / den


def _ebit_ttm(f: Any) -> float | None:
    """revenue_ttm * operating_margin, or None when either input is missing/zero."""
    if not f:
        return None
    revenue = getattr(f, "revenue_ttm", None)
    margin = getattr(f, "operating_margin", None)
    if revenue and margin:
        return float(revenue * margin)
    return None


METRIC_RESOLVERS: dict[str, MetricResolver] = {
    # --- BusinessReality-sourced (all in [0,1] or [-1,1], see that module) ---
    "roic_durability": lambda br, f: getattr(br, "roic_durability", None) if br else None,
    "cashflow_durability": lambda br, f: getattr(br, "cashflow_durability", None) if br else None,
    "growth_quality": lambda br, f: getattr(br, "growth_quality", None) if br else None,
    "capital_allocation": lambda br, f: getattr(br, "capital_allocation", None) if br else None,
    "fragility": lambda br, f: getattr(br, "fragility", None) if br else None,
    "robustness": lambda br, f: getattr(br, "robustness", None) if br else None,
    # --- Fundamentals-sourced ---
    "revenue_growth_ttm": lambda br, f: getattr(f, "revenue_growth_ttm", None) if f else None,
    "operating_margin": lambda br, f: getattr(f, "operating_margin", None) if f else None,
    "debt_to_ebitda": lambda br, f: _safe_div(
        getattr(f, "total_debt", None) if f else None,
        getattr(f, "ebitda_ttm", None) if f else None,
    ),
    # raw ROIC: most-recent value from roic_history, or computed from EBIT/assets
    "roic": lambda br, f: (
        f.roic_history[0]
        if f and getattr(f, "roic_history", None)
        else _safe_div(
            getattr(f, "revenue_ttm", None)
            and getattr(f, "operating_margin", None)
            and getattr(f, "revenue_ttm") * getattr(f, "operating_margin"),
            (getattr(f, "total_debt", None) or 0)
            + (getattr(f, "cash_and_equivalents", None) or 0)
            + 1,
        )
        if f
        else None
    ),
    # reinvestment_rate = (capex + change_in_working_capital) / EBIT
    "reinvestment_rate": lambda br, f: _safe_div(
        getattr(f, "capex_ttm", None) if f else None,
        _ebit_ttm(f),
    ),
}

# Allowed comparators. The constraint passes if `op(actual, bound)` is True;
# a breach is when it is False.
_COMPARATORS: dict[str, Callable[[float, float], bool]] = {
    ">=": operator.ge,
    ">": operator.gt,
    "<=": operator.le,
    "<": operator.lt,
    "==": operator.eq,
}


@dataclass(frozen=True)
class ThesisConstraint:
    """A single registered bound the thesis depends on.

    severity is the number of confidence-band levels to degrade on breach
    (1 => HIGH->MEDIUM, 2 => HIGH->LOW). Total degradation across all breaches
    is capped at 2 by DriftReport so a verdict is never pushed below LOW.
    """

    id: str
    metric: str
    comparator: str
    bound: float
    severity: int = 1
    supports: str | None = None  # optional scenario label this bound defends
    note: str = ""

    def __post_init__(self) -> None:
        if self.metric not in METRIC_RESOLVERS:
            raise ValueError(
                f"Unknown metric '{self.metric}' in constraint '{self.id}'. "
                f"Allowed: {sorted(METRIC_RESOLVERS)}"
            )
        if self.comparator not in _COMPARATORS:
            raise ValueError(
                f"Unknown comparator '{self.comparator}' in constraint '{self.id}'. "
                f"Allowed: {sorted(_COMPARATORS)}"
            )
        if self.severity not in (1, 2):
            raise ValueError(f"severity must be 1 or 2 in constraint '{self.id}'.")


@dataclass
class ConstraintBreach:
    """A constraint that is currently violated."""

    id: str
    metric: str
    comparator: str
    bound: float
    actual: float
    severity: int
    supports: str | None
    note: str

    def describe(self) -> str:
        base = (
            f"[THESIS DRIFT] '{self.id}': {self.metric} = {self.actual:.3f} "
            f"violates {self.comparator} {self.bound:.3f}"
        )
        if self.supports:
            base += f" (undermines '{self.supports}' case)"
        if self.note:
            base += f" — {self.note}"
        return base


@dataclass
class DriftReport:
    """Aggregate drift state for one security at one point in time."""

    ticker: str
    breaches: list[ConstraintBreach] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)  # metric ids lacking data
    # "user" = the owner's own <TICKER>.yml; "example" = a shipped
    # <TICKER>.example.yml whose illustrative bounds are NOT the owner's thesis.
    source: str = "user"
    constraints_path: str | None = None

    @property
    def is_example(self) -> bool:
        return self.source == "example"

    @property
    def has_drift(self) -> bool:
        return bool(self.breaches)

    @property
    def degrade_levels(self) -> int:
        """Confidence-band levels to drop, capped at 2 (never below LOW).

        Cap rationale: matches the Bayesian-shrinkage philosophy — a single
        noisy data point should not be able to do more damage than the worst
        existing hook (Damodaran-law hard breach also caps at 2).
        """
        if self.is_example:
            # Example bounds are illustrative; they must never move the verdict.
            return 0
        return min(2, sum(b.severity for b in self.breaches))

    @property
    def conviction_drift(self) -> float:
        """Normalised 0-1 drift score (0 = no drift, 1 = maximum breach severity).

        Derived from degrade_levels / 2 so it maps cleanly onto the
        existing two-level degradation scale used by VerdictGenerator.
        """
        return self.degrade_levels / 2.0

    def notes(self) -> list[str]:
        return [b.describe() for b in self.breaches]

    @property
    def source_banner(self) -> str | None:
        """Warning shown with the report when the bounds aren't the owner's."""
        if not self.is_example:
            return None
        return (
            f"EXAMPLE THRESHOLDS, not your thesis; no effect on the verdict. "
            f"Create data/constraints/{self.ticker}.yml to register your own."
        )


def no_thesis_message(ticker: str) -> str:
    return (
        f"No thesis constraints defined for {ticker}. "
        f"Create data/constraints/{ticker}.yml to monitor drift."
    )


class DriftDetector:
    """Evaluates registered constraints against a PIT fundamentals snapshot."""

    def evaluate(
        self,
        ticker: str,
        constraints: list[ThesisConstraint],
        *,
        business_reality: Any | None = None,
        fundamentals: Any | None = None,
    ) -> DriftReport:
        report = DriftReport(ticker=ticker)
        for c in constraints:
            resolver = METRIC_RESOLVERS[c.metric]
            actual = resolver(business_reality, fundamentals)
            if actual is None:
                report.skipped.append(c.id)
                continue
            passes = _COMPARATORS[c.comparator](actual, c.bound)
            if not passes:
                report.breaches.append(
                    ConstraintBreach(
                        id=c.id,
                        metric=c.metric,
                        comparator=c.comparator,
                        bound=c.bound,
                        actual=actual,
                        severity=c.severity,
                        supports=c.supports,
                        note=c.note,
                    )
                )
        return report


# --------------------------------------------------------------------------- #
# YAML loader — lazy import keeps PyYAML out of the core import path.
# --------------------------------------------------------------------------- #
def constraints_dir() -> Path:
    """Where per-ticker constraint files live, independent of the CWD.

    ``IAM_CONSTRAINTS_DIR`` wins; otherwise the repo's ``data/constraints``
    next to the package; otherwise ``./data/constraints`` as a last resort.
    """
    import os

    env = os.environ.get("IAM_CONSTRAINTS_DIR")
    if env:
        return Path(env)
    repo = Path(__file__).resolve().parents[3] / "data" / "constraints"
    if repo.is_dir():
        return repo
    return Path("data") / "constraints"


def find_constraints(ticker: str) -> tuple[Path, str] | None:
    """Return (path, source) for a ticker's constraint file, or None.

    The owner's ``<TICKER>.yml`` is preferred; a shipped
    ``<TICKER>.example.yml`` is used only as a clearly labelled fallback.
    """
    base = constraints_dir()
    user = base / f"{ticker}.yml"
    if user.exists():
        return user, "user"
    example = base / f"{ticker}.example.yml"
    if example.exists():
        return example, "example"
    return None


def load_constraints(path: str | Path) -> tuple[str, list[ThesisConstraint]]:
    """Load a per-ticker constraint file. Returns (ticker, constraints).

    Raises on unknown metric/comparator (via ThesisConstraint.__post_init__),
    so a malformed thesis file fails at load, not silently at runtime.
    """
    try:
        import yaml  # lazy: PyYAML present via iam.config.settings
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "load_constraints requires PyYAML. It ships with the [backtest] "
            "extra; install with `pip install -e '.[backtest]'`."
        ) from exc

    data = yaml.safe_load(Path(path).read_text())
    ticker = data["ticker"]
    from iam.validation import validate_ticker

    validate_ticker(ticker)
    constraints = [
        ThesisConstraint(
            id=raw["id"],
            metric=raw["metric"],
            comparator=raw["comparator"],
            bound=float(raw["bound"]),
            severity=int(raw.get("severity", 1)),
            supports=raw.get("supports"),
            note=raw.get("note", ""),
        )
        for raw in data.get("constraints", [])
    ]
    return ticker, constraints
