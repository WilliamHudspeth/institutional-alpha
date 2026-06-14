"""IC term structure & alpha-decay analytics.

The backtest already *measures* IC at multiple horizons (21/63/126/252d). This
module turns that raw term structure into the decisions a PM actually needs:

  - **Alpha decay & half-life.** How fast does *new* predictive power arrive as
    the horizon lengthens, and at what horizon has half of the ultimately-
    available marginal information already shown up?
  - **Optimal holding period.** Raw IC almost always *rises* with horizon
    (a longer window accumulates more signal), so "biggest IC" is a trap. The
    right objective is information *per unit of time* — IC velocity — which
    trades the signal off against the turnover/holding cost of a shorter horizon.
  - **Decay-aware horizon weighting.** If you blend signals measured at several
    horizons, weight each by its Information Ratio (consistency), not its raw IC.

Design notes / honesty:
  - Two distinct quantities are computed because they answer different questions.
    `ic_velocity(h) = mean_IC(h) / sqrt(h / 252)` is a Sharpe-like "information
    per sqrt-year" used to pick the holding period. The decay fit is run on the
    *marginal* IC (Δ IC / Δ days), which is what genuinely decays; fitting decay
    to raw cumulative IC would be wrong because raw IC trends up.
  - The half-life is only reported when the marginal IC is actually decaying.
    When IC simply accumulates with no detectable decay, we say so rather than
    inventing a number.
  - Forward-return windows overlap across horizons, so per-horizon t-stats are
    optimistic. We surface them with that caveat; the backtest's Newey-West path
    remains the rigorous SE source.

Pure numpy; consumes plain IC series so it is fully testable offline without the
price stack.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np

_TRADING_DAYS = 252.0


@dataclass(frozen=True)
class HorizonIC:
    """Per-horizon IC summary."""

    horizon_days: int
    mean_ic: float
    std_ic: float
    n_periods: int

    @property
    def information_ratio(self) -> float:
        """IR = mean(IC) / std(IC); consistency of the signal over time."""
        if self.std_ic == 0 or math.isnan(self.std_ic):
            return float("nan")
        return self.mean_ic / self.std_ic

    @property
    def t_stat(self) -> float:
        """Naive t-stat of mean IC (optimistic — windows overlap)."""
        if self.std_ic == 0 or self.n_periods < 2:
            return float("nan")
        return self.mean_ic / (self.std_ic / math.sqrt(self.n_periods))

    @property
    def ic_velocity(self) -> float:
        """Information per sqrt-year: mean_IC / sqrt(horizon_in_years).

        The objective for choosing a holding period — penalises long horizons
        for the time they tie up capital.
        """
        years = self.horizon_days / _TRADING_DAYS
        if years <= 0:
            return float("nan")
        return self.mean_ic / math.sqrt(years)


@dataclass
class ICTermStructure:
    """Full term-structure analysis."""

    horizons: list[HorizonIC]
    optimal_horizon_days: int
    recommended_rebalance_days: int
    half_life_days: float | None
    decay_tau_days: float | None
    monotonic_decay: bool
    peak_ic_horizon_days: int
    notes: list[str] = field(default_factory=list)

    def horizon_weights(self) -> dict[int, float]:
        """IR-normalised blend weights across horizons (negative IR clipped)."""
        irs = {h.horizon_days: max(0.0, h.information_ratio) for h in self.horizons}
        total = sum(v for v in irs.values() if not math.isnan(v))
        if total <= 0:
            n = len(self.horizons)
            return {h.horizon_days: 1.0 / n for h in self.horizons}
        return {k: (0.0 if math.isnan(v) else v) / total for k, v in irs.items()}

    def explain(self) -> str:
        lines = ["IC term structure:"]
        for h in self.horizons:
            lines.append(
                f"  {h.horizon_days:>4}d  IC={h.mean_ic:+.4f}  IR={h.information_ratio:+.2f}"
                f"  velocity={h.ic_velocity:+.4f}  t={h.t_stat:+.2f}"
            )
        if self.half_life_days is not None:
            lines.append(f"Alpha half-life: ~{self.half_life_days:.0f} trading days.")
        else:
            lines.append("Alpha half-life: not detected (IC accumulates with horizon).")
        lines.append(
            f"Optimal holding ~{self.optimal_horizon_days}d "
            f"(peak raw IC at {self.peak_ic_horizon_days}d); "
            f"suggested rebalance every ~{self.recommended_rebalance_days}d."
        )
        return "\n".join(lines)


def _summarise(horizon_days: int, ic: Sequence[float]) -> HorizonIC:
    arr = np.asarray([x for x in ic if x is not None and not math.isnan(x)], dtype=float)
    if arr.size == 0:
        return HorizonIC(horizon_days, float("nan"), float("nan"), 0)
    # population std matches the backtest's IR convention
    std = float(arr.std(ddof=0)) if arr.size > 1 else float("nan")
    return HorizonIC(horizon_days, float(arr.mean()), std, int(arr.size))


def fit_marginal_decay(horizons: list[HorizonIC]) -> tuple[float | None, float | None, bool]:
    """Fit exponential decay to the *marginal* IC arriving per day.

    marginal_i = (IC_i - IC_{i-1}) / (days_i - days_{i-1})

    Model marginal(d) = m0 * exp(-d / tau). Log-linear regression on the
    horizons where marginal IC is positive. Returns (tau_days, half_life_days,
    monotonic_decay). All None when fewer than two positive marginals exist or
    the slope is non-decaying.
    """
    ordered = sorted(horizons, key=lambda h: h.horizon_days)
    if len(ordered) < 3:
        return None, None, False

    mids: list[float] = []
    marg: list[float] = []
    for a, b in zip(ordered, ordered[1:]):
        dd = b.horizon_days - a.horizon_days
        if dd <= 0:
            continue
        m = (b.mean_ic - a.mean_ic) / dd
        mids.append((a.horizon_days + b.horizon_days) / 2.0)
        marg.append(m)

    monotonic = all(m >= -1e-9 for m in marg) and any(m > 0 for m in marg)

    pos = [(d, m) for d, m in zip(mids, marg) if m > 0]
    if len(pos) < 2:
        return None, None, monotonic

    d = np.array([p[0] for p in pos], dtype=float)
    y = np.log(np.array([p[1] for p in pos], dtype=float))
    slope, _ = np.polyfit(d, y, 1)
    if slope >= 0:  # marginal IC not decaying
        return None, None, monotonic

    tau = -1.0 / slope
    half_life = tau * math.log(2.0)
    return float(tau), float(half_life), monotonic


def build_term_structure(ic_by_horizon: dict[int, Sequence[float]]) -> ICTermStructure:
    """Build the full term-structure analysis from per-horizon IC series.

    Args:
        ic_by_horizon: {horizon_days: iterable of per-period IC values}. Accepts
            the raw IC time series the backtest produces per horizon. A single
            float per horizon is also accepted (treated as a 1-element series,
            in which case IR/t-stat are undefined).
    """
    if not ic_by_horizon:
        raise ValueError("ic_by_horizon is empty.")

    horizons = [
        _summarise(h, series if isinstance(series, Sequence) else [series])
        for h, series in sorted(ic_by_horizon.items())
    ]
    notes: list[str] = []

    usable = [h for h in horizons if not math.isnan(h.mean_ic)]
    if not usable:
        raise ValueError("No usable IC values across any horizon.")

    peak = max(usable, key=lambda h: h.mean_ic)
    optimal = max(usable, key=lambda h: (h.ic_velocity if not math.isnan(h.ic_velocity) else -1e9))

    tau, half_life, monotonic = fit_marginal_decay(usable)
    if half_life is None:
        notes.append("Marginal IC not decaying over the measured horizons; "
                     "no half-life — signal accumulates rather than fades.")

    # Rebalance no slower than the optimal holding period; if a half-life exists
    # and is shorter, refresh on the half-life instead (information ages out).
    rebalance = optimal.horizon_days
    if half_life is not None and half_life < rebalance:
        rebalance = int(round(half_life))
        notes.append("Rebalance tightened to the alpha half-life "
                     "(information decays faster than the optimal holding period).")

    if peak.horizon_days != optimal.horizon_days:
        notes.append(
            f"Peak raw IC is at {peak.horizon_days}d but risk-adjusted "
            f"(velocity-optimal) holding is {optimal.horizon_days}d — "
            "longer horizons buy IC at the cost of capital turnover."
        )

    return ICTermStructure(
        horizons=horizons,
        optimal_horizon_days=optimal.horizon_days,
        recommended_rebalance_days=max(1, rebalance),
        half_life_days=half_life,
        decay_tau_days=tau,
        monotonic_decay=monotonic,
        peak_ic_horizon_days=peak.horizon_days,
        notes=notes,
    )
