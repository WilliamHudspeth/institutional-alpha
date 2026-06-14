"""Stage 4b: Valuation Battlefield — disagreement *attribution*.

The Triangulator (Stage 4) already decides whether the lenses agree
(AGREE / TWO_OF_THREE / DISAGREE) by collapsing each lens to a single
`fair_value_to_price` ratio. That collapse is exactly what makes it unable
to say *why* they disagree.

This module does not re-decide agreement. It consumes the upstream assumption
sets — the market-implied parameter vector (reverse DCF / MarketImpliedEngine)
and the intrinsic parameter vector (FCFE DCF) — and answers a different
question: **if the two lenses disagree, which single assumption explains most
of the gap?** Growth, discount rate (risk), terminal growth, or quality (ROE/
ROIC)?

Method: ceteris-paribus sensitivity. Start from the intrinsic parameter
vector, swap exactly one parameter to its market-implied value, hold the rest
fixed, and revalue. The parameter whose swap moves value the most is the key
disagreement.

Honesty note: because the value model is non-linear, the per-parameter deltas
do NOT additively reconstruct the full gap. We therefore report the argmax as
the headline driver and the normalised |delta| only as colour ("~60% of the
disagreement is about growth"), never as an exact decomposition. This is the
same discipline the repo already applies elsewhere (reverse_dcf_to_ratio is
"an approximation but a defensible one").

Wiring: `build_battlefield` is the orchestrator entry point. It is decoupled
from any concrete engine via an injected `value_fn`; pass a closure over
`FCFEDCF` for production, or rely on the bundled `two_stage_fcfe_value` for
unit tests. Keep this module consistent with Triangulation: a regression test
should assert the battlefield never reports a "key disagreement" when the
TriangulationResult.verdict == "agree".
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace

from iam.valuation.types import ImpliedExpectations, TriangulationResult, ValuationResult

# The common parameter space shared by the reverse-DCF (market-implied) and
# FCFE-DCF (intrinsic) lenses. These are the only levers the intrinsic engine
# actually exposes, so they are the only honest axes for attribution.
#
# Mapping note on "margin": the FCFE engine has no standalone operating-margin
# lever — margin quality enters through ROE/ROIC (the reinvestment / ERR term).
# We therefore fold "margin fade" into the `roe` channel rather than invent a
# parameter the model does not have. ImpliedExpectations.implied_operating_margin
# is surfaced in the notes for the analyst but is not a swap axis.
_PARAMS = ("growth", "terminal_growth", "discount_rate", "roe")

# Human-readable disagreement labels keyed by the dominant parameter.
_LABELS = {
    "growth": "GROWTH expectations",
    "terminal_growth": "TERMINAL GROWTH / fade",
    "discount_rate": "DISCOUNT RATE (risk)",
    "roe": "QUALITY (ROE/ROIC reinvestment)",
}


@dataclass(frozen=True)
class ParamVector:
    """A point in the shared valuation parameter space.

    All fields optional so a lens that didn't populate one (e.g. reverse DCF
    that left implied_roic=None) is skipped from attribution rather than faked.
    """

    growth: float | None = None
    terminal_growth: float | None = None
    discount_rate: float | None = None
    roe: float | None = None


@dataclass
class DriverContribution:
    """One parameter's ceteris-paribus contribution to the disagreement."""

    parameter: str
    value_intrinsic: float
    value_market: float
    value_if_swapped: float  # intrinsic vector with ONLY this param := market
    delta_value: float  # signed: value_if_swapped - base_value
    share: float = 0.0  # |delta| / Σ|delta| across swappable params


@dataclass
class BattlefieldAttribution:
    """The Battlefield's structured output, fed into the verdict synthesis."""

    key_disagreement: str  # _LABELS value, or "NONE — lenses agree"
    key_parameter: str | None  # raw param name, or None
    base_value: float  # intrinsic value
    target_value: float  # market-implied value (≈ current price by construction)
    total_gap: float  # target - base (signed)
    contributions: list[DriverContribution] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Mappers: turn the existing engine outputs into the shared ParamVector
# --------------------------------------------------------------------------- #
def market_vector_from_implied(implied: ImpliedExpectations) -> ParamVector:
    """Project a reverse-DCF ImpliedExpectations onto the shared space.

    implied_roic is mapped onto the `roe` axis (both drive the reinvestment
    constraint in the two-stage FCFE engine); they are not identical, which is
    documented and acceptable for *ranking* the dominant driver.
    """
    return ParamVector(
        growth=implied.implied_revenue_growth,
        terminal_growth=implied.implied_terminal_growth,
        discount_rate=implied.discount_rate_assumed,
        roe=implied.implied_roic,
    )


def intrinsic_vector_from_assumptions(assumptions: dict[str, float]) -> ParamVector:
    """Project an intrinsic ValuationResult.assumptions dict onto the space.

    Accepts the key names the FCFE lens already writes; falls back across a
    couple of common aliases so this is robust to minor upstream naming.
    """

    def pick(*keys: str) -> float | None:
        for k in keys:
            if k in assumptions and assumptions[k] is not None:
                return float(assumptions[k])
        return None

    return ParamVector(
        growth=pick("high_growth", "forecast_growth", "growth"),
        terminal_growth=pick("terminal_growth", "forecast_terminal_growth"),
        discount_rate=pick("discount_rate", "forecast_discount_rate", "wacc"),
        roe=pick("roe", "roic"),
    )


