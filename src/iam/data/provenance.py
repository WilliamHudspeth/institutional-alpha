"""Audit trail and provenance tracking for institutional valuations.

Every calculation should be traceable to its source (Damodaran baseline, live data, etc).
This module provides utilities for attaching provenance metadata to risk profiles.
"""

from __future__ import annotations

from typing import Any

from iam.data.damodaran import read_country_erp, read_country_tax


def _dataset_stamp(table: dict[str, Any]) -> str:
    """``YYYY-MM`` of a dataset's ``as_of`` (``unknown`` if it carries none)."""
    as_of = str(table.get("as_of", ""))[:7]
    return as_of if len(as_of) == 7 and as_of[4] == "-" else "unknown"


def attach_provenance(data: dict[str, Any], version: str | None = None) -> dict[str, Any]:
    """Attach provenance metadata to a dict for auditability.

    Args:
        data: Dictionary to augment with provenance. A ``tax_source`` key means the
            data used the Damodaran country tax table, so its version is stamped too.
        version: Source version identifier; default is derived from the loaded country
            ERP dataset (e.g. ``damodaran_2026-04``), so it cannot go stale.

    Returns:
        Same dict with _provenance key added
    """
    result = dict(data)
    if version is None:
        version = f"damodaran_{_dataset_stamp(read_country_erp())}"
    result["_provenance"] = {
        "version": version,
        "source": "Damodaran (NYU Stern)",
        "reference": "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/",
        "stale": False,  # Mark as current vintage unless explicitly set
    }
    if "tax_source" in data:
        result["_provenance"]["tax_version"] = f"damodaran_tax_{_dataset_stamp(read_country_tax())}"
    return result
