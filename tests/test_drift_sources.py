"""Thesis drift must say where its bounds came from.

Regression cover for: constraint lookup depending on the CWD, and a shipped
``<TICKER>.example.yml`` silently acting as the owner's thesis (and
downgrading the verdict).
"""

from __future__ import annotations

import os
import types
from pathlib import Path
from unittest.mock import patch

import pytest

from iam import Fundamentals, MarketData, Security, ValuationPipeline
from iam.thesis.drift import (
    ConstraintBreach,
    DriftReport,
    constraints_dir,
    find_constraints,
    no_thesis_message,
)
from iam.ui import research_panels as rp

_YAML = """\
ticker: {ticker}
constraints:
  - id: margin_floor
    metric: operating_margin
    comparator: ">="
    bound: 0.50
    severity: 2
"""


@pytest.fixture
def cdir(tmp_path, monkeypatch):
    monkeypatch.setenv("IAM_CONSTRAINTS_DIR", str(tmp_path))
    return tmp_path


def _breach() -> ConstraintBreach:
    return ConstraintBreach(
        id="margin_floor",
        metric="operating_margin",
        comparator=">=",
        bound=0.5,
        actual=0.2,
        severity=2,
        supports=None,
        note="",
    )


def test_default_dir_does_not_depend_on_cwd(tmp_path, monkeypatch):
    monkeypatch.delenv("IAM_CONSTRAINTS_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    d = constraints_dir()
    assert d.is_absolute()
    assert (d / "MSFT.example.yml").exists()


def test_user_file_preferred_over_example(cdir):
    (cdir / "ABC.example.yml").write_text(_YAML.format(ticker="ABC"))
    assert find_constraints("ABC") == (cdir / "ABC.example.yml", "example")
    (cdir / "ABC.yml").write_text(_YAML.format(ticker="ABC"))
    assert find_constraints("ABC") == (cdir / "ABC.yml", "user")


def test_missing_file_returns_none(cdir):
    assert find_constraints("NOPE") is None


def test_example_breaches_never_degrade_the_verdict():
    user = DriftReport(ticker="ABC", breaches=[_breach()])
    example = DriftReport(ticker="ABC", breaches=[_breach()], source="example")
    assert user.degrade_levels == 2
    assert example.degrade_levels == 0
    assert example.has_drift  # still reported, just labelled
    assert user.source_banner is None
    assert "EXAMPLE THRESHOLDS" in example.source_banner


def _sec(ticker: str) -> Security:
    return Security(
        ticker=ticker,
        fundamentals=Fundamentals(
            fcf_ttm=1000,
            net_income_ttm=1000,
            shares_outstanding=100,
            operating_margin=0.20,
            revenue_history=[1200, 1100, 1000, 900, 800],
        ),
        market=MarketData(price=180),
        qualitative={"forecast_growth": 0.06},
    )


@pytest.fixture
def offline():
    with (
        patch("iam.data.markets.fetch_live_quote", return_value=None),
        patch(
            "iam.data.providers.yfinance_adapter.build_regression_inputs",
            side_effect=RuntimeError("offline"),
        ),
    ):
        yield


def test_pipeline_labels_example_source(cdir, offline):
    (cdir / "ABC.example.yml").write_text(_YAML.format(ticker="ABC"))
    report = ValuationPipeline().run(_sec("ABC"))
    dr = report.drift_report
    assert dr is not None and dr.is_example
    assert dr.constraints_path == str(cdir / "ABC.example.yml")
    assert "EXAMPLE THRESHOLDS" in report.explain()


def test_pipeline_finds_constraints_from_other_cwd(cdir, offline, tmp_path_factory):
    (cdir / "ABC.yml").write_text(_YAML.format(ticker="ABC"))
    elsewhere = tmp_path_factory.mktemp("elsewhere")
    old = os.getcwd()
    os.chdir(elsewhere)
    try:
        report = ValuationPipeline().run(_sec("ABC"))
    finally:
        os.chdir(old)
    assert report.drift_report is not None
    assert report.drift_report.source == "user"
    assert Path(report.drift_report.constraints_path).name == "ABC.yml"


class _Canvas:
    def __init__(self):
        self.text = []

    def put(self, r, c, t, style=""):
        self.text.append(str(t))

    def hline(self, *a, **k):
        pass


def test_tui_panel_flags_example_and_missing():
    cv = _Canvas()
    dr = DriftReport(ticker="ABC", breaches=[_breach()], source="example")
    rp.ThesisDriftPanel().render(
        cv,
        0,
        20,
        0,
        100,
        types.SimpleNamespace(pipeline_result=types.SimpleNamespace(drift_report=dr)),
    )
    out = "\n".join(cv.text)
    assert "EXAMPLE THRESHOLDS" in out
    assert "no effect on the verdict" in out

    cv = _Canvas()
    rp.ThesisDriftPanel().render(
        cv,
        0,
        20,
        0,
        100,
        types.SimpleNamespace(
            pipeline_result=types.SimpleNamespace(drift_report=None, ticker="XYZ")
        ),
    )
    assert no_thesis_message("XYZ")[:40] in "\n".join(cv.text)
