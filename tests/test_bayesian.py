"""Tests for the Bayesian updating engine and signal dampening logic."""

import pytest

from iam.thesis.bayesian.evidence import Evidence, ScenarioLikelihood
from iam.thesis.bayesian.priors import ScenarioPrior
from iam.thesis.bayesian.updater import BayesianUpdater


@pytest.fixture
def initial_priors():
    """Standard starting thesis: 60% Base, 20% Bull, 20% Bear."""
    return [
        ScenarioPrior(label="Bull", probability=0.20),
        ScenarioPrior(label="Base", probability=0.60),
        ScenarioPrior(label="Bear", probability=0.20),
    ]


def test_high_signal_strength_swings_posteriors(initial_priors):
    """Perfect signal strength allows aggressive probability updates."""
    evidence = Evidence(
        type="EARNINGS_BEAT",
        description="Massive earnings beat directly confirming the Bull thesis.",
        reliability=1.0,  # 100% confidence in the data
        likelihoods={
            "Bull": ScenarioLikelihood(0.90),
            "Base": ScenarioLikelihood(0.40),
            "Bear": ScenarioLikelihood(0.05),
        },
    )
    updater = BayesianUpdater()
    posteriors = updater.update(initial_priors, evidence)
    post_map = {p.label: p.probability for p in posteriors}

    # Bear case likelihood was tiny, so its probability should collapse
    assert post_map["Bear"] < 0.05
    # Bull case likelihood was huge, so it should roughly double from 20% to ~42%
    assert post_map["Bull"] > 0.40


def test_low_signal_strength_dampens_swings(initial_priors):
    """Low signal strength mathematically shrinks likelihoods to prevent overfitting."""
    evidence = Evidence(
        type="ALTERNATIVE_DATA",
        description="Sketchy alternative data suggests a Bull thesis beat.",
        reliability=0.1,  # Only 10% confidence in the data
        likelihoods={
            "Bull": ScenarioLikelihood(0.90),
            "Base": ScenarioLikelihood(0.40),
            "Bear": ScenarioLikelihood(0.05),
        },
    )
    updater = BayesianUpdater()
    posteriors = updater.update(initial_priors, evidence)
    post_map = {p.label: p.probability for p in posteriors}

    # Because confidence is low, the posterior should barely move from the prior
    assert post_map["Bull"] == pytest.approx(0.209, abs=0.01)  # Barely moved from 0.20
    assert post_map["Base"] == pytest.approx(0.598, abs=0.01)  # Barely moved from 0.60
    assert post_map["Bear"] == pytest.approx(0.191, abs=0.01)  # Barely moved from 0.20


def test_zero_signal_strength_ignores_evidence(initial_priors):
    """Zero signal strength means the evidence provides no new information."""
    evidence = Evidence(
        type="RUMOR",
        description="Completely unverified rumor on a message board.",
        reliability=0.0,
        likelihoods={
            "Bull": ScenarioLikelihood(1.0),
            "Base": ScenarioLikelihood(0.0),
            "Bear": ScenarioLikelihood(0.0),
        },
    )
    updater = BayesianUpdater()
    posteriors = updater.update(initial_priors, evidence)
    post_map = {p.label: p.probability for p in posteriors}

    # Posteriors should exactly equal priors
    assert post_map["Bull"] == 0.20
    assert post_map["Base"] == 0.60
    assert post_map["Bear"] == 0.20
