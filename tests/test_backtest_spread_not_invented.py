"""compute_validation_metrics must not derive a quintile spread from IC."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from iam.backtest.multiple_testing import compute_validation_metrics


def _df(with_spread: bool) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    df = pd.DataFrame({"ic_quality": rng.normal(0.05, 0.02, 24)})
    if with_spread:
        df["spread_quality"] = 0.031
    return df


def test_spread_is_nan_when_not_measured():
    m = compute_validation_metrics(_df(False), ["quality"])
    assert math.isnan(m.factor_metrics["quality"]["spread"])


def test_spread_uses_measured_column():
    m = compute_validation_metrics(_df(True), ["quality"])
    assert m.factor_metrics["quality"]["spread"] == 0.031
