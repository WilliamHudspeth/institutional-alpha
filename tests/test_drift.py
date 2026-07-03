"""Tests for Thesis Drift Detection (Phase 2.5)."""

import pytest

from iam.thesis.drift import (
    METRIC_RESOLVERS,
    DriftDetector,
    DriftReport,
    ThesisConstraint,
)
from tests.fixtures.sample_securities import make_security


class TestMetricResolvers:
    def test_all_expected_metrics_registered(self):
        expected = {
            "roic_durability",
            "cashflow_durability",
            "growth_quality",
            "capital_allocation",
            "fragility",
            "robustness",
            "revenue_growth_ttm",
            "operating_margin",
            "debt_to_ebitda",
            "roic",
            "reinvestment_rate",
        }
        assert expected.issubset(set(METRIC_RESOLVERS))

    def test_roic_resolver_uses_roic_history(self):
        sec = make_security(roic_history=[0.22, 0.18])
        val = METRIC_RESOLVERS["roic"](None, sec.fundamentals)
        assert val == pytest.approx(0.22)

    def test_roic_resolver_returns_none_without_data(self):
        sec = make_security()
        val = METRIC_RESOLVERS["roic"](None, sec.fundamentals)
        # No roic_history and no revenue/margin → None or computed float, not a crash
        assert val is None or isinstance(val, float)

    def test_reinvestment_rate_resolver(self):
        sec = make_security(capex_ttm=5e9, revenue_ttm=50e9, operating_margin=0.30)
        val = METRIC_RESOLVERS["reinvestment_rate"](None, sec.fundamentals)
        # capex / (revenue * margin) = 5e9 / 15e9 ≈ 0.333
        if val is not None:
            assert 0 < val < 2.0

    def test_resolver_none_propagation(self):
        """All resolvers must return None (not raise) when inputs are None."""
        for name, resolver in METRIC_RESOLVERS.items():
            result = resolver(None, None)
            assert result is None, f"resolver '{name}' raised or returned non-None on None inputs"


class TestDriftReport:
    def test_conviction_drift_no_breaches(self):
        report = DriftReport(ticker="TEST")
        assert report.conviction_drift == 0.0

    def test_conviction_drift_one_severity_one_breach(self):
        detector = DriftDetector()
        sec = make_security(operating_margin=0.10)
        constraints = [
            ThesisConstraint(
                id="margin_floor",
                metric="operating_margin",
                comparator=">=",
                bound=0.35,
                severity=1,
            )
        ]
        report = detector.evaluate("TEST", constraints, fundamentals=sec.fundamentals)
        assert report.has_drift
        assert report.conviction_drift == 0.5  # 1 degrade_level / 2

    def test_conviction_drift_capped_at_one(self):
        detector = DriftDetector()
        sec = make_security(operating_margin=0.05)
        constraints = [
            ThesisConstraint(
                id="c1", metric="operating_margin", comparator=">=", bound=0.35, severity=2
            ),
            ThesisConstraint(
                id="c2", metric="operating_margin", comparator=">=", bound=0.50, severity=2
            ),
        ]
        report = detector.evaluate("TEST", constraints, fundamentals=sec.fundamentals)
        # degrade_levels capped at 2, so conviction_drift capped at 1.0
        assert report.conviction_drift == 1.0

    def test_skipped_when_metric_data_missing(self):
        detector = DriftDetector()
        constraints = [
            ThesisConstraint(id="reinvest", metric="reinvestment_rate", comparator="<=", bound=0.5)
        ]
        report = detector.evaluate("TEST", constraints, fundamentals=None)
        assert "reinvest" in report.skipped
        assert not report.has_drift


class TestDriftConstraintYaml:
    def test_load_example_yaml(self):
        from pathlib import Path

        from iam.thesis.drift import load_constraints

        path = Path("data/constraints/MSFT.example.yml")
        if not path.exists():
            pytest.skip("Example YAML not present")
        ticker, constraints = load_constraints(path)
        assert ticker == "MSFT"
        assert len(constraints) == 3
        assert all(c.metric in METRIC_RESOLVERS for c in constraints)
