"""Manifest system for backtest reproducibility (git SHA, file hashes, config snapshot)."""

import hashlib
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any


class BacktestManifest:
    """Captures code and data state for audit trail."""

    def __init__(self, config: "BacktestConfig"):
        """Initialize manifest with git state and file hashes."""
        self.config = config
        self.git_sha = self._get_git_sha()
        self.timestamp = datetime.utcnow().isoformat()
        self.file_hashes = self._compute_file_hashes()

    def _get_git_sha(self) -> str:
        """Get current git commit SHA."""
        try:
            sha = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()
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
        return {
            "_meta": {
                "version": "v0.4.0",
                "git_sha": self.git_sha,
                "timestamp": self.timestamp,
            },
            "config": config_dict,
            "file_hashes": self.file_hashes,
        }

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
            return json.load(f)
