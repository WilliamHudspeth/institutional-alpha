"""Behavioural tests for thesis.engine and thesis.scenarios."""

import pytest

from iam.data.security import Assumption, Security, Thesis
from iam.thesis.bayesian.evidence import Evidence
from iam.thesis.bayesian.priors import ScenarioPrior
from iam.thesis.engine import ThesisEngine, ThesisEvaluation
from iam.thesis.scenarios import ScenarioAssumptions, ScenarioMatrix, ValuationScenario


def _sec(**kw) -> Security:
    return Security(
        ticker="T",
        theses=[
            Thesis(
                label="Bear",
                fair_value_low=50,
                fair_value_high=80,
                assumptions=[Assumption(name="g", value=0.02)],
            ),
            Thesis(
                label="Bull",
                fair_value_low=120,
                fair_value_high=150,
                assumptions=[Assumption(name="g", value=0.10), Assumption(name="tag", value="x")],
            ),
        ],
        **kw,
    )


def _fv(sec: Security) -> float:
    return 1000 * sec.qualitative["g"]


class TestEvaluate:
    def test_no_theses(self):
        ev = ThesisEngine().evaluate(Security(ticker="X"))
        assert ev.best_case is None and ev.worst_case is None and ev.spread is None
        assert ev.narrative == "No theses defined."

    def test_range_and_spread(self):
        ev = ThesisEngine().evaluate(_sec())
        assert (ev.worst_case, ev.best_case, ev.spread) == (50, 150, 100)
        assert ev.warnings == []

    def test_missing_bounds_gives_none_spread(self):
        sec = Security(ticker="X", theses=[Thesis(label="Base")])
        ev = ThesisEngine().evaluate(sec)
        assert ev.spread is None and ev.best_case is None

    def test_overlap_warning(self):
        sec = Security(
            ticker="X",
            theses=[
                Thesis(label="bull", fair_value_low=70, fair_value_high=100),
                Thesis(label="bear", fair_value_low=40, fair_value_high=80),
            ],
        )
        ev = ThesisEngine().evaluate(sec)
        assert len(ev.warnings) == 1 and "Overlap Warning" in ev.warnings[0]


class TestSimulate:
    def test_no_theses(self):
        ev = ThesisEngine().simulate(Security(ticker="X"), _fv)
        assert ev.narrative == "No theses defined."

    def test_ranges_follow_valuation_and_state_restored(self):
        sec = _sec(qualitative={"keep": 1})
        ev = ThesisEngine().simulate(sec, _fv, spread_pct=0.1)
        bear, bull = sec.theses
        assert bear.fair_value_low == pytest.approx(20 * 0.9)
        assert bear.fair_value_high == pytest.approx(20 * 1.1)
        assert bull.fair_value_high == pytest.approx(100 * 1.1)
        assert ev.worst_case == pytest.approx(18)
        assert ev.best_case == pytest.approx(110)
        assert "Dynamically simulated 2" in ev.narrative
        assert sec.qualitative == {"keep": 1}

    def test_valuation_failure_becomes_warning(self):
        def boom(sec):
            raise RuntimeError("nope")

        ev = ThesisEngine().simulate(_sec(), boom)
        assert len(ev.warnings) == 2
        assert "Failed to simulate thesis 'Bear'" in ev.warnings[0]

    def test_restores_none_qualitative(self):
        sec = _sec()
        sec.qualitative = None
        ThesisEngine().simulate(sec, _fv)
        assert sec.qualitative is None


class TestSensitivity:
    def test_perturbation_scales_value(self):
        res = ThesisEngine().calculate_sensitivity(_sec(), _fv, "g", 0.5)
        assert [r[0] for r in res] == ["Bear", "Bull"]
        assert res[0][1:] == pytest.approx((20.0, 30.0))
        assert res[1][1:] == pytest.approx((100.0, 150.0))

    def test_no_theses_and_non_numeric_skipped(self):
        eng = ThesisEngine()
        assert eng.calculate_sensitivity(Security(ticker="X"), _fv, "g") == []
        assert eng.calculate_sensitivity(_sec(), _fv, "tag") == []
        assert eng.calculate_sensitivity(_sec(), _fv, "missing") == []

    def test_failing_valuation_skipped_and_state_restored(self):
        def boom(sec):
            raise ValueError

        sec = _sec(qualitative={"a": 1})
        assert ThesisEngine().calculate_sensitivity(sec, boom, "g") == []
        assert sec.qualitative == {"a": 1}


