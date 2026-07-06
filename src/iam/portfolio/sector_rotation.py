"""Sector rotation framework: regime-aware sector tilting.

Combines two signals to recommend sector over/underweight deltas:

1. **Regime-conditioned sector preference** — a lookup table of which GICS
   sectors historically outperform in each macro regime (tightening, easing,
   stagflation, neutral).  Based on the standard business-cycle sector
   rotation framework (Fidelity/BlackRock sector-cycle theory).

2. **Relative sector momentum** — trailing N-month relative return of each
   sector vs. the overall market/benchmark.

The blended tilt can be consumed by
:meth:`iam.portfolio.optimizer.FactorBalancer.suggest_sector_rotation_trades`
to generate per-ticker BUY/SELL suggestions, connecting sector rotation
directly to the existing factor-balancing pipeline.
"""

from __future__ import annotations

# ── Signal blend weights (no magic numbers) ────────────────────────────────
# Weight of the regime-conditioned preference in the final tilt.
# Regime signal dominates because sector-cycle theory has stronger
# empirical support than short-term momentum at the sector level.
REGIME_SIGNAL_WEIGHT: float = 0.6

# Weight of the relative momentum signal.
MOMENTUM_SIGNAL_WEIGHT: float = 0.4

# ── Sector tilt clamps ────────────────────────────────────────────────────
# Maximum absolute tilt for any single sector (prevents extreme rotation).
MAX_SECTOR_TILT: float = 0.08  # 8% max over/underweight

# ── Momentum threshold ────────────────────────────────────────────────────
# Minimum absolute relative momentum (decimal) to register as a signal.
# Smaller values are treated as noise.
MOMENTUM_SIGNAL_FLOOR: float = 0.005  # 0.5%

# ── Regime-conditioned sector preferences ─────────────────────────────────
# Each regime maps sector -> overweight/underweight tilt.  These reflect
# standard sector-cycle relationships documented in Fidelity's business-cycle
# sector-rotation framework and BlackRock's macro sector playbooks.
# Positive = overweight, negative = underweight.
# Only sectors with non-neutral tilts are listed.
REGIME_SECTOR_PREFERENCES: dict[str, dict[str, float]] = {
    "tightening": {
        "Financials": 0.06,
        "Energy": 0.05,
        "Materials": 0.04,
        "Industrials": 0.03,
        "Technology": -0.03,
        "Consumer Discretionary": -0.04,
        "Utilities": -0.05,
        "Real Estate": -0.04,
        "Communication Services": -0.02,
    },
    "easing": {
        "Technology": 0.06,
        "Consumer Discretionary": 0.05,
        "Real Estate": 0.04,
        "Communication Services": 0.03,
        "Financials": -0.03,
        "Energy": -0.04,
        "Utilities": -0.05,
        "Consumer Staples": -0.02,
    },
    "stagflation": {
        "Energy": 0.06,
        "Utilities": 0.05,
        "Consumer Staples": 0.04,
        "Healthcare": 0.03,
        "Materials": 0.02,
        "Financials": -0.04,
        "Technology": -0.05,
        "Consumer Discretionary": -0.05,
        "Real Estate": -0.04,
        "Communication Services": -0.02,
    },
    "neutral": {},
}


class SectorRotationEngine:
    """Recommend sector over/underweight tilts based on macro regime and
    relative momentum.

    Pure signal computation — no I/O, no mutation.  Missing or degenerate
    inputs degrade gracefully (return no tilt) rather than raising.
    """

    @staticmethod
    def recommend_sector_tilts(
        regime: str,  # "easing" / "tightening" / "stagflation" / "neutral"
        sector_momentum: dict[str, float],  # sector -> relative momentum
    ) -> dict[str, float]:
        """Compute target sector over/underweight deltas.

        Args:
            regime: Current macro regime string matching
                :attr:`MacroRegimeAssessment.regime`'s value.
            sector_momentum: Trailing relative momentum per sector
                (e.g. ``{"Technology": 0.03, "Utilities": -0.02}``).
                Positive = sector outperforming benchmark.

        Returns:
            Dict mapping sector -> tilt delta (positive = overweight,
            negative = underweight).  Empty dict when no signal is present.
        """
        # Regime-conditioned preference
        regime_tilts = REGIME_SECTOR_PREFERENCES.get(regime, {})

        if not sector_momentum and not regime_tilts:
            return {}

        # Blend: combine regime preference with momentum signal
        blended: dict[str, float] = {}

        all_sectors = set(regime_tilts.keys()) | set(sector_momentum.keys())

        for sector in all_sectors:
            regime_part = regime_tilts.get(sector, 0.0) * REGIME_SIGNAL_WEIGHT
            momentum = sector_momentum.get(sector, 0.0)
            if abs(momentum) < MOMENTUM_SIGNAL_FLOOR:
                momentum = 0.0
            momentum_part = momentum * MOMENTUM_SIGNAL_WEIGHT
            tilt = regime_part + momentum_part
            if tilt != 0.0:
                # Clamp to max tilt
                tilt = max(-MAX_SECTOR_TILT, min(MAX_SECTOR_TILT, tilt))
                blended[sector] = tilt

        return blended
