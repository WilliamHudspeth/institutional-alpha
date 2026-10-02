"""Behavioural tests for valuation.expectations_battlefield."""

from types import SimpleNamespace

import pytest

from iam.valuation.expectations_battlefield import (
    ExpectationBattlefieldExplicit,
    ExpectationsBattlefieldEngine,
    Scenario,
    ScenarioDistribution,
    alignment_score,
    build_distributions,
    distribution_overlap,
)


def _dist(growths, probs=None, margin=0.2, roic=0.1):
    probs = probs or [1 / len(growths)] * len(growths)
    return ScenarioDistribution([Scenario(p, g, margin, roic) for p, g in zip(probs, growths)])


class TestDistribution:
    def test_moments(self):
        d = _dist([0.0, 0.10], [0.25, 0.75])
        assert d.mean_growth() == pytest.approx(0.075)
        assert d.mean_margin() == pytest.approx(0.2)
        assert d.mean_roic() == pytest.approx(0.1)
        assert d.variance_growth() == pytest.approx(0.25 * 0.075**2 + 0.75 * 0.025**2)
        assert d.variance_margin() == pytest.approx(0.0)
        assert d.variance_roic() == pytest.approx(0.0)

    def test_weighted_median(self):
        d = _dist([0.30, 0.0, 0.10], [0.2, 0.5, 0.3])
        # sorted: 0.0 (0.5) -> cumulative reaches 50% immediately
        assert d.median_growth() == 0.0
        d2 = _dist([0.30, 0.0, 0.10], [0.6, 0.2, 0.2])
        assert d2.median_growth() == 0.30
        assert d.median_margin() == 0.2
        assert d.median_roic() == 0.1


class TestOverlap:
    def test_identical_is_high_and_bounded(self):
        d = _dist([0.0, 0.05, 0.10])
        ov = distribution_overlap(d, d)
        assert 0.9 <= ov <= 1.0

    def test_disjoint_is_zero(self):
        assert distribution_overlap(_dist([0.0, 0.01]), _dist([0.5, 0.51])) == pytest.approx(0.0)

    def test_degenerate_returns_one(self):
        assert distribution_overlap(_dist([0.1]), _dist([0.1])) == 1.0
        empty = ScenarioDistribution([])
        assert distribution_overlap(empty, empty) == 1.0

    def test_metric_selection(self):
        a = ScenarioDistribution([Scenario(1.0, 0.1, 0.1, 0.1)])
        b = ScenarioDistribution([Scenario(1.0, 0.1, 0.5, 0.1)])
        assert distribution_overlap(a, b, "growth") == 1.0
        assert distribution_overlap(a, b, "margin") == pytest.approx(0.0)


class TestAlignment:
    def test_identical_scores_near_max(self):
        d = _dist([0.0, 0.05, 0.10])
        assert alignment_score(d, d) > 90

    def test_far_apart_scores_low(self):
        assert alignment_score(_dist([0.0, 0.01]), _dist([0.5, 0.51])) < 40

    def test_degenerate_zero_variance_identical(self):
        # zero variance on both sides -> var_ratio branch = 1
        assert alignment_score(_dist([0.1]), _dist([0.1])) == pytest.approx(100.0)

    def test_bounded(self):
        s = alignment_score(_dist([0.0, 0.3]), _dist([0.1]))
        assert 0.0 <= s <= 100.0


class TestEngine:
    def test_identical_distributions_aligned(self):
        d = _dist([0.0, 0.05, 0.10])
        bf = ExpectationsBattlefieldEngine(d, d).compute()
        assert bf.growth_gap == 0 and bf.margin_gap == 0 and bf.roic_gap == 0
        assert bf.expectation_mismatch_score == pytest.approx(0.0)
        assert "broadly aligned" in bf._interpretation()

    def test_primary_disagreement_and_mismatch(self):
        intrinsic = ScenarioDistribution(
            [Scenario(0.5, 0.04, 0.20, 0.10), Scenario(0.5, 0.06, 0.22, 0.12)]
        )
        market = ScenarioDistribution(
            [Scenario(0.5, 0.14, 0.21, 0.10), Scenario(0.5, 0.16, 0.23, 0.12)]
        )
        bf = ExpectationsBattlefieldEngine(intrinsic, market).compute()
        assert bf.primary_disagreement == "Growth"
        assert bf.growth_gap == pytest.approx(0.10)
        assert bf.margin_gap == pytest.approx(0.01)
        assert bf.expectation_mismatch_score > 70
        assert "materially more optimistic" in bf._interpretation()
        assert bf.disagreement_ranking[0][0] == "Growth"
        assert 0 <= bf.expectation_mismatch_score <= 100


class TestExplicitModel:
    def _bf(self, mismatch):
        return ExpectationBattlefieldExplicit(
            market_growth=0.10,
            intrinsic_growth=0.05,
            market_margin=0.20,
            intrinsic_margin=0.25,
            market_roic=0.12,
            intrinsic_roic=0.10,
            growth_overlap=0.5,
            alignment_score=60,
            primary_disagreement="Growth",
            expectation_mismatch_score=mismatch,
            market_terminal_growth=0.03,
            market_beta=1.3,
            market_erp=0.06,
        )

    def test_gaps_and_ranking(self):
        bf = self._bf(50)
        assert bf.terminal_growth_gap == pytest.approx(0.005)
        assert bf.beta_gap == pytest.approx(0.3)
        assert bf.erp_gap == pytest.approx(0.01)
        ranking = bf.disagreement_ranking
        assert ranking[0] == ("Beta", pytest.approx(0.3))
        assert [v for _, v in ranking] == sorted((v for _, v in ranking), reverse=True)

    def test_summary_and_interpretation_bands(self):
        out = self._bf(50).summary()
        assert "EXPECTATIONS BATTLEFIELD" in out
        assert "Market:    +10.0%" in out and "Gap:       -5.0%" in out
        assert "Alignment Score:   60/100" in out
        assert "Moderate disagreement" in out
        assert "materially" in self._bf(80)._interpretation()
        assert "aligned" in self._bf(40)._interpretation()


def test_build_distributions():
    profile = SimpleNamespace(implied_growth=0.10, op_margin=0.20, roic=0.15, hist_volatility=0.03)
    tri = SimpleNamespace(blended_growth=0.06)
    intrinsic, market = build_distributions(profile, tri)
    assert [s.probability for s in market.scenarios] == [0.2, 0.6, 0.2]
    assert market.mean_growth() == pytest.approx(0.10)
    assert intrinsic.mean_growth() == pytest.approx(0.06)
    assert intrinsic.scenarios[0].growth == pytest.approx(0.03)
    assert intrinsic.scenarios[2].margin == pytest.approx(0.22)
    assert market.scenarios[0].roic == pytest.approx(0.13)