class TestExpectedValue:
    def test_none_without_inputs(self):
        eng = ThesisEngine()
        assert eng.calculate_expected_value(Security(ticker="X"), [ScenarioPrior("a", 1)]) is None
        assert eng.calculate_expected_value(_sec(), []) is None

    def test_none_when_no_label_matches(self):
        assert ThesisEngine().calculate_expected_value(_sec(), [ScenarioPrior("zzz", 1)]) is None

    def test_weighted_midpoints_case_insensitive(self):
        priors = [ScenarioPrior("BEAR", 0.25), ScenarioPrior("bull", 0.75)]
        ev = ThesisEngine().calculate_expected_value(_sec(), priors)
        assert ev == pytest.approx(65 * 0.25 + 135 * 0.75)

    def test_renormalises_over_matched_only(self):
        priors = [ScenarioPrior("bear", 0.2), ScenarioPrior("other", 0.8)]
        assert ThesisEngine().calculate_expected_value(_sec(), priors) == pytest.approx(65)


class TestApplyEvidence:
    def test_posteriors_sum_to_one_and_shift_toward_likely(self):
        priors = [ScenarioPrior("Bear", 0.5), ScenarioPrior("Bull", 0.5)]
        evidence = Evidence("T", "beat", likelihoods={"Bear": 0.1, "Bull": 0.9})
        ev = ThesisEngine().apply_evidence(_sec(), priors, evidence)
        post = {p.label: p.probability for p in ev.posteriors}
        assert sum(post.values()) == pytest.approx(1.0)
        assert post["Bull"] == pytest.approx(0.9)
        assert ev.expected_value == pytest.approx(65 * 0.1 + 135 * 0.9)
        assert "Applied Evidence: 'beat'" in ev.narrative


class TestRender:
    def test_dispersed_in_range_with_posteriors_and_warnings(self):
        eng = ThesisEngine()
        ev = eng.evaluate(_sec())
        ev.expected_value = 100.0
        ev.warnings = ["careful"]
        ev.posteriors = [ScenarioPrior("Bull", 0.6)]
        out = eng.render_report(ev, current_price=100.0)
        assert "Consensus Range: 50.00 - 150.00" in out
        assert "Expected Value (EV): 100.00" in out
        assert "HIGH DISPERSION" in out
        assert "IN RANGE" in out
        assert "• careful" in out
        assert "[Bull] : 60.0%" in out

    def test_consolidated_and_out_of_range(self):
        ev = ThesisEvaluation(best_case=105, worst_case=100, spread=5, narrative="n")
        out = ThesisEngine().render_report(ev, current_price=200)
        assert "CONSOLIDATED" in out and "OUT OF RANGE" in out

    def test_incomplete(self):
        out = ThesisEngine().render_report(ThesisEvaluation(None, None, None, "n"))
        assert "Insufficient data" in out and "INCOMPLETE" in out

    def test_sensitivity_report(self):
        eng = ThesisEngine()
        assert eng.render_sensitivity_report([], "g", 0.1) == "No sensitivity data to display."
        out = eng.render_sensitivity_report([("Base", 100.0, 110.0), ("Zero", 0.0, 5.0)], "g", 0.1)
        assert "perturbed by +10.0%" in out
        assert "+10.00%" in out
        assert "█" * 20 in out
        assert "Zero" not in out


class TestScenarios:
    def _m(self):
        a = ScenarioAssumptions(0.1, 0.08, 0.02)
        return ScenarioMatrix(
            "ABC",
            {
                "bull": ValuationScenario("Bull", 0.25, "up", ["s"], a, 200.0),
                "bear": ValuationScenario("Bear", 0.75, "down", ["s"], a, 100.0),
            },
        )

    def test_probability_clamped(self):
        a = ScenarioAssumptions(0.1, 0.08, 0.02)
        assert ValuationScenario("x", 1.7, "t", [], a).probability == 1.0
        assert ValuationScenario("x", -1, "t", [], a).probability == 0.0

    def test_pwev_and_upside(self):
        m = self._m()
        assert m.get_pwev() == pytest.approx(125.0)
        assert m.get_upside(100.0) == pytest.approx(0.25)
        assert m.get_upside(0) == 0.0

    def test_pwev_normalises_and_handles_empty(self):
        assert ScenarioMatrix("E").get_pwev() == 0.0
        m = self._m()
        for s in m.scenarios.values():
            s.probability = 0.0
        assert m.get_pwev() == 0.0
        m = self._m()
        for s in m.scenarios.values():
            s.probability /= 2
        assert m.get_pwev() == pytest.approx(125.0)

    def test_summaries(self):
        m = self._m()
        s = m.scenarios["bull"].summarize()
        assert "Bull (25%)" in s and "Target: $200.00" in s and "WACC: 8.00%" in s
        out = m.summarize()
        assert out.startswith("Scenario Matrix for ABC") and "PWEV: $125.00" in out
