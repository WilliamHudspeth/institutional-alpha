from iam.data.security import Fundamentals, MarketData, Security
from iam.valuation.damodaran_defaults import DamodaranUniverse
from iam.valuation.relative import RelativeValuation


def test_relative_valuation_logic():
    universe = DamodaranUniverse(
        us_erp=0.05,
        region_erps={},
        sector_beta_u={},
        sector_multiples={"Tech": {"ev_ebitda": 10.0, "pe": 20.0}},
    )
    sec = Security(
        ticker="TEST",
        sector="Tech",
        fundamentals=Fundamentals(ebitda_ttm=100, net_income_ttm=50, shares_outstanding=10),
        market=MarketData(price=100.0),
    )

    engine = RelativeValuation(universe)
    result = engine.compute(sec)

    assert result.fair_value_per_share is not None
    assert result.confidence > 0
