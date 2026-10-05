"""Safe loader for calibrated reliability weights.

This module ensures that:
1. Synthetic calibrations are never used in production
2. Empirical calibrations are clearly marked
3. Fallback defaults are used when calibration is unavailable/invalid
4. All loading is logged for audit purposes

Key principle: Synthetic (architectural validation) != Empirical (real backtest)
"""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Any, TypeGuard

from iam.backtest.calibration import MIN_CALIBRATION_OBS, RELIABILITY_CAP, RELIABILITY_FLOOR

logger = logging.getLogger(__name__)

# Default reliabilities (conservative, institutional standard)
DEFAULT_RELIABILITIES = {
    "cost_of_equity": 0.70,  # Institutional baseline
    "fcfe_upside": 0.70,
    "relative_value": 0.70,
}

# The only signal the empirical backtest measures (the composite score's IC). It does
# NOT calibrate cost_of_equity / fcfe_upside / relative_value, so its reliability is
# never applied to them.
EMPIRICAL_SIGNAL = "composite"

# Neutral reliabilities (no information)
NEUTRAL_RELIABILITIES = {
    "cost_of_equity": 0.50,
    "fcfe_upside": 0.50,
    "relative_value": 0.50,
}


class ReliabilityLoader:
    """Load and validate calibrated reliability weights."""

    def __init__(self, calibration_path: Path | None = None):
        """Initialize loader.

        Args:
            calibration_path: Path to calibrated_reliabilities.json
                             Defaults to src/iam/arbitration/calibrated_reliabilities_empirical.json if it exists,
                             otherwise falling back to calibrated_reliabilities.json
        """
        if calibration_path is None:
            empirical_path = Path(__file__).parent / "calibrated_reliabilities_empirical.json"
            if empirical_path.exists():
                calibration_path = empirical_path
            else:
                calibration_path = Path(__file__).parent / "calibrated_reliabilities.json"

        self.path = calibration_path
        self._data: dict[str, float] | None = None
        self._is_empirical = False
        self._metadata: dict = {}

    @staticmethod
    def _is_finite(x: Any) -> TypeGuard[float]:
        return isinstance(x, int | float) and not isinstance(x, bool) and math.isfinite(x)

    def _validate_empirical(self, raw: dict) -> str | None:
        """Return None if the empirical schema is valid, else the reason it is not."""
        ic = raw.get("empirical_ic")
        bayes = raw.get("bayesian_calibration")
        if not isinstance(ic, dict) or not isinstance(bayes, dict):
            return "calibration insufficient: empirical_ic / bayesian_calibration missing"
        if raw.get("signal") != EMPIRICAL_SIGNAL:
            return f"calibration insufficient: signal {raw.get('signal')!r} is not {EMPIRICAL_SIGNAL!r}"
        if not self._is_finite(ic.get("mean")):
            return "calibration insufficient: empirical IC mean is not finite (NaN or missing)"
        n_obs = ic.get("n_obs")
        if not self._is_finite(n_obs) or n_obs < MIN_CALIBRATION_OBS:
            return (
                f"calibration insufficient: {n_obs} IC observations "
                f"(need at least {MIN_CALIBRATION_OBS})"
            )
        rel = bayes.get("reliability")
        if not self._is_finite(rel) or not (RELIABILITY_FLOOR <= rel <= RELIABILITY_CAP):
            return (
                f"calibration insufficient: reliability {rel!r} is not a finite number in "
                f"[{RELIABILITY_FLOOR}, {RELIABILITY_CAP}]"
            )
        return None

    def _fallback(self, reason: str) -> dict[str, float]:
        """Record why defaults are in use and return them."""
        self._is_empirical = False
        self._metadata["reason"] = reason
        self._data = dict(DEFAULT_RELIABILITIES)
        return self._data

    def load(self) -> dict[str, float]:
        """Load reliabilities with validation.

        Returns:
            Dict mapping signal name -> reliability weight. Always contains the
            DEFAULT_RELIABILITIES signals; "composite" is added only when a valid
            empirical calibration exists. The empirical calibration measures the
            composite score alone, so it never overrides the other signals.

        Priority:
            1. Valid empirical calibration (data_source == "empirical" and schema valid)
            2. Default (safe fallback), with the reason in metadata()["reason"]
        """
        self._is_empirical = False
        self._metadata = {}

        if not self.path.exists():
            logger.warning(f"No calibration file at {self.path}, using defaults")
            return self._fallback(f"no calibration file at {self.path}")

        try:
            # json accepts NaN/Infinity tokens (older files); validation treats them as missing.
            raw_data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw_data, dict):
                raise ValueError("top-level JSON value is not an object")
        except Exception as e:
            logger.error(f"Failed to load calibration JSON: {e}, using defaults")
            return self._fallback(f"calibration file unreadable: {e}")

        meta = raw_data.get("_meta")
        self._metadata = dict(meta) if isinstance(meta, dict) else {}
        data_source = self._metadata.get("data_source", "unknown")

        if data_source == "empirical":
            invalid = self._validate_empirical(raw_data)
            if invalid is not None:
                logger.warning(f"{invalid}; using defaults")
                return self._fallback(invalid)
            ic = raw_data["empirical_ic"]
            reliability = float(raw_data["bayesian_calibration"]["reliability"])
            self._metadata.update(
                period=raw_data.get("period"),
                ic_mean=ic["mean"],
                ic_std=ic.get("std") if self._is_finite(ic.get("std")) else None,
                n_obs=ic["n_obs"],
                reliability=reliability,
            )
            self._is_empirical = True
            logger.info(
                f"Loading empirical calibration (v{self._metadata.get('version')}), "
                f"period {self._metadata.get('period')}, IC mean {ic['mean']:.4f}"
            )
            self._data = {**DEFAULT_RELIABILITIES, EMPIRICAL_SIGNAL: reliability}
            return self._data

        if data_source == "insufficient_data":
            reason = self._metadata.get("reason") or "no reason recorded"
            msg = f"calibration insufficient: {reason}"
            logger.warning(f"{msg}; using defaults")
            return self._fallback(msg)

        if data_source == "synthetic":
            logger.warning("⚠️  SYNTHETIC CALIBRATION LOADED")
            logger.warning(f"   Version: {self._metadata.get('version')}")
            logger.warning("   This is architectural validation only. NOT FOR PRODUCTION.")
            logger.warning("   Using default reliabilities instead of synthetic values")
            return self._fallback("synthetic calibration ignored (architectural validation only)")

        logger.warning(f"Unknown calibration source: {data_source}, using defaults")
        return self._fallback(f"unknown calibration source: {data_source}")

    def get_reliability(self, signal_name: str, data_source: str | None = None) -> float:
        """Get reliability for a specific signal.

        Args:
            signal_name: Name of signal (e.g., 'cost_of_equity')
            data_source: Override loaded data source ('empirical', 'synthetic', 'default')

        Returns:
            Reliability weight [0.5, 0.95]
        """
        if data_source == "neutral":
            return NEUTRAL_RELIABILITIES.get(signal_name, 0.50)

        if not self._data:
            self._data = self.load()

        return self._data.get(signal_name, DEFAULT_RELIABILITIES.get(signal_name, 0.70))

    def is_empirical(self) -> bool:
        """Check if loaded calibration is empirical (real backtest)."""
        if not self._data:
            self.load()
        return self._is_empirical

    def metadata(self) -> dict:
        """Get calibration metadata."""
        if not self._data:
            self.load()
        return self._metadata

    def summary(self) -> str:
        """Human-readable summary of loaded calibration."""
        if not self._data:
            self._data = self.load()

        if self._is_empirical:
            lines = [
                "📊 EMPIRICAL CALIBRATION (composite signal only)",
                f"  Version: {self._metadata.get('version')}",
                f"  Period: {self._metadata.get('period')}",
                f"  IC Mean: {self._metadata.get('ic_mean')}",
                f"  IC Std: {self._metadata.get('ic_std', 'N/A')}",
                f"  Composite reliability: {self._metadata.get('reliability')}",
                f"  Source: {self._metadata.get('data_source')}",
            ]
        else:
            lines = [
                "Reliabilities: defaults (no valid empirical calibration)",
                f"  Reason: {self._metadata.get('reason', 'unknown')}",
            ]

        return "\n".join(lines)


def get_reliabilities() -> dict[str, float]:
    """Convenience function: Load reliabilities with safe defaults.

    Returns:
        Dict mapping signal -> reliability, with safe fallbacks
    """
    loader = ReliabilityLoader()
    return loader.load()


def get_reliability(signal_name: str) -> float:
    """Get reliability for a single signal.

    Args:
        signal_name: Signal name (e.g., 'cost_of_equity')

    Returns:
        Reliability weight, or default if not found
    """
    loader = ReliabilityLoader()
    return loader.get_reliability(signal_name)


def is_empirical_calibration() -> bool:
    """Check if using empirical (real backtest) calibration."""
    loader = ReliabilityLoader()
    return loader.is_empirical()
