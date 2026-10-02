"""Verdict conviction-downgrade paths and Bayesian updater/evidence behaviour."""

from types import SimpleNamespace

import pytest

from iam.data.security import Security
from iam.pipeline.verdict import VerdictGenerator, _downgrade_band
from iam.thesis.bayesian.evidence import Evidence, ScenarioLikelihood
from iam.thesis.bayesian.priors import ScenarioPrior
from iam.thesis.bayesian.updater import BayesianUpdater
from iam.thesis.bayesian.updater import ThesisEngine as MatrixEngine
from iam.thesis.scenarios import ScenarioAssumptions, ScenarioMatrix, ValuationScenario
from iam.valuation.types import Method, TriangulationResult, ValuationResult


def _tri(center=0.25, conf=0.9, verdict="agree"):
    return TriangulationResult(
        cluster_center=center,
        cluster_members=[Method.REVERSE_DCF],
        confidence=conf,
        verdict=verdict,
    )


def _rel(ftp=None):
    return ValuationResult(method=Method.RELATIVE, fair_value_to_price=ftp)


def _gen(tri=None, sec=None, **kw):
    return VerdictGenerator().generate(tri or _tri(), _rel(), sec or Security(ticker="V"), **kw)


class TestDowngradeBand:
    def test_steps_and_floor(self):
        assert _downgrade_band("HIGH") == "MEDIUM"
        assert _downgrade_band("HIGH", 2) == "LOW"
        assert _downgrade_band("MEDIUM", 5) == "LOW"
        assert _downgrade_band("LOW") == "LOW"

    def test_unknown_band_passthrough(self):
        assert _downgrade_band("WEIRD", 2) == "WEIRD"


class TestRatings:
    def test_thresholds(self):
        assert _gen(_tri(0.25)).rating == "BUY"
        assert _gen(_tri(0.0)).rating == "HOLD"
        assert _gen(_tri(-0.2)).rating == "SELL"

    @pytest.mark.parametrize("verdict", ["no_data", "disagree"])
    def test_inconclusive_on_failed_triangulation(self, verdict):
        r = _gen(_tri(0.3, verdict=verdict))
        assert r.rating == "INCONCLUSIVE"

    def test_inconclusive_without_center(self):
        r = _gen(_tri(None))
        assert r.rating == "INCONCLUSIVE" and "No implied upside" in r.notes[0]

    def test_mismatch_makes_buy_speculative(self):
        assert _gen(_tri(0.25), mismatch_score=70).rating == "SPECULATIVE_BUY"
        assert _gen(_tri(0.25), mismatch_score=10).rating == "BUY"

    def test_confidence_bands(self):
        assert _gen(_tri(conf=0.85)).confidence_band == "HIGH"
        assert _gen(_tri(conf=0.6)).confidence_band == "MEDIUM"
        r = _gen(_tri(conf=0.2))
        assert r.confidence_band == "LOW" and any("LOW" in n for n in r.notes)

    def test_low_band_note_suppressed_for_inconclusive(self):
        r = _gen(_tri(None, conf=0.1))
        assert not any("Confidence band is LOW" in n for n in r.notes)

    def test_arbitration_path(self):
        r = _gen(_tri(0.3, conf=0.9), synthesis_upside=0.25)
        assert r.arbitration is not None
        assert r.blended_upside == pytest.approx(0.6 * 0.3 + 0.4 * 0.25)
        assert r.rating == "STRONG BUY"
        assert any("Master Arbitration" in n for n in r.notes)

    def test_arbitration_moderate_note(self):
        r = _gen(_tri(0.3, conf=0.7), synthesis_upside=0.0)
        assert any("MODERATE due to conflicting" in n for n in r.notes)

    def test_peer_ranking_note(self):
        sec = Security(ticker="V", sector="Software")
        r = VerdictGenerator().generate(_tri(), _rel(0.25), sec)
        assert any("25% discount to Software" in n for n in r.notes)
        r = VerdictGenerator().generate(_tri(), _rel(-0.4), sec)
        assert any("40% premium" in n for n in r.notes)

    def test_leverage_penalty(self):
        sec = Security(ticker="V")
        sec.fundamentals.total_debt = 500.0
        sec.fundamentals.ebitda_ttm = 100.0
        r = _gen(_tri(conf=0.9), sec=sec)
        assert r.confidence_band == "MEDIUM"
        assert any("5.0x" in n for n in r.notes)


def _check(n):
    return SimpleNamespace(number=n, narrative=f"n{n}")


