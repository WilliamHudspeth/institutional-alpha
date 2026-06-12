"""Damodaran Laws constraint layer (v0.5 reasoning engine).

Theory-first consistency checks that flag fragile analyses instead of
inventing numbers. See :mod:`iam.laws.registry` for the five laws and
``docs/damodaran_laws.md`` for the full specification.
"""

from __future__ import annotations

from iam.laws.fade import excess_return_fade_path, fade_adjusted_growth
from iam.laws.registry import DamodaranLawRegistry
from iam.laws.types import LawCheck, LawReport, LawStatus

__all__ = [
    "LawStatus",
    "LawCheck",
    "LawReport",
    "DamodaranLawRegistry",
    "excess_return_fade_path",
    "fade_adjusted_growth",
]