# --------------------------------------------------------------------------- #
# Core attribution
# --------------------------------------------------------------------------- #
def attribute_disagreement(
    intrinsic: ParamVector,
    market: ParamVector,
    value_fn: Callable[[ParamVector], float],
    *,
    triangulation: TriangulationResult | None = None,
    agree_short_circuit: bool = True,
) -> BattlefieldAttribution:
    """Identify which single assumption explains most of the value gap.

    Args:
        intrinsic: the bottom-up assumption vector (the "fair value" lens).
        market:    the market-implied assumption vector (reverse DCF).
        value_fn:  revalues a ParamVector -> equity value per share. Inject a
                   closure over FCFEDCF in production; see two_stage_fcfe_value
                   for a test-friendly default.
        triangulation: optional Stage-4 result. If provided and verdict ==
                   "agree", we short-circuit so the Battlefield can never
                   contradict the Triangulator (see module docstring).
    """
    notes: list[str] = []

    if agree_short_circuit and triangulation is not None and triangulation.verdict == "agree":
        return BattlefieldAttribution(
            key_disagreement="NONE — lenses agree",
            key_parameter=None,
            base_value=value_fn(intrinsic),
            target_value=value_fn(intrinsic),
            total_gap=0.0,
            notes=["Triangulation verdict is AGREE; no disagreement to attribute."],
        )

    base_value = value_fn(intrinsic)
    target_value = value_fn(market)
    total_gap = target_value - base_value

    contributions: list[DriverContribution] = []
    for name in _PARAMS:
        iv = getattr(intrinsic, name)
        mv = getattr(market, name)
        if iv is None or mv is None:
            notes.append(
                f"Skipped '{name}': missing on {'intrinsic' if iv is None else 'market'} lens."
            )
            continue
        swapped = replace(intrinsic, **{name: mv})
        v_swapped = value_fn(swapped)
        contributions.append(
            DriverContribution(
                parameter=name,
                value_intrinsic=iv,
                value_market=mv,
                value_if_swapped=v_swapped,
                delta_value=v_swapped - base_value,
            )
        )

    if not contributions:
        return BattlefieldAttribution(
            key_disagreement="UNDETERMINED — no shared parameters",
            key_parameter=None,
            base_value=base_value,
            target_value=target_value,
            total_gap=total_gap,
            notes=notes or ["No overlapping parameters between the two lenses."],
        )

    denom = sum(abs(c.delta_value) for c in contributions) or 1.0
    for c in contributions:
        c.share = abs(c.delta_value) / denom

    winner = max(contributions, key=lambda c: abs(c.delta_value))
    contributions.sort(key=lambda c: abs(c.delta_value), reverse=True)

    notes.append(
        f"Key disagreement: {_LABELS[winner.parameter]} "
        f"(intrinsic {winner.value_intrinsic:.3f} vs market-implied {winner.value_market:.3f}); "
        f"explains ~{winner.share:.0%} of cross-parameter sensitivity."
    )
    notes.append(
        "Shares are ceteris-paribus sensitivities and do not additively "
        "reconstruct the gap (model is non-linear); use as colour, not a decomposition."
    )

    return BattlefieldAttribution(
        key_disagreement=_LABELS[winner.parameter],
        key_parameter=winner.parameter,
        base_value=base_value,
        target_value=target_value,
        total_gap=total_gap,
        contributions=contributions,
        notes=notes,
    )


# --------------------------------------------------------------------------- #
# Orchestrator entry point
# --------------------------------------------------------------------------- #
def build_battlefield(
    *,
    market_implied: ValuationResult,
    intrinsic: ValuationResult,
    value_fn: Callable[[ParamVector], float],
    triangulation: TriangulationResult | None = None,
) -> BattlefieldAttribution:
    """Adapter the orchestrator calls: pulls vectors off real engine outputs.

    `market_implied` must carry a populated `.implied` (ImpliedExpectations);
    `intrinsic` must carry a populated `.assumptions` dict. Both are already
    produced by the existing pipeline stages — this module adds no new fetch.
    """
    if market_implied.implied is None:
        return BattlefieldAttribution(
            key_disagreement="UNDETERMINED — reverse DCF produced no implied set",
            key_parameter=None,
            base_value=0.0,
            target_value=0.0,
            total_gap=0.0,
            notes=["market_implied.implied is None."],
        )

    market_vec = market_vector_from_implied(market_implied.implied)
    intrinsic_vec = intrinsic_vector_from_assumptions(intrinsic.assumptions)
    return attribute_disagreement(intrinsic_vec, market_vec, value_fn, triangulation=triangulation)


# --------------------------------------------------------------------------- #
# Test-friendly default value function (compact two-stage FCFE)
# --------------------------------------------------------------------------- #
def two_stage_fcfe_value(
    p: ParamVector,
    *,
    base_cashflow: float = 1.0,
    high_growth_years: int = 10,
) -> float:
    """A faithful-but-compact stand-in for FCFEDCF, for unit tests.

    Mirrors the repo's two-stage Gordon structure with an ERR (equity
    reinvestment rate) constraint via ROE, so swapping `roe` actually moves
    value the way the production engine would. In production, inject a closure
    over the real FCFEDCF instead of this.
    """
    g = p.growth if p.growth is not None else 0.0
    gt = p.terminal_growth if p.terminal_growth is not None else 0.025
    r = p.discount_rate if p.discount_rate is not None else 0.09
    roe = p.roe if p.roe is not None else 0.15
    if r <= gt:  # convergence guard, matches reverse_dcf
        return float("nan")

    pv = 0.0
    cf = base_cashflow
    for t in range(1, high_growth_years + 1):
        cf *= 1 + g
        pv += cf / ((1 + r) ** t)

    # Terminal value with reinvestment drag: payout = 1 - gt/roe (ERR capped).
    err = min(gt / roe, 1.0) if roe > 0 else 1.0
    cf_terminal = cf * (1 + gt) * (1 - err)
    tv = cf_terminal / (r - gt)
    pv += tv / ((1 + r) ** high_growth_years)
    return pv
