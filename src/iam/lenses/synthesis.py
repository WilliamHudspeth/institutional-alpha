"""Synthesis engine for valuation lenses."""

from __future__ import annotations

from typing import Sequence, Optional
from dataclasses import dataclass

from iam.lenses.base import LensResult


@dataclass
class SynthesisResult:
    weighted_fair_value_low: Optional[float]
    weighted_fair_value_high: Optional[float]
    weighted_implied_move_pct: Optional[float]
    narratives: list[str]


def synthesize_lenses(lenses: Sequence[LensResult]) -> SynthesisResult:
    """Combines multiple LensResult outputs into a weighted summary.
    
    Diagnostic lenses (where implied_move_pct is None) are skipped for the 
    weighted fair value calculation but their narratives are preserved.
    """
    # Rule 5: diagnostic lenses are skipped in the weighted average
    valid_lenses = [
        l for l in lenses
        if l.fair_value_low is not None 
        and l.fair_value_high is not None 
        and l.implied_move_pct is not None
        and l.confidence > 0
    ]
    
    narratives = [f"{l.lens_name.upper()}: {l.narrative}" for l in lenses]
    total_conf = sum(l.confidence for l in valid_lenses)
    
    if not valid_lenses or total_conf == 0:
        return SynthesisResult(
            weighted_fair_value_low=None, weighted_fair_value_high=None, 
            weighted_implied_move_pct=None, narratives=narratives
        )
        
    weighted_low = sum(l.fair_value_low * l.confidence for l in valid_lenses) / total_conf
    weighted_high = sum(l.fair_value_high * l.confidence for l in valid_lenses) / total_conf
    weighted_move = sum(l.implied_move_pct * l.confidence for l in valid_lenses) / total_conf
    
    return SynthesisResult(
        weighted_fair_value_low=weighted_low, weighted_fair_value_high=weighted_high, 
        weighted_implied_move_pct=weighted_move, narratives=narratives
    )