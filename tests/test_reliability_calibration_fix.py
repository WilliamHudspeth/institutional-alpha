"""Regression tests: an unmeasured IC must never become a reliability number.

Background: ``min(0.95, nan)`` returns 0.95 in Python, so a backtest that measured
nothing (IC = NaN) used to be reported as 95% reliable, written as invalid JSON
labelled "empirical", and the loader then crashed reading it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from iam.arbitration import reliability_loader
from iam.arbitration.reliability_loader import (
    DEFAULT_RELIABILITIES,
    ReliabilityLoader,
    get_reliabilities,
    is_empirical_calibration,
)
from iam.backtest.calibration import (
    MIN_CALIBRATION_OBS,
    build_empirical_calibration_record,
    ic_to_reliability,
    ic_to_reliability_bayesian,
    serialize_calibration_record,
)

SHIPPED = Path(reliability_loader.__file__).parent / "calibrated_reliabilities_empirical.json"


def _no_nan(token: str):
    raise ValueError(f"invalid JSON constant {token}")


def _valid_record(reliability: float = 0.8, n_obs: int = 59, ic_mean: float = 0.06) -> dict:
    return {
        "_meta": {"version": "t", "data_source": "empirical"},
        "signal": "composite",
        "period": "2018-01-31 to 2024-12-31",
        "empirical_ic": {"mean": ic_mean, "std": 0.1, "n_obs": n_obs},
        "bayesian_calibration": {
            "prior_ic": 0.02,
            "posterior_ic": 0.05,
            "posterior_std": 0.01,
            "shrinkage_factor": 0.6,
            "reliability": reliability,
        },
    }


class TestCalibrationMath:
    def test_linear_nan_is_not_95(self):
        assert ic_to_reliability(float("nan")) is None

    def test_linear_inf_is_not_a_number(self):
        assert ic_to_reliability(float("inf")) is None
        assert ic_to_reliability(float("-inf")) is None

    def test_linear_finite_mapping_unchanged(self):
        assert ic_to_reliability(0.05) == pytest.approx(0.75)
        assert ic_to_reliability(1.0) == pytest.approx(0.95)
        assert ic_to_reliability(-1.0) == pytest.approx(0.50)

    def test_bayesian_nan_never_95(self):
        r = ic_to_reliability_bayesian(float("nan"), float("nan"), 59)
        assert r["reliability"] is None
        assert r["posterior_ic"] is None
        assert r["posterior_std"] is None
        assert "not finite" in r["reason"]

    def test_bayesian_nan_std_alone_is_insufficient(self):
        r = ic_to_reliability_bayesian(0.05, float("nan"), 59)
        assert r["reliability"] is None
        assert r["reason"]

    def test_bayesian_too_few_obs_is_insufficient(self):
        r = ic_to_reliability_bayesian(0.10, 0.05, MIN_CALIBRATION_OBS - 1)
        assert r["reliability"] is None
        assert "observations" in r["reason"]

    def test_bayesian_enough_obs_has_number_and_no_reason(self):
        r = ic_to_reliability_bayesian(0.10, 0.05, MIN_CALIBRATION_OBS)
        assert r["reliability"] is not None
        assert 0.5 <= r["reliability"] <= 0.95
        assert r["reason"] is None


class TestWriter:
    def _record(self, ic_mean, ic_std, n_obs):
        return build_empirical_calibration_record(
            ic_mean=ic_mean,
            ic_std=ic_std,
            n_obs=n_obs,
            version="v",
            timestamp="t",
            git_sha="sha",
            period="a to b",
            horizon_days=63,
        )

    def test_nan_ic_writes_valid_json_insufficient(self):
        text = serialize_calibration_record(self._record(float("nan"), float("nan"), 59))
        data = json.loads(text, parse_constant=_no_nan)
        assert data["_meta"]["data_source"] == "insufficient_data"
        assert data["_meta"]["reason"]
        assert data["bayesian_calibration"]["reliability"] is None
        assert data["empirical_ic"]["mean"] is None
        assert data["empirical_ic"]["n_obs"] == 59
        assert data["bayesian_calibration"]["prior_ic"] == 0.02

    def test_valid_ic_is_empirical(self):
        text = serialize_calibration_record(self._record(0.06, 0.1, 59))
        data = json.loads(text, parse_constant=_no_nan)
        assert data["_meta"]["data_source"] == "empirical"
        assert "reason" not in data["_meta"]
        assert 0.5 <= data["bayesian_calibration"]["reliability"] <= 0.95

    def test_written_valid_record_is_accepted_by_loader(self, tmp_path):
        p = tmp_path / "c.json"
        p.write_text(serialize_calibration_record(self._record(0.06, 0.1, 59)))
        assert ReliabilityLoader(p).is_empirical() is True


class TestLoaderShippedFile:
    def test_shipped_file_is_strict_json(self):
        json.loads(SHIPPED.read_text(encoding="utf-8"), parse_constant=_no_nan)

    def test_shipped_file_is_insufficient(self):
        data = json.loads(SHIPPED.read_text(encoding="utf-8"))
        assert data["_meta"]["data_source"] == "insufficient_data"
        assert data["bayesian_calibration"]["reliability"] is None
        assert data["_meta"]["reason"]

    def test_loader_defaults_without_raising(self):
        loader = ReliabilityLoader(SHIPPED)
        assert loader.load() == DEFAULT_RELIABILITIES
        assert loader.is_empirical() is False
        assert "insufficient" in loader.summary().lower()
        assert loader.get_reliability("cost_of_equity") == 0.70

    def test_default_path_loader_does_not_raise(self):
        assert ReliabilityLoader().load() == DEFAULT_RELIABILITIES

    def test_module_helpers_do_not_raise(self):
        assert get_reliabilities() == DEFAULT_RELIABILITIES
        assert is_empirical_calibration() is False


class TestLoaderSchema:
    def _loader(self, tmp_path, record) -> ReliabilityLoader:
        p = tmp_path / "c.json"
        p.write_text(json.dumps(record))
        return ReliabilityLoader(p)

    def test_valid_file_adds_composite_only(self, tmp_path):
        loader = self._loader(tmp_path, _valid_record(0.8))
        data = loader.load()
        assert loader.is_empirical() is True
        assert data["composite"] == 0.8
        for sig in ("cost_of_equity", "fcfe_upside", "relative_value"):
            assert data[sig] == DEFAULT_RELIABILITIES[sig]
        assert loader.get_reliability("cost_of_equity") == 0.70
        assert loader.get_reliability("composite") == 0.8

    def test_default_dict_is_not_mutated(self, tmp_path):
        self._loader(tmp_path, _valid_record(0.8)).load()
        assert "composite" not in DEFAULT_RELIABILITIES

    def test_nan_token_file_is_insufficient(self, tmp_path):
        p = tmp_path / "old.json"
        p.write_text(
            '{"_meta": {"data_source": "empirical"}, "signal": "composite",'
            ' "empirical_ic": {"mean": NaN, "std": NaN, "n_obs": 59},'
            ' "bayesian_calibration": {"reliability": 0.95, "posterior_ic": NaN}}'
        )
        loader = ReliabilityLoader(p)
        assert loader.load() == DEFAULT_RELIABILITIES
        assert loader.is_empirical() is False
        assert "not finite" in loader.summary()

    @pytest.mark.parametrize(
        "mutate",
        [
            lambda r: r["empirical_ic"].update(n_obs=MIN_CALIBRATION_OBS - 1),
            lambda r: r["bayesian_calibration"].update(reliability=0.99),
            lambda r: r["bayesian_calibration"].update(reliability=0.4),
            lambda r: r["bayesian_calibration"].update(reliability=None),
            lambda r: r["bayesian_calibration"].update(reliability="0.8"),
            lambda r: r["_meta"].update(data_source="insufficient_data"),
            lambda r: r.pop("empirical_ic"),
            lambda r: r.update(signal="other"),
        ],
    )
    def test_invalid_schema_falls_back(self, tmp_path, mutate):
        rec = _valid_record(0.8)
        mutate(rec)
        loader = self._loader(tmp_path, rec)
        assert loader.load() == DEFAULT_RELIABILITIES
        assert loader.is_empirical() is False
        assert loader.metadata().get("reason")

    def test_infinite_ic_rejected(self, tmp_path):
        p = tmp_path / "inf.json"
        p.write_text(json.dumps(_valid_record(0.8)).replace("0.06", "Infinity"))
        loader = ReliabilityLoader(p)
        assert loader.load() == DEFAULT_RELIABILITIES
        assert loader.is_empirical() is False


class TestWriteCalibrationLinear:
    def test_nan_lens_gets_no_reliability_and_json_is_strict(self, tmp_path):
        from iam.backtest.calibration import write_calibration

        out = tmp_path / "c.json"
        write_calibration({"measured": 0.05, "unmeasured": float("nan")}, out)
        data = json.loads(out.read_text(encoding="utf-8"), parse_constant=_no_nan)
        assert data["reliabilities"] == {"measured": pytest.approx(0.75)}
        assert data["unmeasured_lenses"] == ["unmeasured"]
