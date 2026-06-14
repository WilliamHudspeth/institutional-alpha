from pathlib import Path

import pytest

from iam.thesis.drift import (
    ConstraintBreach,
    DriftDetector,
    DriftReport,
    ThesisConstraint,
    load_constraints,
)


def test_thesis_constraint_validation():
    # Valid constraint
    c = ThesisConstraint(
        id="roic_check",
        metric="roic_durability",
        comparator=">=",
        bound=0.15,
        severity=1,
        supports="Bull",
        note="Note",
    )
    assert c.id == "roic_check"

    # Invalid metric
    with pytest.raises(ValueError, match="Unknown metric"):
        ThesisConstraint(id="bad", metric="invalid_metric", comparator=">=", bound=1.0)

    # Invalid comparator
    with pytest.raises(ValueError, match="Unknown comparator"):
        ThesisConstraint(id="bad", metric="roic_durability", comparator="~", bound=1.0)

    # Invalid severity
    with pytest.raises(ValueError, match="severity must be 1 or 2"):
        ThesisConstraint(id="bad", metric="roic_durability", comparator=">=", bound=1.0, severity=3)


def test_drift_report_degrade_levels():
    # No breaches
    r = DriftReport(ticker="AAPL")
    assert not r.has_drift
    assert r.degrade_levels == 0

    # Low severity breach
    b1 = ConstraintBreach(
        id="c1",
        metric="roic_durability",
        comparator=">=",
        bound=0.15,
        actual=0.10,
        severity=1,
        supports=None,
        note="test",
    )
    r.breaches.append(b1)
    assert r.has_drift
    assert r.degrade_levels == 1
    assert "c1" in r.notes()[0]

    # Add second breach, severity total = 3, capped at 2
    b2 = ConstraintBreach(
        id="c2",
        metric="fragility",
        comparator="<=",
        bound=0.5,
        actual=0.6,
        severity=2,
        supports="Bull",
        note="test2",
    )
    r.breaches.append(b2)
    assert r.degrade_levels == 2
    assert len(r.notes()) == 2
    assert "undermines 'Bull' case" in r.notes()[1]


def test_drift_detector_evaluate():
    class DummyReality:
        def __init__(self):
            self.roic_durability = 0.12
            self.fragility = 0.40

    class DummyFundamentals:
        def __init__(self):
            self.revenue_growth_ttm = 0.03
            self.total_debt = 100.0
            self.ebitda_ttm = 50.0

    constraints = [
        ThesisConstraint(
            id="roic", metric="roic_durability", comparator=">=", bound=0.15, severity=1
        ),
        ThesisConstraint(id="frag", metric="fragility", comparator="<=", bound=0.50, severity=1),
        ThesisConstraint(
            id="growth", metric="revenue_growth_ttm", comparator=">=", bound=0.05, severity=1
        ),
        ThesisConstraint(
            id="leverage", metric="debt_to_ebitda", comparator="<=", bound=3.0, severity=2
        ),
    ]

    detector = DriftDetector()
    report = detector.evaluate(
        ticker="AAPL",
        constraints=constraints,
        business_reality=DummyReality(),
        fundamentals=DummyFundamentals(),
    )

    # roic: 0.12 < 0.15 (breach, sev 1)
    # frag: 0.40 <= 0.50 (pass)
    # growth: 0.03 < 0.05 (breach, sev 1)
    # leverage: 100/50 = 2.0 <= 3.0 (pass)
    assert len(report.breaches) == 2
    breached_ids = {b.id for b in report.breaches}
    assert breached_ids == {"roic", "growth"}
    assert report.degrade_levels == 2
    assert not report.skipped


def test_drift_detector_skipped():
    constraints = [
        ThesisConstraint(id="roic", metric="roic_durability", comparator=">=", bound=0.15),
    ]
    detector = DriftDetector()
    report = detector.evaluate(
        ticker="AAPL", constraints=constraints, business_reality=None, fundamentals=None
    )
    assert not report.breaches
    assert report.skipped == ["roic"]


def test_load_constraints():
    # Test loading from data/constraints/AAPL.example.yml
    path = Path("data/constraints/AAPL.example.yml")
    if path.exists():
        ticker, constraints = load_constraints(path)
        assert ticker == "AAPL"
        assert len(constraints) == 4
        assert constraints[0].id == "roic_floor"
        assert constraints[0].metric == "roic_durability"
        assert constraints[0].bound == 0.15
