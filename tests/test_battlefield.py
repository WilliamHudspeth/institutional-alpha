from iam.pipeline.battlefield import (
    ParamVector,
    attribute_disagreement,
    build_battlefield,
    intrinsic_vector_from_assumptions,
    market_vector_from_implied,
    two_stage_fcfe_value,
)
from iam.valuation.types import ImpliedExpectations, Method, TriangulationResult, ValuationResult


def test_param_vector_mapping():
    implied = ImpliedExpectations(
        implied_revenue_growth=0.08,
        implied_terminal_growth=0.03,
        discount_rate_assumed=0.10,
        implied_roic=0.20,
    )
    mv = market_vector_from_implied(implied)
    assert mv.growth == 0.08
    assert mv.terminal_growth == 0.03
    assert mv.discount_rate == 0.10
    assert mv.roe == 0.20

    assumptions = {
        "high_growth": 0.06,
        "terminal_growth": 0.02,
        "discount_rate": 0.09,
        "roe": 0.18,
    }
    iv = intrinsic_vector_from_assumptions(assumptions)
    assert iv.growth == 0.06
    assert iv.terminal_growth == 0.02
    assert iv.discount_rate == 0.09
    assert iv.roe == 0.18


def test_attribute_disagreement():
    intrinsic = ParamVector(growth=0.06, terminal_growth=0.025, discount_rate=0.09, roe=0.15)
    market = ParamVector(growth=0.12, terminal_growth=0.025, discount_rate=0.09, roe=0.15)

    attr = attribute_disagreement(
        intrinsic=intrinsic,
        market=market,
        value_fn=two_stage_fcfe_value,
    )
    # The disagreement is growth (0.06 vs 0.12).
    assert attr.key_parameter == "growth"
    assert attr.total_gap > 0
    assert len(attr.contributions) > 0
    growth_contrib = [c for c in attr.contributions if c.parameter == "growth"][0]
    assert growth_contrib.share > 0.9  # since only growth differs


def test_attribute_disagreement_agree_short_circuit():
    intrinsic = ParamVector(growth=0.06, terminal_growth=0.025, discount_rate=0.09, roe=0.15)
    market = ParamVector(growth=0.12, terminal_growth=0.025, discount_rate=0.09, roe=0.15)

    triangulation = TriangulationResult(
        verdict="agree", confidence=0.9, cluster_center=0.0, notes=[]
    )

    attr = attribute_disagreement(
        intrinsic=intrinsic,
        market=market,
        value_fn=two_stage_fcfe_value,
        triangulation=triangulation,
        agree_short_circuit=True,
    )
    assert attr.key_disagreement == "NONE — lenses agree"
    assert attr.key_parameter is None
    assert attr.total_gap == 0.0


def test_build_battlefield():
    market_implied = ValuationResult(
        method=Method.REVERSE_DCF,
        confidence=0.8,
        verdict_text="",
        implied=ImpliedExpectations(
            implied_revenue_growth=0.10,
            implied_terminal_growth=0.025,
            discount_rate_assumed=0.09,
            implied_roic=0.15,
        ),
    )
    intrinsic = ValuationResult(
        method=Method.INTRINSIC,
        confidence=0.8,
        verdict_text="",
        assumptions={
            "high_growth": 0.06,
            "terminal_growth": 0.025,
            "discount_rate": 0.09,
            "roe": 0.15,
        },
    )

    attr = build_battlefield(
        market_implied=market_implied,
        intrinsic=intrinsic,
        value_fn=two_stage_fcfe_value,
    )
    assert attr.key_parameter == "growth"
    assert attr.base_value > 0
