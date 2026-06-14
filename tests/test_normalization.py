"""Tests for the cycle normalization engine."""

import pytest
from iam.valuation.normalization import (
    CycleWeights, normalize_through_cycle, apply_distributable_haircut, fragility_penalty
)

def test_cycle_weights_validation():
    cw = CycleWeights(expansion=0.25, contraction=0.25, distress=0.25, recovery=0.25)
    cw.validate()  # Should pass
    
    invalid_cw = CycleWeights(expansion=0.1)
    with pytest.raises(ValueError, match="must sum to 1.0"):
        invalid_cw.validate()

def test_normalize_through_cycle():
    # Test with default weights (expansion=0.5, contraction=0.3, distress=0.1, recovery=0.1)
    # factor = 0.5*1.0 + 0.3*0.7 + 0.1*0.4 + 0.1*0.75 = 0.5 + 0.21 + 0.04 + 0.075 = 0.825
    norm = normalize_through_cycle(100)
    assert norm == pytest.approx(82.5)

def test_apply_distributable_haircut():
    assert apply_distributable_haircut(100, 0.1) == 90
    with pytest.raises(ValueError):
        apply_distributable_haircut(100, 1.1)

def test_fragility_penalty():
    # gap = 1.85 - 0.69 = 1.16
    # penalty = -0.5 * 1.16 = -0.58
    assert fragility_penalty(1.85, 0.69) == pytest.approx(-0.58)
    # Test bounds
    assert fragility_penalty(10, 1) == -1.0
    assert fragility_penalty(1, 10) == 0.0
