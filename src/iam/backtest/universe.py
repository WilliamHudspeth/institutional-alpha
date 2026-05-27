"""Static universe loader from JSON with integrity checking."""

import json
import hashlib
from pathlib import Path
from typing import Optional

from iam.data.security import Fundamentals, Security


def load_universe_from_json(path: Path) -> tuple[list[Security], str]:
    """Load static universe from JSON file with hash.

    Args:
        path: Path to universe JSON file (e.g., data/universe/sp100.json)

    Returns:
        Tuple of (securities list, file hash)

    Expected JSON format:
        {
            "universe": "sp100",
            "date": "2024-12-31",
            "tickers": ["AAPL", "MSFT", ...],
            "securities": [
                {
                    "ticker": "AAPL",
                    "sector": "Technology",
                    "industry": "Consumer Electronics",
                    "revenue_mix": {"Domestic": 0.6, "International": 0.4},
                    "shares_outstanding": 15_600_000_000
                },
                ...
            ]
        }
    """
    if not path.exists():
        raise FileNotFoundError(f"Universe file not found: {path}")

    # Read raw bytes for hash
    raw = path.read_bytes()
    file_hash = hashlib.sha256(raw).hexdigest()[:12]

    # Parse JSON
    data = json.loads(raw)

    # Build Security objects from securities list or infer from tickers
    securities = []
    if "securities" in data:
        for sec_data in data["securities"]:
            shares = sec_data.pop("shares_outstanding", None)
            sec = Security(**sec_data)
            if shares is not None:
                sec.fundamentals.shares_outstanding = shares
            securities.append(sec)
    elif "tickers" in data:
        # Minimal universe: just tickers, minimal Security objects
        for ticker in data["tickers"]:
            sec = Security(
                ticker=ticker,
                sector="Unknown",
                industry="Unknown",
                revenue_mix={},
                fundamentals=Fundamentals(shares_outstanding=1_000_000_000),
            )
            securities.append(sec)
    else:
        raise ValueError("Universe JSON must contain either 'securities' or 'tickers'")

    return securities, file_hash


def load_universe_tickers(path: Path) -> list[str]:
    """Load just the ticker list from universe file."""
    if not path.exists():
        raise FileNotFoundError(f"Universe file not found: {path}")

    data = json.loads(path.read_text())

    if "tickers" in data:
        return data["tickers"]
    elif "securities" in data:
        return [sec["ticker"] for sec in data["securities"]]
    else:
        raise ValueError("Universe JSON must contain either 'securities' or 'tickers'")
