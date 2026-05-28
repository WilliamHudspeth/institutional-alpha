"""Calibration: Convert empirical IC to reliability weights for the arbitrator.

After the backtest, write out the Information Coefficient per lens to a JSON file
that the MasterArbitrator loads at import time. This empirically grounds the
Bayesian priors.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


def ic_to_reliability(ic: float, ic_std: float = 0.0) -> float:
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
        Reliability weight in [0.5, 0.95]
    """
    # Clamp to reasonable range
    raw = 0.5 + (ic * 5.0)
    return max(0.50, min(0.95, raw))


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
        - reliability: Final reliability weight [0.5, 0.95]
        - shrinkage_factor: How much empirical data weighted (n / (n + prior_strength))
    """
    total_strength = n_obs + prior_strength

    # Posterior mean (weighted average of prior and empirical)
    posterior_ic = (prior_strength * prior_ic + n_obs * ic_mean) / total_strength

    # Posterior std (simplified: harmonic mean of uncertainties)
    posterior_std = np.sqrt((prior_strength * ic_std**2 + n_obs * ic_std**2) / (total_strength**2))

    # Convert to reliability
    reliability = max(0.50, min(0.95, 0.5 + posterior_ic * 5.0))

    # Shrinkage factor: how much weight on empirical data
    shrinkage_factor = n_obs / total_strength

    return {
        "prior_ic": prior_ic,
        "empirical_ic": ic_mean,
        "posterior_ic": posterior_ic,
        "posterior_std": posterior_std,
        "reliability": reliability,
        "shrinkage_factor": shrinkage_factor,
    }


def write_calibration(
    ic_by_lens: dict[str, float],
    output_path: Path = Path("src/iam/arbitration/calibrated_reliabilities.json"),
) -> None:
    """Write calibrated reliability weights to JSON for the arbitrator.

    Args:
        ic_by_lens: Dict mapping lens names to their empirical IC values
        output_path: Path to write calibrated_reliabilities.json
    """
    calibrated = {lens: ic_to_reliability(ic) for lens, ic in ic_by_lens.items()}

    # Add metadata
    output = {
        "version": "backtest_v0_1",
        "source": "Empirical Information Coefficient (Spearman rank)",
        "universe": "S&P 100",
        "period": "2018-01 to 2024-12",
        "horizon_days": 63,
        "note": "Only promote to production after 36+ months of out-of-sample IC",
        "reliabilities": calibrated,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"✓ Calibration written to {output_path}")
    print(f"  Lenses: {', '.join(calibrated.keys())}")
    for lens, rel in calibrated.items():
        ic = ic_by_lens[lens]
        print(f"  {lens:30} IC={ic:+.4f} → reliability={rel:.2f}")


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
