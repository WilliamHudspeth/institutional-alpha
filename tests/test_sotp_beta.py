from iam.engine.damodaran import DamodaranEngine
from iam.valuation.sotp import SOTP, Segment


def test_sotp_and_bottom_up_beta():
    # Setup test segments (Page 6/7 BLK methodology parameters)
    segments = [
        Segment(
            "iShares",
            revenue=5000,
            ebit=2000,
            unlevered_beta=0.60,
            tax_rate=0.21,
            growth_rate=0.04,
            fcfe=1500,
        ),
        Segment(
            "Aladdin",
            revenue=3000,
            ebit=1500,
            unlevered_beta=1.14,
            tax_rate=0.21,
            growth_rate=0.05,
            fcfe=1100,
        ),
        Segment(
            "GIP",
            revenue=2000,
            ebit=900,
            unlevered_beta=0.95,
            tax_rate=0.21,
            growth_rate=0.03,
            fcfe=700,
        ),
        Segment(
            "HPS",
            revenue=1000,
            ebit=400,
            unlevered_beta=1.05,
            tax_rate=0.21,
            growth_rate=0.04,
            fcfe=300,
        ),
    ]

    # Calculate weighted average unlevered beta
    total_revenue = sum(s.revenue for s in segments)
    assert total_revenue == 11000

    # Weighted Unlevered Beta calculation:
    # (5000*0.60 + 3000*1.14 + 2000*0.95 + 1000*1.05) / 11000
    # = (3000 + 3420 + 1900 + 1050) / 11000 = 9370 / 11000 ≈ 0.8518
    weighted_beta_u = sum(s.revenue * s.unlevered_beta for s in segments) / total_revenue
    assert round(weighted_beta_u, 4) == 0.8518

    # Compute cost of equity via DamodaranEngine
    # Rf = 4%, ERP = 5%, D/E = 0.5 (as per prompt instructions / PDF example)
    damodaran = DamodaranEngine(risk_free_rate=0.04, equity_risk_premium=0.05)
    ke = damodaran.compute_cost_of_equity(segments, debt_to_equity=0.5, tax_rate=0.21)

    # beta_l = beta_u * (1 + (1 - tax) * D/E)
    # beta_l = 0.851818... * (1 + 0.79 * 0.5) = 0.851818... * 1.395 = 1.18828
    # ke = 0.04 + 1.18828 * 0.05 = 0.04 + 0.059414 ≈ 0.0994 (9.94%)
    assert round(ke, 4) == 0.0994

    # Compute SOTP values using Ke
    result = SOTP.compute(segments, cost_of_equity=ke)
    assert round(result.weighted_unlevered_beta, 4) == 0.8518
    assert len(result.segments) == 4

    # Check EV calculations for segments
    # iShares: EV = 1500 * 1.04 / (0.099414 - 0.04) = 1560 / 0.059414 ≈ 26256
    # Aladdin: EV = 1100 * 1.05 / (0.099414 - 0.05) = 1155 / 0.049414 ≈ 23374
    ishares_ev = [item["ev"] for item in result.segments if item["name"] == "iShares"][0]
    assert round(ishares_ev, 0) == 26256
