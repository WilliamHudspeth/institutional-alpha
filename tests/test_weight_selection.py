import json

import numpy as np
import pandas as pd
import pytest

from iam.backtest.weight_selection import (
    MAX_DATA_WEIGHT,
    PRIOR,
    CandidateContext,
    TrialLedger,
    candidate_equal,
    candidate_prior,
    empirical_bayes_data_weight,
    format_horse_race_report,
    haircut_vector,
    project_to_simplex,
    run_horse_race,
)

FACTORS = ["signal", "noise_a", "noise_b"]


def _panel(n_months=96, n_stocks=60, signal_strength=0.4, seed=0):
    """Monthly cross-sections where only factor 0 predicts returns."""
    rng = np.random.default_rng(seed)
    dates = list(pd.date_range("2010-01-31", periods=n_months, freq="ME"))
    scores, rets = {}, {}
    for d in dates:
        x = rng.standard_normal((n_stocks, len(FACTORS)))
        scores[d] = x
        rets[d] = signal_strength * x[:, 0] + rng.standard_normal(n_stocks)
    return dates, scores, rets


class TestHorseRace:
    def test_wrong_prior_is_replaced(self):
        dates, scores, rets = _panel()
        prior = {"signal": 0.05, "noise_a": 0.55, "noise_b": 0.40}

        res = run_horse_race(dates, scores, rets, FACTORS, prior, spa_n_boot=500)

        assert res.status == "success"
        assert res.promoted, res.reasons
        assert res.winner != PRIOR
        assert res.full_sample_weights[res.winner][0] > prior["signal"]
        assert res.pbo is not None and res.pbo < 0.5
        assert res.spa_pvalue is not None and res.spa_pvalue < 0.10

    def test_pure_noise_keeps_the_prior(self):
        dates, scores, rets = _panel(signal_strength=0.0, seed=1)
        prior = {"signal": 0.4, "noise_a": 0.3, "noise_b": 0.3}

        res = run_horse_race(dates, scores, rets, FACTORS, prior, spa_n_boot=500)

        assert not res.promoted
        assert res.winner == PRIOR
        assert res.reasons

    def test_candidates_only_see_training_rows(self):
        dates, scores, rets = _panel(n_months=48)
        seen: list[int] = []

        def spy(ctx: CandidateContext) -> np.ndarray:
            seen.append(len(ctx.ic))
            return ctx.prior.copy()

        run_horse_race(
            dates,
            scores,
            rets,
            FACTORS,
            np.ones(3),
            horizon_months=3,
            candidates={PRIOR: candidate_prior, "spy": spy},
            spa_n_boot=100,
        )

        # Every fold call sees fewer rows than the full sample (test fold plus the
        # purge/embargo gap removed); the final call is the full-sample fit.
        assert all(n < len(dates) for n in seen[:-1])
        assert seen[-1] == len(dates)

    def test_too_few_dates_fails_cleanly(self):
        dates, scores, rets = _panel(n_months=4)
        res = run_horse_race(dates, scores, rets, FACTORS, np.ones(3))
        assert res.status.startswith("failed")
        assert not res.promoted

    def test_rejects_bad_prior(self):
        dates, scores, rets = _panel(n_months=24)
        with pytest.raises(ValueError):
            run_horse_race(dates, scores, rets, FACTORS, np.zeros(3))

    def test_report_names_every_candidate(self):
        dates, scores, rets = _panel(n_months=48)
        res = run_horse_race(dates, scores, rets, FACTORS, np.ones(3), spa_n_boot=100)
        text = format_horse_race_report(res)
        for name in res.candidate_names:
            assert name in text
        assert "Decision:" in text


class TestEmpiricalBayes:
    def test_noise_dominated_dispersion_gives_no_data_weight(self):
        means = np.array([0.010, 0.012, 0.011])
        ses = np.array([0.02, 0.02, 0.02])
        np.testing.assert_array_equal(empirical_bayes_data_weight(means, ses), np.zeros(3))

    def test_clear_dispersion_is_capped(self):
        means = np.array([0.10, -0.05, 0.00])
        ses = np.array([0.001, 0.001, 0.001])
        w = empirical_bayes_data_weight(means, ses)
        np.testing.assert_allclose(w, MAX_DATA_WEIGHT)

    def test_noisier_factor_gets_less_data_weight(self):
        means = np.array([0.08, -0.04, 0.02, 0.05])
        ses = np.array([0.005, 0.005, 0.05, 0.005])
        w = empirical_bayes_data_weight(means, ses, cap=1.0)
        assert w[2] < w[0]

    def test_undefined_factor_gets_zero(self):
        means = np.array([0.10, -0.05, np.nan])
        ses = np.array([0.001, 0.001, 0.001])
        assert empirical_bayes_data_weight(means, ses)[2] == 0.0


class TestHelpers:
    @pytest.mark.parametrize("v", [[0.2, 0.3, 0.5], [3.0, -1.0, 0.5], [-2.0, -1.0, -3.0]])
    def test_simplex_projection(self, v):
        w = project_to_simplex(np.array(v))
        assert np.all(w >= 0)
        assert np.isclose(w.sum(), 1.0)

    def test_simplex_projection_keeps_points_already_on_it(self):
        v = np.array([0.2, 0.3, 0.5])
        np.testing.assert_allclose(project_to_simplex(v), v)

    def test_haircut_vector(self):
        np.testing.assert_array_equal(
            haircut_vector(["quality", "crowding"], {"quality"}), np.array([0.5, 1.0])
        )

    def test_equal_candidate_falls_back_to_prior_when_nothing_is_positive(self):
        ctx = CandidateContext(
            ic=-np.ones((10, 2)) * 0.05, prior=np.array([0.7, 0.3]), haircut=np.ones(2), nw_lags=3
        )
        np.testing.assert_array_equal(candidate_equal(ctx), ctx.prior)


class TestTrialLedger:
    def test_identical_configs_count_once(self, tmp_path):
        ledger = TrialLedger(tmp_path / "ledger.jsonl")
        ledger.append("weight_candidate", "a", {"x": 1})
        ledger.append("weight_candidate", "a", {"x": 1}, {"ic": 0.02})
        ledger.append("manual", "edit DEFAULT_WEIGHTS", {"x": 2})

        assert len(ledger.records()) == 3
        assert ledger.n_trials() == 2
        assert ledger.file_hash() is not None

    def test_records_are_strict_json_lines(self, tmp_path):
        path = tmp_path / "ledger.jsonl"
        ledger = TrialLedger(path)
        ledger.append("weight_candidate", "a", {"x": 1}, {"ic": 0.02})
        record = json.loads(path.read_text().splitlines()[0])
        assert {"timestamp", "git_sha", "config_hash", "kind", "name", "config", "result"} <= set(
            record
        )

    def test_empty_ledger(self, tmp_path):
        ledger = TrialLedger(tmp_path / "missing.jsonl")
        assert ledger.n_trials() == 0
        assert ledger.file_hash() is None

    def test_horse_race_records_each_candidate(self, tmp_path):
        dates, scores, rets = _panel(n_months=48)
        ledger = TrialLedger(tmp_path / "ledger.jsonl")
        res = run_horse_race(
            dates, scores, rets, FACTORS, np.ones(3), ledger=ledger, spa_n_boot=100
        )
        assert ledger.n_trials() == len(res.candidate_names)
        assert res.n_trials == len(res.candidate_names)


def test_backtest_package_exports_resolve():
    import iam.backtest as bt

    missing = [n for n in bt.__all__ if not hasattr(bt, n)]
    assert missing == []
    assert len(bt.__all__) == len(set(bt.__all__))
