"""Law 3 (terminal growth <= Rf) judges against the Rf the pipeline used (Part C1).

The orchestrator no longer writes ``qualitative["risk_free_rate"]``, so Law 3's old
4.3% fallback fired silently. The pipeline now passes the Rf it used (with its source)
through an explicit argument; with no Rf at all Law 3 is NOT_EVALUATED.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from iam.data.security import Fundamentals, MarketData, Security
from iam.laws import DamodaranLawRegistry
from iam.laws import registry as reg
from iam.laws.types import LawStatus
from iam.pipeline.orchestrator import ValuationPipeline

RF = 0.05  # deliberately not the retired 4.3% fallback


def _tnx(_symbol: str) -> SimpleNamespace:
    return SimpleNamespace(last=RF * 100.0)


def _security(**qual) -> Security:
    return Security(
        ticker="L3",
        sector="Investments & Asset Management",
        industry="Asset Management",
        fundamentals=Fundamentals(
            revenue_ttm=100.0,
            operating_margin=0.3,
            interest_expense_ttm=5.0,
            net_income_ttm=50.0,
            fcf_ttm=50.0,
            total_debt=230.0,
            shares_outstanding=10.0,
        ),
        market=MarketData(price=100.0, shares_outstanding=10.0, market_cap=1000.0, beta=1.3),
        qualitative=dict(qual),
    )


def _run(sec: Security):
    with (
        patch("iam.data.markets.fetch_live_quote", side_effect=_tnx),
        patch(
            "iam.data.providers.yfinance_adapter.build_regression_inputs",
            side_effect=Exception("No network"),
        ),
    ):
        return ValuationPipeline().run(sec)


def _law3(report):
    return next(c for c in report.checks if c.number == 3)


def test_pipeline_law3_is_evaluated_against_the_rf_the_pipeline_used():
    sec = _security(forecast_terminal_growth=0.07)
    report = _run(sec)
    assert report.intrinsic.assumptions["terminal_growth"] == pytest.approx(RF)  # capped at Rf
    check = _law3(report.law_report)
    assert check.components["risk_free_rate"] == pytest.approx(RF)
    assert "live ^TNX" in check.components["rf_source"]
    assert check.status is LawStatus.FLAG  # at the ceiling, not a VIOLATION vs a stale 4.3%


def test_pipeline_law3_passes_when_terminal_growth_has_headroom():
    report = _run(_security(forecast_terminal_growth=0.02))
    check = _law3(report.law_report)
    assert check.status is LawStatus.PASS
    assert check.components["risk_free_rate"] == pytest.approx(RF)


def test_no_rf_at_all_is_not_evaluated_with_a_narrative_saying_so():
    check = _law3(DamodaranLawRegistry().evaluate(_security(), {"terminal_growth": 0.05}))
    assert check.status is LawStatus.NOT_EVALUATED
    assert "risk-free" in check.narrative.lower()
    assert "risk_free_rate" not in check.components


def test_explicit_rf_argument_is_used_and_its_source_recorded():
    check = _law3(
        DamodaranLawRegistry().evaluate(
            _security(),
            {"terminal_growth": 0.06},
            risk_free_rate=0.05,
            rf_source="test source",
        )
    )
    assert check.status is LawStatus.VIOLATION
    assert check.components["risk_free_rate"] == 0.05
    assert check.components["rf_source"] == "test source"


def test_caller_supplied_qualitative_rf_wins_over_the_argument():
    sec = _security(risk_free_rate=0.06)
    check = _law3(
        DamodaranLawRegistry().evaluate(
            sec, {"terminal_growth": 0.05}, risk_free_rate=0.03, rf_source="pipeline"
        )
    )
    assert check.status is LawStatus.PASS
    assert check.components["risk_free_rate"] == 0.06
    assert check.components["rf_source"] == "caller-supplied"


def test_the_retired_default_is_gone():
    assert not hasattr(reg, "DEFAULT_RISK_FREE")
