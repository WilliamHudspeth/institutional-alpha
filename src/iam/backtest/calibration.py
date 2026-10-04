"""Calibration: Convert empirical IC to reliability weights for the arbitrator.

After the backtest, write out the Information Coefficient per lens to a JSON file
that the MasterArbitrator loads at import time. This empirically grounds the
Bayesian priors.

Convention for an unmeasured calibration: the reliability is ``None`` (never a
clamped default). ``ic_to_reliability_bayesian`` also returns a ``reason``.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# Minimum number of monthly IC observations before a reliability may be derived.
# 36 months (3 years) matches the Bayesian prior_strength below and the "36+ months
# of out-of-sample IC" promotion note in write_calibration(): below that, the IC
# mean is dominated by sampling noise and no reliability is reported at all.
MIN_CALIBRATION_OBS = 36

# Reliability bounds shared with the arbitrator: 0.50 = no information, 0.95 caps
# overconfidence. Applied to finite values only.
RELIABILITY_FLOOR = 0.50
RELIABILITY_CAP = 0.95


def _is_finite_number(x: Any) -> bool:
    """True for real, finite numbers (bool excluded)."""
    if isinstance(x, bool):
        return False
    try:
        return math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


def ic_to_reliability(ic: float, ic_std: float = 0.0) -> float | None:
    """Convert Information Coefficient to reliability [0.5, 0.95].

    Formula: reliability = 0.5 + clamp(ic * 5, -0.5, 0.45)

    Clipping prevents overconfidence:
    - IC = 0.0 → reliability = 0.50 (baseline, no signal)
    - IC = 0.05 → reliability = 0.75 (moderate signal)
    - IC = 0.10 → reliability = 1.00 (clamped to 0.95 to avoid overfit)

    Args:
        ic: Information Coefficient (Spearman rank correlation)
        ic_std: Standard deviation of IC (for uncertainty, optional)

    Returns:
        Reliability weight in [0.5, 0.95], or None when ``ic`` or ``ic_std`` is not
        finite (NaN/inf): an unmeasured IC has no reliability. Python's
        ``min(0.95, nan)`` would otherwise return 0.95.
    """
    if not _is_finite_number(ic) or not _is_finite_number(ic_std):
        return None
    raw = 0.5 + (ic * 5.0)
    return max(RELIABILITY_FLOOR, min(RELIABILITY_CAP, raw))


def ic_to_reliability_bayesian(
    ic_mean: float,
    ic_std: float,
    n_obs: int,
    prior_ic: float = 0.02,
    prior_strength: int = 36,  # 3 years of monthly IC
) -> dict:
    """Convert IC to reliability using Bayesian shrinkage toward a neutral prior.

    Posterior IC = (prior_strength * prior_ic + n_obs * empirical_ic) / (prior_strength + n_obs)

    This regularizes empirical IC toward a conservative prior, preventing overfitting
    on short-history backtests. After 36 months, prior and empirical have equal weight.

    Args:
        ic_mean: Empirical mean IC
        ic_std: Empirical std dev of IC
        n_obs: Number of observations (months)
        prior_ic: Prior belief about IC (default 0.02, conservative)
        prior_strength: Prior strength in months (default 36 = 3 years)

    Returns:
        Dict with:
        - prior_ic: Prior assumption
        - empirical_ic: Observed IC
        - posterior_ic: Bayesian posterior after shrinkage
        - posterior_std: Posterior uncertainty
        - reliability: Final reliability weight [0.5, 0.95], or None if unmeasured
        - shrinkage_factor: How much empirical data weighted (n / (n + prior_strength))
        - reason: None when a reliability was derived, else why it is None

    Reliability is None (with a reason) when ic_mean/ic_std is not finite (the
    posterior values are then None too) or when n_obs < MIN_CALIBRATION_OBS (the
    shrunk posterior is still reported, but is not promoted to a reliability).
    """
    total_strength = n_obs + prior_strength
    shrinkage_factor = n_obs / total_strength

    if not _is_finite_number(ic_mean) or not _is_finite_number(ic_std):
        return {
            "prior_ic": prior_ic,
            "empirical_ic": None,
            "posterior_ic": None,
            "posterior_std": None,
            "reliability": None,
            "shrinkage_factor": shrinkage_factor,
            "reason": "empirical IC mean/std is not finite (NaN or inf): nothing was measured",
        }

    # Posterior mean (weighted average of prior and empirical)
    posterior_ic = (prior_strength * prior_ic + n_obs * ic_mean) / total_strength

    # Posterior std (simplified: harmonic mean of uncertainties)
    posterior_std = np.sqrt((prior_strength * ic_std**2 + n_obs * ic_std**2) / (total_strength**2))

    # Convert to reliability (only finite values reach this point)
    reason = None
    reliability: float | None = max(
        RELIABILITY_FLOOR, min(RELIABILITY_CAP, 0.5 + posterior_ic * 5.0)
    )
    if n_obs < MIN_CALIBRATION_OBS:
        reliability = None
        reason = (
            f"only {n_obs} IC observations; at least {MIN_CALIBRATION_OBS} "
            "are required to derive a reliability"
        )

    return {
        "prior_ic": prior_ic,
        "empirical_ic": ic_mean,
        "posterior_ic": posterior_ic,
        "posterior_std": posterior_std,
        "reliability": reliability,
        "shrinkage_factor": shrinkage_factor,
        "reason": reason,
    }


def _json_safe(value: Any) -> Any:
    """Recursively convert numpy scalars to Python and NaN/inf to None."""
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_json_safe(v) for v in value]
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def build_empirical_calibration_record(
    *,
    ic_mean: float,
    ic_std: float,
    n_obs: int,
    version: str,
    timestamp: str,
    git_sha: str,
    period: str,
    horizon_days: int,
) -> dict:
    """Build the calibrated_reliabilities_empirical.json record.

    data_source is "empirical" only when a reliability was actually derived;
    otherwise "insufficient_data" with a reason and a null reliability.
    """
    calibration = ic_to_reliability_bayesian(ic_mean, ic_std, n_obs)
    reason = calibration["reason"]
    meta: dict[str, Any] = {
        "version": version,
        "data_source": "empirical" if reason is None else "insufficient_data",
        "timestamp": timestamp,
        "git_sha": git_sha,
    }
    if reason is not None:
        meta["reason"] = reason
    return {
        "_meta": meta,
        "source": "Real S&P 100 price data via yfinance → Stooq fallback",
        "universe": "S&P 100 (static 2024-12-31)",
        "period": period,
        "horizon_days": horizon_days,
        "signal": "composite",
        "empirical_ic": {"mean": ic_mean, "std": ic_std, "n_obs": n_obs},
        "bayesian_calibration": {
            "prior_ic": calibration["prior_ic"],
            "posterior_ic": calibration["posterior_ic"],
            "posterior_std": calibration["posterior_std"],
            "shrinkage_factor": calibration["shrinkage_factor"],
            "reliability": calibration["reliability"],
        },
    }


def serialize_calibration_record(record: dict) -> str:
    """Serialize to strict JSON: NaN/inf become null; allow_nan=False proves it."""
    return json.dumps(_json_safe(record), indent=2, allow_nan=False)


def write_calibration(
    ic_by_lens: dict[str, float],
    output_path: Path = Path("src/iam/arbitration/calibrated_reliabilities.json"),
) -> None:
    """Write calibrated reliability weights to JSON for the arbitrator.

    Lenses whose IC is not finite get no reliability entry (listed under
    ``unmeasured_lenses``); the file is always strict JSON.

    Args:
        ic_by_lens: Dict mapping lens names to their empirical IC values
        output_path: Path to write calibrated_reliabilities.json
    """
    calibrated = {
        lens: rel for lens, ic in ic_by_lens.items() if (rel := ic_to_reliability(ic)) is not None
    }
    unmeasured = [lens for lens in ic_by_lens if lens not in calibrated]

    # Add metadata
    output = {
        "version": "backtest_v0_1",
        "source": "Empirical Information Coefficient (Spearman rank)",
        "universe": "S&P 100",
        "period": "2018-01 to 2024-12",
        "horizon_days": 63,
        "note": "Only promote to production after 36+ months of out-of-sample IC",
        "reliabilities": calibrated,
        "unmeasured_lenses": unmeasured,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        f.write(serialize_calibration_record(output))

    print(f"✓ Calibration written to {output_path}")
    print(f"  Lenses: {', '.join(ic_by_lens.keys())}")
    for lens, ic in ic_by_lens.items():
        rel = calibrated.get(lens)
        rel_txt = f"{rel:.2f}" if rel is not None else "n/a (IC not measured)"
        print(f"  {lens:30} IC={ic:+.4f} → reliability={rel_txt}")


def summarize_backtest(results_df: pd.DataFrame) -> dict[str, float]:
    """Summarize backtest results into key metrics.

    Args:
        results_df: DataFrame with columns 'date', 'ic', 'spread', 'hit_rate', etc.

    Returns:
        Dict with summary metrics
    """
    ic_mean = results_df["ic"].mean()
    ic_std = results_df["ic"].std()
    ic_ir = ic_mean / ic_std if ic_std > 0 else 0.0

    return {
        "ic_mean": ic_mean,
        "ic_std": ic_std,
        "icir": ic_ir,
        "hit_rate": results_df.get("hit_rate", pd.Series()).mean(),
        "spread_mean": results_df.get("spread", pd.Series()).mean(),
        "top_decile_mean": results_df.get("top", pd.Series()).mean(),
        "bottom_decile_mean": results_df.get("bottom", pd.Series()).mean(),
    }
