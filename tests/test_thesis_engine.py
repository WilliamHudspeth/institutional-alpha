"""Tests for the ThesisEngine and sensitivity analysis."""

import pytest

from iam.data.security import Assumption, Security, Thesis
from iam.thesis.engine import ThesisEngine
from iam.thesis.bayesian.priors import ScenarioPrior
from iam.thesis.bayesian.evidence import Evidence, ScenarioLikelihood


def mock_intrinsic_dcf(sec: Security) -> float:
    """A simplistic mock valuation function returning base * (1 + growth) * margin."""
    qualitative = sec.qualitative or {}
    growth = qualitative.get("revenue_growth_5y", 0.10)
    margin = qualitative.get("terminal_margin", 0.20)
    return 1000 * (1 + growth) * margin


def test_calculate_sensitivity_increases_fair_value():
    sec = Security(
        ticker="TEST",
        theses=[
            Thesis(
                label="Base",
                narrative="Base case.",
                assumptions=[
                    Assumption("terminal_margin", 0.20, source="user"),
                    Assumption("revenue_growth_5y", 0.10, source="user"),
                ]
            )
        ]
    )
    engine = ThesisEngine()

    # Calculate sensitivity of a 10% INCREASE to the terminal margin
    results = engine.calculate_sensitivity(sec, mock_intrinsic_dcf, "terminal_margin", 0.10)

    assert len(results) == 1
    thesis_label, base_fv, perturbed_fv = results[0]

    # Base FV = 1000 * (1 + 0.10) * 0.20 = 220.0
    # Perturbed FV = 1000 * (1 + 0.10) * 0.22 = 242.0
    assert thesis_label == "Base"
    assert base_fv == pytest.approx(220.0)
    assert perturbed_fv == pytest.approx(242.0)

    # Confirm perturbation actually increased the value
    assert perturbed_fv > base_fv

    # Check state reversion: ensure qualitative state returns to empty dict since it started as empty    assert sec.qualitative == {}

    # Check that original assumption value wasn't permanently mutated
    assert sec.theses[0].assumptions[0].value == 0.20


def test_expected_value_calculation():
    sec = Security(
        ticker="TEST",
        theses=[
            Thesis(label="Bull", fair_value_low=150, fair_value_high=200),
            Thesis(label="Bear", fair_value_low=50, fair_value_high=100),
        ]
    )
    engine = ThesisEngine()
    priors = [ScenarioPrior("Bull", 0.8), ScenarioPrior("Bear", 0.2)]

    # Bull mid = 175, Bear mid = 75
    # EV = (175 * 0.8) + (75 * 0.2) = 140 + 15 = 155
    ev = engine.calculate_expected_value(sec, priors)
    assert ev == pytest.approx(155.0)


def test_apply_evidence_updates_posteriors():
    sec = Security(
        ticker="TEST",
        theses=[
            Thesis(label="Bull", fair_value_low=150, fair_value_high=200),
            Thesis(label="Bear", fair_value_low=50, fair_value_high=100),
        ]
    )
    engine = ThesisEngine()
    priors = [ScenarioPrior("Bull", 0.5), ScenarioPrior("Bear", 0.5)]
    evidence = Evidence(
        type="EARNINGS_BEAT",
        description="Massive positive beat.",
        reliability=1.0,
        likelihoods={"Bull": ScenarioLikelihood(1.0), "Bear": ScenarioLikelihood(0.0)}
    )

    evaluation = engine.apply_evidence(sec, priors, evidence)

    # ~100% probability shifts to Bull, EV approaches Bull Midpoint (175)
    assert evaluation.expected_value == pytest.approx(175.0, abs=1.0)
    assert evaluation.posteriors[0].probability == pytest.approx(1.0, abs=0.01)
