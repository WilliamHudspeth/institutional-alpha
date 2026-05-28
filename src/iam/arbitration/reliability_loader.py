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
from pathlib import Path

logger = logging.getLogger(__name__)

# Default reliabilities (conservative, institutional standard)
DEFAULT_RELIABILITIES = {
    "cost_of_equity": 0.70,  # Institutional baseline
    "fcfe_upside": 0.70,
    "relative_value": 0.70,
}

# Neutral reliabilities (no information)
NEUTRAL_RELIABILITIES = {
    "cost_of_equity": 0.50,
    "fcfe_upside": 0.50,
    "relative_value": 0.50,
}


class ReliabilityLoader:
    """Load and validate calibrated reliability weights."""

    def __init__(self, calibration_path: Path = None):
        """Initialize loader.

        Args:
            calibration_path: Path to calibrated_reliabilities.json
                             Defaults to src/iam/arbitration/calibrated_reliabilities.json
        """
        if calibration_path is None:
            calibration_path = Path(__file__).parent / "calibrated_reliabilities.json"

        self.path = calibration_path
        self._data = None
        self._is_empirical = False
        self._metadata = {}

    def load(self) -> dict[str, float]:
        """Load reliabilities with validation.

        Returns:
            Dict mapping signal name -> reliability weight

        Priority:
            1. Empirical calibration (if data_source == "empirical")
            2. Synthetic (if available, logs warning)
            3. Default (safe fallback)
        """
        if not self.path.exists():
            logger.warning(f"No calibration file at {self.path}, using defaults")
            return DEFAULT_RELIABILITIES

        try:
            raw_data = json.loads(self.path.read_text())
        except Exception as e:
            logger.error(f"Failed to load calibration JSON: {e}, using defaults")
            return DEFAULT_RELIABILITIES

        # Extract metadata
        self._metadata = raw_data.pop("_meta", {})

        # Validate source
        data_source = self._metadata.get("data_source", "unknown")

        if data_source == "empirical":
            self._is_empirical = True
            logger.info(f"Loading empirical calibration (v{self._metadata.get('version')})")
            logger.info(
                f"  Period: {self._metadata.get('period')}, "
                f"IC mean: {self._metadata.get('ic_mean'):.4f}"
            )
            return {k: v for k, v in raw_data.items() if k != "_meta"}

        elif data_source == "synthetic":
            self._is_empirical = False
            logger.warning("⚠️  SYNTHETIC CALIBRATION LOADED")
            logger.warning(f"   Version: {self._metadata.get('version')}")
            logger.warning("   This is architectural validation only. NOT FOR PRODUCTION.")
            logger.warning("   Using default reliabilities instead of synthetic values")
            return DEFAULT_RELIABILITIES

        else:
            logger.warning(f"Unknown calibration source: {data_source}, using defaults")
            return DEFAULT_RELIABILITIES

    def get_reliability(self, signal_name: str, data_source: str = None) -> float:
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
                "📊 EMPIRICAL CALIBRATION",
                f"  Version: {self._metadata.get('version')}",
                f"  Period: {self._metadata.get('period')}",
                f"  IC Mean: {self._metadata.get('ic_mean', 'N/A')}",
                f"  IC Std: {self._metadata.get('ic_std', 'N/A')}",
                f"  Source: {self._metadata.get('data_source')}",
            ]
        else:
            lines = [
                "⚠️  SYNTHETIC CALIBRATION (Architectural Validation Only)",
                "  NOT FOR PRODUCTION USE",
                "  Using default reliabilities instead",
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
