"""Tests for the assumption distribution engine."""

import pytest
from iam.valuation.assumptions import AssumptionDistribution

def test_assumption_distribution_sources():
    ad = AssumptionDistribution(
        name="growth",
        historical_cagr=0.10,
        sustainable_growth=0.08
    )
    sources = ad.get_sources()
    assert len(sources) == 2
    # weights should be normalized: 0.40/(0.4+0.25) and 0.25/(0.4+0.25)
    total_weight = sum(w for _, _, w in sources)
    assert total_weight == pytest.approx(1.0)

def test_recommended_value():
    ad = AssumptionDistribution(name="growth", historical_cagr=0.10)
    assert ad.recommended_value == 0.10
    
    ad.user_override = 0.15
    assert ad.recommended_value == 0.15
    
    empty_ad = AssumptionDistribution(name="empty")
    assert empty_ad.recommended_value == 0.0

def test_confidence_score():
    empty_ad = AssumptionDistribution(name="empty")
    assert empty_ad.confidence_score == 0.0
    
    single_ad = AssumptionDistribution(name="single", bottom_up=0.05)
    assert single_ad.confidence_score == 0.30
    
    multi_ad = AssumptionDistribution(
        name="multi",
        historical_cagr=0.10,
        sustainable_growth=0.10,
        bottom_up=0.10
    )
    # Variance is 0, so confidence should be high
    assert multi_ad.confidence_score > 0.60
