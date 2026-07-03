"""Manifest system for backtest reproducibility (git SHA, file hashes, config snapshot).

Extended to capture **data provenance**: which data tiers/sources actually served
a run, and whether any field fell back to a degraded tier. Pass the
`TieredDataSource.audit_summary()` dict as `data_provenance` and it is recorded
in the manifest alongside code/config hashes, so a run that leaned on a degraded
source is reproducible and visible rather than silent.

The new argument is optional and defaults to None, so existing callers are
unaffected.
"""

import hashlib
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from iam.backtest.config import BacktestConfig


class BacktestManifest:
    """Captures code, data, and provenance state for audit trail."""

    def __init__(
        self,
        config: "BacktestConfig",
        data_provenance: dict[str, Any] | None = None,
    ):
        """Initialize manifest with git state, file hashes, and optional provenance.

        Args:
            config: the frozen backtest config.
            data_provenance: optional dict from ``TieredDataSource.audit_summary()``
                describing which sources/tiers served the run. When provided, a
                ``data_provenance`` block (and a top-level ``degraded`` flag) is
                added to the manifest.
        """
        self.config = config
        self.data_provenance = data_provenance
        self.git_sha = self._get_git_sha()
        self.timestamp = datetime.utcnow().isoformat()
        self.file_hashes = self._compute_file_hashes()

    def _get_git_sha(self) -> str:
        """Get current git commit SHA."""
        try:
            sha = subprocess.check_output(["git", "rev-parse", "HEAD"])  # nosec.decode().strip()
            return sha
        except (subprocess.CalledProcessError, FileNotFoundError):
            return "unknown"

    def _compute_file_hashes(self) -> dict[str, str]:
        """Compute SHA256 hashes of critical backtest files."""
        files = [
            "src/iam/backtest/config.py",
            "src/iam/backtest/manifest.py",
            "src/iam/backtest/snapshots.py",
            "src/iam/backtest/prices.py",
            "src/iam/backtest/metrics.py",
            "src/iam/backtest/quantiles.py",
            "src/iam/backtest/runner.py",
            "src/iam/backtest/calibration.py",
            "src/iam/backtest/universe.py",
            # Data layer — hashing these ties results to the exact source/router code.
            "src/iam/backtest/sources/base.py",
            "src/iam/backtest/sources/composite.py",
            "src/iam/backtest/sources/tiers.py",
            "src/iam/backtest/sources/yfinance_source.py",
            "src/iam/backtest/sources/stooq_source.py",
            "src/iam/backtest/sources/fmp_source.py",
            "src/iam/backtest/sources/tiingo_source.py",
            "src/iam/backtest/sources/sec_edgar_source.py",
        ]

        hashes = {}
        for file_path in files:
            full_path = Path(file_path)
            if full_path.exists():
                file_hash = hashlib.sha256(full_path.read_bytes()).hexdigest()[:12]
                hashes[file_path] = file_hash

        # Also hash data files if they exist
        if self.config.universe_file.exists():
            u_hash = hashlib.sha256(self.config.universe_file.read_bytes()).hexdigest()[:12]
            hashes[str(self.config.universe_file)] = u_hash

        if self.config.price_file.exists():
            p_hash = hashlib.sha256(self.config.price_file.read_bytes()).hexdigest()[:12]
            hashes[str(self.config.price_file)] = p_hash

        return hashes

    def to_dict(self) -> dict[str, Any]:
        """Export manifest as dictionary."""
        # Pydantic model_dump() returns PosixPath objects; stringify for JSON
        config_dict = self.config.model_dump()
        config_dict = {k: (str(v) if isinstance(v, Path) else v) for k, v in config_dict.items()}
        out: dict[str, Any] = {
            "_meta": {
                "version": "v0.4.0",
                "git_sha": self.git_sha,
                "timestamp": self.timestamp,
            },
            "config": config_dict,
            "file_hashes": self.file_hashes,
        }
        if self.data_provenance is not None:
            out["data_provenance"] = self.data_provenance
            # Surface a top-level flag so a degraded run is obvious at a glance.
            out["_meta"]["degraded_data"] = bool(self.data_provenance.get("degraded_count", 0))
        return out

    def write(self, path: Path) -> None:
        """Write manifest to JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)

    @staticmethod
    def load(path: Path) -> dict[str, Any]:
        """Load manifest from JSON file."""
        if not path.exists():
            return {}
        with open(path) as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
            return {}
