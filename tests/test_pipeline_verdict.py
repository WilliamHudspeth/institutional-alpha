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