class TestConvictionDowngrades:
    @pytest.mark.parametrize("mult,band", [(0.9, "HIGH"), (0.8, "MEDIUM"), (0.6, "LOW")])
    def test_law_report(self, mult, band):
        rep = SimpleNamespace(violations=[_check(1)], flags=[_check(2)], conviction_multiplier=mult)
        r = _gen(law_report=rep)
        assert r.confidence_band == band
        assert any("[LAW 1 VIOLATED]" in n for n in r.notes)
        assert any("[LAW 2 FLAGGED]" in n for n in r.notes)

    @pytest.mark.parametrize(
        "drift,band", [(0.1, "HIGH"), (0.3, "MEDIUM"), (0.6, "LOW"), (None, "HIGH")]
    )
    def test_stress_drift(self, drift, band):
        resp = SimpleNamespace(conviction_drift=drift, scenario=SimpleNamespace(name="rates+100"))
        assert _gen(stress_response=resp).confidence_band == band

    def test_thesis_drift(self):
        rep = SimpleNamespace(
            has_drift=True, degrade_levels=1, breaches=["a", "b"], notes=lambda: ["x", "y"]
        )
        r = _gen(drift_report=rep)
        assert r.confidence_band == "MEDIUM"
        assert any("2 breaches" in n for n in r.notes) and "  ↳ x" in r.notes

    def test_thesis_drift_zero_levels_or_absent(self):
        rep = SimpleNamespace(has_drift=True, degrade_levels=0, breaches=[], notes=lambda: [])
        assert _gen(drift_report=rep).confidence_band == "HIGH"
        rep = SimpleNamespace(has_drift=False, degrade_levels=2, breaches=[], notes=lambda: [])
        assert _gen(drift_report=rep).confidence_band == "HIGH"

    @pytest.mark.parametrize(
        "gap,center,band",
        [
            (0.2, 0.25, "HIGH"),  # below soft threshold
            (0.35, 0.25, "MEDIUM"),  # bullish rating, overvalued
            (0.6, 0.25, "LOW"),
            (-0.35, -0.2, "MEDIUM"),  # SELL rating, undervalued
            (-0.6, 0.25, "HIGH"),  # gap agrees with direction -> no change
            (0.6, -0.2, "HIGH"),
        ],
    )
    def test_justified_premium(self, gap, center, band):
        jp = SimpleNamespace(premium_gap=gap)
        r = _gen(_tri(center), justified_premium=jp)
        assert r.confidence_band == band
        if band != "HIGH":
            word = "overvalued" if gap > 0 else "undervalued"
            assert any(word in n for n in r.notes)

    def test_justified_premium_none_gap(self):
        assert _gen(justified_premium=SimpleNamespace(premium_gap=None)).confidence_band == "HIGH"


class TestEvidence:
    def test_likelihood_clamped(self):
        assert ScenarioLikelihood(0.0).probability == 0.01
        assert ScenarioLikelihood(5).probability == 1.0

    def test_reliability_clamped_and_floats_normalised(self):
        e = Evidence("T", "d", {"A": 0.5}, reliability=3)
        assert e.reliability == 1.0
        assert isinstance(e.likelihoods["A"], ScenarioLikelihood)
        assert Evidence("T", "d", reliability=-1).reliability == 0.0

    def test_dampening_formula(self):
        e = Evidence("T", "d", {"A": 0.2}, reliability=0.5)
        assert e.get_dampened_likelihood("A") == pytest.approx(1 + (0.2 - 1) * 0.5)
        assert Evidence("T", "d", {"A": 0.2}, reliability=0.0).get_dampened_likelihood("A") == 1.0

    def test_unknown_label_is_neutral_and_floor(self):
        assert Evidence("T", "d", {}).get_dampened_likelihood("zz") == 1.0
        e = Evidence("T", "d", {"A": 0.01})
        assert e.get_dampened_likelihood("A") == pytest.approx(0.01)

    def test_int_likelihood_branch(self):
        e = Evidence("T", "d", {})
        e.likelihoods["A"] = 1  # raw int bypasses normalisation
        assert e.get_dampened_likelihood("A") == 1.0

    def test_dampened_dict(self):
        e = Evidence("T", "d", {"A": 0.4, "B": 0.8}, reliability=0.5)
        assert e.get_dampened_likelihoods() == pytest.approx({"A": 0.7, "B": 0.9})


class TestBayesianUpdater:
    def test_empty(self):
        assert BayesianUpdater.update([], Evidence("T", "d")) == []

    def test_posterior_math(self):
        priors = [ScenarioPrior("Bull", 0.5), ScenarioPrior("Bear", 0.5)]
        post = BayesianUpdater.update(priors, Evidence("T", "d", {"Bull": 0.8, "Bear": 0.2}))
        d = {p.label: p.probability for p in post}
        assert d["Bull"] == pytest.approx(0.8) and d["Bear"] == pytest.approx(0.2)

    def test_zero_reliability_is_no_update(self):
        priors = [ScenarioPrior("Bull", 0.3), ScenarioPrior("Bear", 0.7)]
        post = BayesianUpdater.update(priors, Evidence("T", "d", {"Bull": 0.9}, reliability=0))
        assert [p.probability for p in post] == pytest.approx([0.3, 0.7])

    def test_impossible_evidence_returns_priors_copy(self):
        priors = [ScenarioPrior("A", 0.0)]
        post = BayesianUpdater.update(priors, Evidence("T", "d"))
        assert post[0].probability == 0.0 and post[0] is not priors[0]


def _scen(name, p, tp=100.0):
    return ValuationScenario(name, p, "t", [], ScenarioAssumptions(0.1, 0.08, 0.02), tp)


class TestMatrixEngine:
    EVID = Evidence("T", "d", {"Bull": 0.9, "Bear": 0.1})

    def test_matrix_update_in_place(self):
        m = ScenarioMatrix("X", {"Bull": _scen("Bull", 0.5), "Bear": _scen("Bear", 0.5)})
        out = MatrixEngine.apply_update(m, self.EVID)
        assert out is m
        assert m.scenarios["Bull"].probability == pytest.approx(0.9)
        assert sum(s.probability for s in m.scenarios.values()) == pytest.approx(1.0)

    def test_list_update_uses_scenario_names(self):
        lst = [_scen("Bull", 0.5), _scen("Bear", 0.5)]
        out = MatrixEngine.apply_update(lst, self.EVID)
        assert out is lst
        assert lst[0].probability == pytest.approx(0.9)
        assert lst[1].probability == pytest.approx(0.1)
