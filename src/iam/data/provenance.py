"""Audit trail and provenance tracking for institutional valuations.

Every calculation should be traceable to its source (Damodaran baseline, live data, etc).
This module provides utilities for attaching provenance metadata to risk profiles.
"""

from __future__ import annotations

from typing import Any


def attach_provenance(data: dict[str, Any], version: str = "damodaran_jan_2026") -> dict[str, Any]:
    """Attach provenance metadata to a dict for auditability.

    Args:
        data: Dictionary to augment with provenance
        version: Source version identifier

    Returns:
        Same dict with _provenance key added
    """
    result = dict(data)
    result["_provenance"] = {
        "version": version,
        "source": "Damodaran (NYU Stern)",
        "reference": "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/",
        "stale": False,  # Mark as current vintage unless explicitly set
    }
    return result
