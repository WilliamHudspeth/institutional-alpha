from unittest.mock import MagicMock

from iam.data.security import Fundamentals, Security
from iam.pipeline.verdict import VerdictGenerator
from iam.valuation.types import TriangulationResult


def test_verdict_generator_buy_rating():
    generator = VerdictGenerator(buy_threshold=0.15)
    sec = Security(ticker="TEST")

    # Mock a triangulation result with 20% upside and high confidence
    tri = TriangulationResult(
        verdict="agree",
        confidence=0.9,
        cluster_center=0.20,
        cluster_members=[],
        outliers=[],
        notes=[],
    )

    rel_mock = MagicMock()
    rel_mock.fair_value_to_price = 0.10

    result = generator.generate(tri, rel_mock, sec)
    assert result.rating == "BUY"
    assert result.confidence_band == "HIGH"


def test_verdict_generator_inconclusive_on_disagreement():
    generator = VerdictGenerator()
    sec = Security(ticker="TEST")
    tri = TriangulationResult(
        verdict="disagree",
        confidence=0.2,
        cluster_center=0.10,
        cluster_members=[],
        outliers=[],
        notes=[],
    )

    rel_mock = MagicMock()
    rel_mock.fair_value_to_price = -0.05

    result = generator.generate(tri, rel_mock, sec)
    assert result.rating == "INCONCLUSIVE"
    assert result.confidence_band == "LOW"


def test_verdict_generator_downgrades_high_leverage():
    generator = VerdictGenerator()
    # Security with Debt/EBITDA of 5.0x
    sec = Security(ticker="LEV", fundamentals=Fundamentals(total_debt=500, ebitda_ttm=100))

    tri = TriangulationResult(
        verdict="agree",
        confidence=0.9,
        cluster_center=0.25,
        cluster_members=[],
        outliers=[],
        notes=[],
    )

    rel_mock = MagicMock()
    rel_mock.fair_value_to_price = 0.15

    result = generator.generate(tri, rel_mock, sec)
    assert result.rating == "BUY"
    assert result.confidence_band == "MEDIUM"  # Downgraded from HIGH
    assert any("High leverage detected" in n for n in result.notes)


# ===========================================================================
# Damodaran-law and elasticity-stress conviction degradation
# ===========================================================================


def _agree_triangulation(upside: float = 0.20, confidence: float = 0.9) -> TriangulationResult:
    return TriangulationResult(
        verdict="agree",
        confidence=confidence,
        cluster_center=upside,
        cluster_members=[],
        outliers=[],
        notes=[],
    )


def _relative_mock():
    rel = MagicMock()
    rel.fair_value_to_price = 0.10
    return rel


def test_verdict_downgrades_on_law_violation():
    """One violation (multiplier 0.85) steps the band down one level."""
    from iam.laws.types import LawCheck, LawReport, LawStatus

    law_report = LawReport(
        checks=[
            LawCheck(
                number=2,
                name="growth_requires_reinvestment",
                status=LawStatus.VIOLATION,
                narrative="growth cannot be funded",
            )
        ]
    )

    result = VerdictGenerator().generate(
        _agree_triangulation(), _relative_mock(), Security(ticker="TEST"), law_report=law_report
    )
    assert result.rating == "BUY"
    assert result.confidence_band == "MEDIUM"
    assert any("LAW 2 VIOLATED" in n for n in result.notes)


def test_verdict_drops_two_levels_on_severe_law_breaks():
    """Two violations push the multiplier to the hard threshold (0.70),
    stepping the band down two levels (HIGH -> LOW)."""
    from iam.laws.types import LawCheck, LawReport, LawStatus

    law_report = LawReport(
        checks=[
            LawCheck(number=2, name="growth_requires_reinvestment", status=LawStatus.VIOLATION),
            LawCheck(number=3, name="terminal_growth_ceiling", status=LawStatus.VIOLATION),
        ]
    )

    result = VerdictGenerator().generate(
        _agree_triangulation(), _relative_mock(), Security(ticker="TEST"), law_report=law_report
    )
    assert result.confidence_band == "LOW"


def test_verdict_unchanged_on_clean_law_report():
    from iam.laws.types import LawCheck, LawReport, LawStatus

    law_report = LawReport(
        checks=[LawCheck(number=3, name="terminal_growth_ceiling", status=LawStatus.PASS)]
    )

    result = VerdictGenerator().generate(
        _agree_triangulation(), _relative_mock(), Security(ticker="TEST"), law_report=law_report
    )
    assert result.confidence_band == "HIGH"
    assert not any("LAW" in n for n in result.notes)


def test_verdict_downgrades_on_conviction_drift():
    from iam.elasticity.types import (
        DurabilityScore,
        ElasticityProfile,
        StressResponse,
        StressScenario,
    )

    response = StressResponse(
        scenario=StressScenario(name="Rate Hike"),
        base_fair_value=100.0,
        stressed_fair_value=60.0,
        value_change_pct=-0.40,
        durability=DurabilityScore(score=0.2, confidence=0.8),
        elasticity=ElasticityProfile(growth_elasticity=1.5, rate_elasticity=2.0, confidence=0.9),
        conviction_drift=0.32,
    )

    result = VerdictGenerator().generate(
        _agree_triangulation(), _relative_mock(), Security(ticker="TEST"), stress_response=response
    )
    assert result.confidence_band == "MEDIUM"
    assert any("conviction" in n.lower() and "drift" in n.lower() for n in result.notes)


def test_verdict_drops_to_low_on_severe_drift():
    from iam.elasticity.types import (
        DurabilityScore,
        ElasticityProfile,
        StressResponse,
        StressScenario,
    )

    response = StressResponse(
        scenario=StressScenario(name="Stagflation"),
        base_fair_value=100.0,
        stressed_fair_value=30.0,
        value_change_pct=-0.70,
        durability=DurabilityScore(score=0.1, confidence=0.8),
        elasticity=ElasticityProfile(growth_elasticity=2.0, rate_elasticity=2.5, confidence=0.9),
        conviction_drift=0.63,
    )

    result = VerdictGenerator().generate(
        _agree_triangulation(), _relative_mock(), Security(ticker="TEST"), stress_response=response
    )
    assert result.confidence_band == "LOW"


def test_verdict_ignores_small_drift():
    from iam.elasticity.types import (
        DurabilityScore,
        ElasticityProfile,
        StressResponse,
        StressScenario,
    )

    response = StressResponse(
        scenario=StressScenario(name="Rate Hike"),
        base_fair_value=100.0,
        stressed_fair_value=95.0,
        value_change_pct=-0.05,
        durability=DurabilityScore(score=0.9, confidence=0.9),
        elasticity=ElasticityProfile(growth_elasticity=1.0, rate_elasticity=0.8, confidence=0.9),
        conviction_drift=0.005,
    )

    result = VerdictGenerator().generate(
        _agree_triangulation(), _relative_mock(), Security(ticker="TEST"), stress_response=response
    )
    assert result.confidence_band == "HIGH"
