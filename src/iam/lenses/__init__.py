"""Valuation lenses for alternative views of fair value."""

from iam.lenses.base import BaseLens, LensResult, two_stage_pv
from iam.lenses.damodaran_base import DamodaranBaseLens
from iam.lenses.expectations_difficulty import ExpectationsDifficultyLens
from iam.lenses.platform_compounder import PlatformCompounderLens
from iam.lenses.rate_sensitive import RateSensitiveLens
from iam.lenses.synthesis import SynthesisResult, synthesize_lenses

__all__ = [
    "BaseLens",
    "LensResult",
    "two_stage_pv",
    "RateSensitiveLens",
    "PlatformCompounderLens",
    "ExpectationsDifficultyLens",
    "DamodaranBaseLens",
    "synthesize_lenses",
    "SynthesisResult",
]
