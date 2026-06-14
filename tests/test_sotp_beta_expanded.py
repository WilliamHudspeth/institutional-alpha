import pytest
import shutil
from dataclasses import dataclass
from typing import List
from iam.valuation.sotp import SOTP, Segment, SOTPResult
from iam.engine.damodaran import DamodaranEngine
from iam.ui.sotp_tower import render_sotp_tower
from iam.data.security import Security, Fundamentals, MarketData

# ==============================================================================
# SECTION 1: Segment Dataclass Field and Instantiation Tests (1 to 10)
# ==============================================================================

def test_segment_field_name():
    s = Segment("SegA", 100, 50, 1.2, 0.21, 0.05, 40)
    assert s.name == "SegA"

def test_segment_field_revenue():
    s = Segment("SegA", 100, 50, 1.2, 0.21, 0.05, 40)
    assert s.revenue == 100

def test_segment_field_ebit():
    s = Segment("SegA", 100, 50, 1.2, 0.21, 0.05, 40)
    assert s.ebit == 50

def test_segment_field_unlevered_beta():
    s = Segment("SegA", 100, 50, 1.2, 0.21, 0.05, 40)
    assert s.unlevered_beta == 1.2

def test_segment_field_tax_rate():
    s = Segment("SegA", 100, 50, 1.2, 0.21, 0.05, 40)
    assert s.tax_rate == 0.21

def test_segment_field_growth_rate():
    s = Segment("SegA", 100, 50, 1.2, 0.21, 0.05, 40)
    assert s.growth_rate == 0.05

def test_segment_field_fcfe():
    s = Segment("SegA", 100, 50, 1.2, 0.21, 0.05, 40)
    assert s.fcfe == 40

def test_segment_mutability():
    s = Segment("SegA", 100, 50, 1.2, 0.21, 0.05, 40)
    s.revenue = 150
    assert s.revenue == 150

def test_segment_type_annotations():
    assert Segment.__annotations__['name'] == str
    assert Segment.__annotations__['revenue'] == float

def test_segment_representation():
    s = Segment("SegA", 100.0, 50.0, 1.2, 0.21, 0.05, 40.0)
    assert "SegA" in repr(s)


# ==============================================================================
# SECTION 2: SOTP Compute Logic - Basic Calculations (11 to 20)
# ==============================================================================

def test_sotp_single_segment_ev():
    seg = Segment("A", 1000, 200, 1.0, 0.2, 0.02, 100)
    res = SOTP.compute([seg], cost_of_equity=0.10)
    # ev = 100 * (1 + 0.02) / (0.10 - 0.02) = 102 / 0.08 = 1275
    assert res.total_ev == 1275.0

def test_sotp_single_segment_beta_contrib():
    seg = Segment("A", 1000, 200, 1.5, 0.2, 0.02, 100)
    res = SOTP.compute([seg], cost_of_equity=0.10)
    assert res.segments[0]['beta_contribution'] == 1.5

def test_sotp_weighted_beta_single():
    seg = Segment("A", 1000, 200, 1.5, 0.2, 0.02, 100)
    res = SOTP.compute([seg], cost_of_equity=0.10)
    assert res.weighted_unlevered_beta == 1.5

def test_sotp_multi_segment_beta_weighting():
    segs = [
        Segment("A", 600, 100, 0.8, 0.2, 0.02, 50),
        Segment("B", 400, 100, 1.3, 0.2, 0.02, 50),
    ]
    res = SOTP.compute(segs, cost_of_equity=0.10)
    # (600*0.8 + 400*1.3) / 1000 = (480 + 520) / 1000 = 1.0
    assert res.weighted_unlevered_beta == 1.0

def test_sotp_multi_segment_beta_contributions():
    segs = [
        Segment("A", 600, 100, 0.8, 0.2, 0.02, 50),
        Segment("B", 400, 100, 1.3, 0.2, 0.02, 50),
    ]
    res = SOTP.compute(segs, cost_of_equity=0.10)
    assert res.segments[0]['beta_contribution'] == 0.48
    assert res.segments[1]['beta_contribution'] == 0.52

def test_sotp_multi_segment_ev_sum():
    segs = [
        Segment("A", 500, 100, 1.0, 0.2, 0.05, 100), # ke=10% -> 100 * 1.05 / 0.05 = 2100
        Segment("B", 500, 100, 1.0, 0.2, 0.00, 50),  # ke=10% -> 50 * 1.00 / 0.10 = 500
    ]
    res = SOTP.compute(segs, cost_of_equity=0.10)
    assert res.total_ev == 2600.0

def test_sotp_growth_scaling():
    seg = Segment("A", 1000, 200, 1.0, 0.2, 0.04, 100)
    res1 = SOTP.compute([seg], cost_of_equity=0.08) # 100 * 1.04 / 0.04 = 2600
    res2 = SOTP.compute([seg], cost_of_equity=0.09) # 100 * 1.04 / 0.05 = 2080
    assert res1.total_ev > res2.total_ev

def test_sotp_result_segment_list_size():
    segs = [Segment("A", 100, 10, 1, 0.2, 0.01, 10), Segment("B", 200, 20, 1, 0.2, 0.01, 15)]
    res = SOTP.compute(segs, 0.1)
    assert len(res.segments) == 2

def test_sotp_unlevered_beta_is_zero():
    seg = Segment("A", 100, 20, 0.0, 0.2, 0.02, 10)
    res = SOTP.compute([seg], cost_of_equity=0.1)
    assert res.weighted_unlevered_beta == 0.0

def test_sotp_weighted_unlevered_beta_precision():
    segs = [
        Segment("A", 333, 10, 0.77, 0.2, 0.02, 10),
        Segment("B", 667, 10, 1.15, 0.2, 0.02, 10),
    ]
    res = SOTP.compute(segs, cost_of_equity=0.1)
    expected = (333*0.77 + 667*1.15) / 1000
    assert abs(res.weighted_unlevered_beta - expected) < 1e-7


# ==============================================================================
# SECTION 3: SOTP Compute Logic - Edge cases (21 to 30)
# ==============================================================================

def test_sotp_zero_revenue_handling_beta():
    segs = [Segment("A", 0, 10, 1.0, 0.2, 0.02, 10)]
    res = SOTP.compute(segs, 0.1)
    assert res.weighted_unlevered_beta == 0.0

def test_sotp_zero_revenue_handling_contrib():
    segs = [Segment("A", 0, 10, 1.0, 0.2, 0.02, 10)]
    res = SOTP.compute(segs, 0.1)
    assert res.segments[0]['beta_contribution'] == 0.0

def test_sotp_empty_segment_list():
    res = SOTP.compute([], 0.1)
    assert res.total_ev == 0.0
    assert res.weighted_unlevered_beta == 0.0
    assert len(res.segments) == 0

def test_sotp_growth_rate_equal_cost_of_equity():
    seg = Segment("A", 100, 20, 1.0, 0.2, 0.10, 10)
    res = SOTP.compute([seg], cost_of_equity=0.10)
    assert res.segments[0]['ev'] == float('inf')
    assert res.total_ev == float('inf')

def test_sotp_growth_rate_exceeds_cost_of_equity():
    seg = Segment("A", 100, 20, 1.0, 0.2, 0.12, 10)
    res = SOTP.compute([seg], cost_of_equity=0.10)
    assert res.segments[0]['ev'] == float('inf')
    assert res.total_ev == float('inf')

def test_sotp_negative_growth_rate():
    seg = Segment("A", 100, 20, 1.0, 0.2, -0.05, 10)
    res = SOTP.compute([seg], cost_of_equity=0.10)
    # ev = 10 * (1 - 0.05) / (0.10 - (-0.05)) = 9.5 / 0.15 = 63.333
    assert abs(res.total_ev - 63.333333333333336) < 1e-5

def test_sotp_negative_fcfe():
    seg = Segment("A", 100, 20, 1.0, 0.2, 0.02, -50)
    res = SOTP.compute([seg], cost_of_equity=0.10)
    # ev = -50 * 1.02 / 0.08 = -637.5
    assert res.total_ev == -637.5

def test_sotp_extremely_high_cost_of_equity():
    seg = Segment("A", 100, 20, 1.0, 0.2, 0.02, 10)
    res = SOTP.compute([seg], cost_of_equity=10.0)
    # ev = 10 * 1.02 / (10.0 - 0.02) = 10.2 / 9.98 = 1.022
    assert abs(res.total_ev - 1.022044) < 1e-4

def test_sotp_multiple_infinite_segments():
    segs = [
        Segment("A", 100, 20, 1.0, 0.2, 0.10, 10),
        Segment("B", 100, 20, 1.0, 0.2, 0.15, 10),
    ]
    res = SOTP.compute(segs, cost_of_equity=0.10)
    assert res.total_ev == float('inf')

def test_sotp_finite_and_infinite_segments():
    segs = [
        Segment("A", 100, 20, 1.0, 0.2, 0.05, 10),
        Segment("B", 100, 20, 1.0, 0.2, 0.10, 10),
    ]
    res = SOTP.compute(segs, cost_of_equity=0.10)
    assert res.total_ev == float('inf')


# ==============================================================================
# SECTION 4: Damodaran Engine - Weighted Beta logic (31 to 45)
# ==============================================================================

def test_damodaran_engine_default_initialization():
    engine = DamodaranEngine()
    assert engine.rf == 0.04
    assert engine.erp == 0.05

def test_damodaran_engine_custom_rates():
    engine = DamodaranEngine(risk_free_rate=0.03, equity_risk_premium=0.06)
    assert engine.rf == 0.03
    assert engine.erp == 0.06

def test_damodaran_engine_beta_u_single_segment():
    engine = DamodaranEngine()
    segs = [Segment("A", 1000, 100, 1.2, 0.21, 0.05, 50)]
    # D/E = 0.0 -> Beta_L = Beta_U = 1.2
    ke = engine.compute_cost_of_equity(segs, debt_to_equity=0.0)
    expected_ke = 0.04 + 1.2 * 0.05
    assert abs(ke - expected_ke) < 1e-7

def test_damodaran_engine_beta_u_multi_segments():
    engine = DamodaranEngine()
    segs = [
        Segment("A", 4000, 100, 0.8, 0.21, 0.05, 50),
        Segment("B", 6000, 100, 1.3, 0.21, 0.05, 50),
    ]
    # Weighted Beta_U = (4000*0.8 + 6000*1.3) / 10000 = (3200 + 7800) / 10000 = 1.1
    # D/E = 0.0 -> Beta_L = 1.1
    # Ke = 0.04 + 1.1 * 0.05 = 0.095
    ke = engine.compute_cost_of_equity(segs, debt_to_equity=0.0)
    assert abs(ke - 0.095) < 1e-7

def test_damodaran_engine_beta_u_zero_revenue_fallback():
    engine = DamodaranEngine()
    segs = [Segment("A", 0, 100, 1.2, 0.21, 0.05, 50)]
    # Weighted Beta_U fallback is 1.0 when total revenue is 0
    ke = engine.compute_cost_of_equity(segs, debt_to_equity=0.0)
    expected_ke = 0.04 + 1.0 * 0.05
    assert abs(ke - 0.09) < 1e-7

def test_damodaran_engine_beta_l_zero_debt():
    engine = DamodaranEngine()
    segs = [Segment("A", 100, 10, 1.0, 0.21, 0.02, 10)]
    ke = engine.compute_cost_of_equity(segs, debt_to_equity=0.0)
    # beta_l = 1.0 * (1 + 0.79 * 0.0) = 1.0
    # ke = 0.04 + 1.0 * 0.05 = 0.09
    assert abs(ke - 0.09) < 1e-7

def test_damodaran_engine_beta_l_positive_debt():
    engine = DamodaranEngine()
    segs = [Segment("A", 100, 10, 1.0, 0.21, 0.02, 10)]
    ke = engine.compute_cost_of_equity(segs, debt_to_equity=0.5)
    # beta_l = 1.0 * (1 + 0.79 * 0.5) = 1.395
    # ke = 0.04 + 1.395 * 0.05 = 0.10975
    assert abs(ke - 0.10975) < 1e-7

def test_damodaran_engine_beta_l_custom_tax_rate():
    engine = DamodaranEngine()
    segs = [Segment("A", 100, 10, 1.0, 0.30, 0.02, 10)]
    ke = engine.compute_cost_of_equity(segs, debt_to_equity=0.5, tax_rate=0.30)
    # beta_l = 1.0 * (1 + (1 - 0.30) * 0.5) = 1.0 * (1 + 0.35) = 1.35
    # ke = 0.04 + 1.35 * 0.05 = 0.1075
    assert abs(ke - 0.1075) < 1e-7

def test_damodaran_engine_beta_l_negative_debt_to_equity():
    engine = DamodaranEngine()
    segs = [Segment("A", 100, 10, 1.0, 0.21, 0.02, 10)]
    ke = engine.compute_cost_of_equity(segs, debt_to_equity=-0.2)
    # beta_l = 1.0 * (1 + 0.79 * -0.2) = 1.0 * (1 - 0.158) = 0.842
    # ke = 0.04 + 0.842 * 0.05 = 0.0821
    assert abs(ke - 0.0821) < 1e-7

def test_damodaran_engine_beta_l_very_high_debt():
    engine = DamodaranEngine()
    segs = [Segment("A", 100, 10, 1.0, 0.20, 0.02, 10)]
    ke = engine.compute_cost_of_equity(segs, debt_to_equity=10.0, tax_rate=0.20)
    # beta_l = 1.0 * (1 + 0.8 * 10) = 9.0
    # ke = 0.04 + 9.0 * 0.05 = 0.49
    assert abs(ke - 0.49) < 1e-7

def test_damodaran_engine_beta_l_full_tax_shield():
    engine = DamodaranEngine()
    segs = [Segment("A", 100, 10, 1.0, 1.0, 0.02, 10)]
    # tax_rate = 1.0 -> (1 - tax_rate) = 0 -> beta_l = beta_u regardless of D/E
    ke = engine.compute_cost_of_equity(segs, debt_to_equity=2.0, tax_rate=1.0)
    assert abs(ke - 0.09) < 1e-7

def test_damodaran_engine_negative_unlevered_beta():
    engine = DamodaranEngine()
    segs = [Segment("A", 100, 10, -0.5, 0.20, 0.02, 10)]
    ke = engine.compute_cost_of_equity(segs, debt_to_equity=0.0)
    # ke = 0.04 - 0.5 * 0.05 = 0.015
    assert abs(ke - 0.015) < 1e-7

def test_damodaran_engine_negative_rf():
    engine = DamodaranEngine(risk_free_rate=-0.01)
    segs = [Segment("A", 100, 10, 1.0, 0.20, 0.02, 10)]
    ke = engine.compute_cost_of_equity(segs, debt_to_equity=0.0)
    # ke = -0.01 + 1.0 * 0.05 = 0.04
    assert abs(ke - 0.04) < 1e-7

def test_damodaran_engine_zero_erp():
    engine = DamodaranEngine(equity_risk_premium=0.0)
    segs = [Segment("A", 100, 10, 1.5, 0.20, 0.02, 10)]
    ke = engine.compute_cost_of_equity(segs, debt_to_equity=1.0)
    # ke = 0.04 + beta_l * 0.0 = 0.04
    assert ke == 0.04

def test_damodaran_engine_large_segment_count():
    engine = DamodaranEngine()
    segs = [Segment(f"S{i}", 100, 10, 1.0, 0.21, 0.02, 5) for i in range(100)]
    ke = engine.compute_cost_of_equity(segs, debt_to_equity=0.0)
    assert abs(ke - 0.09) < 1e-7


# ==============================================================================
# SECTION 5: Damodaran Engine - Compute Pipeline Integration (46 to 60)
# ==============================================================================

def test_damodaran_engine_compute_missing_fundamentals():
    sec = Security("AAPL")
    engine = DamodaranEngine()
    res = engine.compute(sec)
    assert res.confidence == 0.0
    assert "Missing required" in res.narrative

def test_damodaran_engine_compute_negative_fcfe():
    sec = Security("AAPL")
    sec.market.price = 150.0
    sec.fundamentals.shares_outstanding = 100.0
    sec.fundamentals.fcf_ttm = -50.0
    engine = DamodaranEngine()
    res = engine.compute(sec)
    assert res.confidence == 0.2
    assert "Base FCFE non-positive" in res.narrative

def test_damodaran_engine_compute_fallback_growth():
    sec = Security("AAPL")
    sec.market.price = 100.0
    sec.fundamentals.shares_outstanding = 10.0
    sec.fundamentals.fcf_ttm = 100.0
    engine = DamodaranEngine()
    res = engine.compute(sec)
    # Should run with default growth 8%
    assert res.assumptions["g_high"] == 0.08

def test_damodaran_engine_compute_custom_forecast_growth():
    sec = Security("AAPL")
    sec.market.price = 100.0
    sec.fundamentals.shares_outstanding = 10.0
    sec.fundamentals.fcf_ttm = 100.0
    sec.qualitative["forecast_growth"] = 0.12
    engine = DamodaranEngine()
    res = engine.compute(sec)
    assert res.assumptions["g_high"] == 0.12

def test_damodaran_engine_compute_custom_terminal_growth():
    sec = Security("AAPL")
    sec.market.price = 100.0
    sec.fundamentals.shares_outstanding = 10.0
    sec.fundamentals.fcf_ttm = 100.0
    sec.qualitative["forecast_terminal_growth"] = 0.03
    engine = DamodaranEngine()
    res = engine.compute(sec)
    assert res.assumptions["g_terminal"] == 0.03

def test_damodaran_engine_compute_with_segments_uses_ke():
    sec = Security("AAPL")
    sec.market.price = 100.0
    sec.fundamentals.shares_outstanding = 10.0
    sec.fundamentals.fcf_ttm = 100.0
    sec.fundamentals.total_debt = 50.0
    sec.market.market_cap = 100.0
    # D/E ratio = 50 / 100 = 0.5
    # Segment weighted beta = 1.0 -> beta_l = 1.0 * (1 + 0.79 * 0.5) = 1.395
    # ke = 0.04 + 1.395 * 0.05 = 0.10975
    sec.qualitative["segments"] = [Segment("Core", 1000, 100, 1.0, 0.21, 0.02, 50)]
    engine = DamodaranEngine()
    res = engine.compute(sec)
    assert abs(res.assumptions["wacc"] - 0.10975) < 1e-5

def test_damodaran_engine_compute_with_qualitative_de_ratio():
    sec = Security("AAPL")
    sec.market.price = 100.0
    sec.fundamentals.shares_outstanding = 10.0
    sec.fundamentals.fcf_ttm = 100.0
    sec.qualitative["current_de_ratio"] = 0.8
    sec.qualitative["segments"] = [Segment("Core", 1000, 100, 1.0, 0.21, 0.02, 50)]
    engine = DamodaranEngine()
    res = engine.compute(sec)
    # beta_l = 1.0 * (1 + 0.79 * 0.8) = 1.632
    # ke = 0.04 + 1.632 * 0.05 = 0.1216
    assert abs(res.assumptions["wacc"] - 0.1216) < 1e-5

def test_damodaran_engine_compute_with_balance_sheet_mock():
    @dataclass
    class BalanceSheetMock:
        debt_to_equity: float

    sec = Security("AAPL")
    sec.market.price = 100.0
    sec.fundamentals.shares_outstanding = 10.0
    sec.fundamentals.fcf_ttm = 100.0
    sec.balance_sheet = BalanceSheetMock(debt_to_equity=0.4)
    sec.qualitative["segments"] = [Segment("Core", 1000, 100, 1.0, 0.21, 0.02, 50)]
    engine = DamodaranEngine()
    res = engine.compute(sec)
    # beta_l = 1.0 * (1 + 0.79 * 0.4) = 1.316
    # ke = 0.04 + 1.316 * 0.05 = 0.1058
    assert abs(res.assumptions["wacc"] - 0.1058) < 1e-5

def test_damodaran_engine_compute_discount_rate_limit_low_pv():
    # When discount rate <= terminal growth, pv calculation will fail gracefully
    sec = Security("AAPL")
    sec.market.price = 100.0
    sec.fundamentals.shares_outstanding = 10.0
    sec.fundamentals.fcf_ttm = 10.0
    sec.qualitative["forecast_terminal_growth"] = 0.15 # Higher than WACC (0.09)
    engine = DamodaranEngine()
    res = engine.compute(sec)
    assert res.confidence == 0.0
    assert "Bad assumptions" in res.narrative

def test_damodaran_engine_compute_implied_move():
    sec = Security("AAPL")
    sec.market.price = 10.0
    sec.fundamentals.shares_outstanding = 1.0
    # base FCF = 1.0. With WACC=9%, growth=8%, term=2.5%
    sec.fundamentals.fcf_ttm = 1.0
    engine = DamodaranEngine()
    res = engine.compute(sec)
    assert res.implied_move_pct is not None
    assert isinstance(res.implied_move_pct, float)

def test_damodaran_engine_compute_fair_value_bounds():
    sec = Security("AAPL")
    sec.market.price = 10.0
    sec.fundamentals.shares_outstanding = 1.0
    sec.fundamentals.fcf_ttm = 1.0
    engine = DamodaranEngine()
    res = engine.compute(sec)
    assert res.fair_value_low < res.fair_value_high

def test_damodaran_engine_compute_wacc_plus_minus_one_percent():
    sec = Security("AAPL")
    sec.market.price = 10.0
    sec.fundamentals.shares_outstanding = 1.0
    sec.fundamentals.fcf_ttm = 1.0
    engine = DamodaranEngine()
    res = engine.compute(sec)
    # Low PV is evaluated at WACC + 1% (meaning it should be lower value)
    # High PV is evaluated at WACC - 1% (meaning it should be higher value)
    assert res.fair_value_low < res.fair_value_high

def test_damodaran_engine_confidence_rating():
    sec = Security("AAPL")
    sec.market.price = 100.0
    sec.fundamentals.shares_outstanding = 10.0
    sec.fundamentals.fcf_ttm = 100.0
    engine = DamodaranEngine()
    res = engine.compute(sec)
    assert res.confidence == 0.85

def test_damodaran_engine_name():
    engine = DamodaranEngine()
    assert engine.name == "damodaran_engine"

def test_damodaran_engine_compute_zero_shares_handling():
    sec = Security("AAPL")
    sec.market.price = 10.0
    sec.fundamentals.shares_outstanding = 0.0
    sec.fundamentals.fcf_ttm = 100.0
    engine = DamodaranEngine()
    res = engine.compute(sec)
    assert res.confidence == 0.0


# ==============================================================================
# SECTION 6: SOTP Tower Terminal Rendering Tests (61 to 70)
# ==============================================================================

def test_sotp_tower_render_empty():
    res = render_sotp_tower([])
    assert res == "No valuation data."

def test_sotp_tower_render_zero_ev():
    res = render_sotp_tower([{'name': 'A', 'ev': 0.0}])
    assert res == "No valuation data."

def test_sotp_tower_single_segment():
    res = render_sotp_tower([{'name': 'iShares', 'ev': 100.0}])
    # Tower should contain block characters
    assert '█' in res
    assert 'iShares' in res
    assert '$100' in res

def test_sotp_tower_multi_segments():
    segs = [{'name': 'iShares', 'ev': 5000.0}, {'name': 'Aladdin', 'ev': 3000.0}]
    res = render_sotp_tower(segs)
    assert 'iShares' in res
    assert 'Aladdin' in res
    assert '$5,000' in res
    assert '$3,000' in res

def test_sotp_tower_heights_stacking_order():
    segs = [{'name': 'A', 'ev': 1000.0}, {'name': 'B', 'ev': 5000.0}]
    res = render_sotp_tower(segs)
    lines = res.split('\n')
    # Since print order is top-to-bottom and lines are reversed at return,
    # the last segment in the list (B) should stack on top or bottom.
    # The code reverses: lines.reverse()
    # So index 0 segment ('A') is processed first, added to lines, then index 1 ('B') added.
    # Reversing lines puts segment 'B' lines at the beginning (top of output).
    assert 'B' in lines[0]
    assert 'A' in lines[-1]

def test_sotp_tower_long_name_truncation():
    segs = [{'name': 'VeryLongSegmentNameMoreThanTenChars', 'ev': 100.0}]
    res = render_sotp_tower(segs)
    assert 'VeryLongSe' in res
    assert 'MoreThanTen' not in res

def test_sotp_tower_block_width():
    segs = [{'name': 'A', 'ev': 100.0}]
    res = render_sotp_tower(segs)
    lines = res.split('\n')
    assert len(lines[0]) > 10

def test_sotp_tower_scaling_under_max_height():
    # Ensure factor scales segments to sum to max_height (20)
    segs = [{'name': 'A', 'ev': 100.0}, {'name': 'B', 'ev': 100.0}]
    res = render_sotp_tower(segs)
    lines = res.split('\n')
    assert len(lines) == 20

def test_sotp_tower_extreme_imbalance_height_allocation():
    # One huge segment, one tiny segment. Tiny should get at least height=1.
    segs = [{'name': 'A', 'ev': 100000.0}, {'name': 'B', 'ev': 1.0}]
    res = render_sotp_tower(segs)
    lines = res.split('\n')
    a_lines = [l for l in lines if 'A' in l]
    b_lines = [l for l in lines if 'B' in l]
    assert len(a_lines) == 19
    assert len(b_lines) == 1

def test_sotp_tower_negative_ev_handling():
    # If EV is negative or zero, it won't crash but will skip or return default.
    segs = [{'name': 'A', 'ev': -50.0}, {'name': 'B', 'ev': 100.0}]
    # Sum total_ev = 50. Heights proportional to EV.
    res = render_sotp_tower(segs)
    assert 'A' in res
    assert 'B' in res


# ==============================================================================
# SECTION 7: End-to-End and Integration Scenarios (71 to 80)
# ==============================================================================

def test_integration_full_workflow():
    # Step 1: Create security
    sec = Security("BLK", name="BlackRock")
    sec.market.price = 800.0
    sec.fundamentals.shares_outstanding = 1.5 # in millions
    sec.fundamentals.fcf_ttm = 3000.0
    
    # Step 2: Define qualitative segments
    sec.qualitative["segments"] = [
        Segment("iShares", revenue=5000, ebit=2000, unlevered_beta=0.60, tax_rate=0.21, growth_rate=0.04, fcfe=1500),
        Segment("Aladdin", revenue=3000, ebit=1500, unlevered_beta=1.14, tax_rate=0.21, growth_rate=0.05, fcfe=1100),
        Segment("PrivateMkt", revenue=2000, ebit=900, unlevered_beta=0.95, tax_rate=0.21, growth_rate=0.03, fcfe=700),
    ]
    
    # Step 3: Damodaran Engine WACC compute
    engine = DamodaranEngine()
    res = engine.compute(sec)
    
    # Check that dynamic WACC was calculated
    assert res.assumptions["wacc"] > 0.05
    assert res.assumptions["wacc"] < 0.15

def test_integration_sotp_valuation_with_dynamic_ke():
    sec = Security("BLK")
    sec.qualitative["segments"] = [
        Segment("iShares", revenue=5000, ebit=2000, unlevered_beta=0.60, tax_rate=0.21, growth_rate=0.04, fcfe=1500),
        Segment("Aladdin", revenue=3000, ebit=1500, unlevered_beta=1.14, tax_rate=0.21, growth_rate=0.05, fcfe=1100),
    ]
    engine = DamodaranEngine()
    ke = engine.compute_cost_of_equity(sec.qualitative["segments"], debt_to_equity=0.2)
    sotp_res = SOTP.compute(sec.qualitative["segments"], cost_of_equity=ke)
    assert sotp_res.total_ev > 0
    assert len(sotp_res.segments) == 2

def test_integration_render_from_computed_sotp():
    segs = [
        Segment("S1", 100, 10, 1.0, 0.2, 0.02, 10),
        Segment("S2", 200, 20, 1.2, 0.2, 0.03, 20),
    ]
    sotp_res = SOTP.compute(segs, cost_of_equity=0.10)
    tower = render_sotp_tower(sotp_res.segments)
    assert "S1" in tower
    assert "S2" in tower

def test_integration_relevered_beta_comparison():
    engine = DamodaranEngine()
    segs = [Segment("A", 1000, 100, 1.0, 0.21, 0.02, 50)]
    # High leverage vs Low leverage
    ke_high = engine.compute_cost_of_equity(segs, debt_to_equity=1.5)
    ke_low = engine.compute_cost_of_equity(segs, debt_to_equity=0.2)
    assert ke_high > ke_low

def test_integration_tax_rate_effect_on_ke():
    engine = DamodaranEngine()
    segs = [Segment("A", 1000, 100, 1.0, 0.40, 0.02, 50)]
    # Higher tax rate means lower levered beta (due to larger tax shield)
    # beta_l = beta_u * (1 + (1 - tax) * D/E)
    ke_high_tax = engine.compute_cost_of_equity(segs, debt_to_equity=1.0, tax_rate=0.40)
    ke_low_tax = engine.compute_cost_of_equity(segs, debt_to_equity=1.0, tax_rate=0.10)
    assert ke_high_tax < ke_low_tax

def test_integration_growth_rate_approaching_ke_bound():
    # If growth rate matches Ke exactly, SOTP returns infinite EV.
    # Let's ensure this is handled without Python throwing a ZeroDivisionError.
    seg = Segment("A", 100, 10, 1.0, 0.2, 0.10, 10)
    try:
        res = SOTP.compute([seg], cost_of_equity=0.10)
        assert res.total_ev == float('inf')
    except ZeroDivisionError:
        pytest.fail("SOTP.compute raised ZeroDivisionError!")

def test_integration_segment_revenue_mix_scale():
    segs = [
        Segment("A", 1e9, 1e7, 1.0, 0.2, 0.02, 1e6),
        Segment("B", 2e9, 2e7, 1.5, 0.2, 0.02, 2e6),
    ]
    res = SOTP.compute(segs, cost_of_equity=0.10)
    # Weighted average: (1e9 * 1.0 + 2e9 * 1.5) / 3e9 = (1.0 + 3.0) / 3 = 1.3333...
    assert abs(res.weighted_unlevered_beta - 1.33333333) < 1e-6

def test_integration_sotp_valuation_formatting():
    segs = [{'name': 'TestSeg', 'ev': 1234567.89}]
    tower = render_sotp_tower(segs)
    # Should format EV with commas and no decimals: $1,234,568
    assert '$1,234,568' in tower

def test_integration_damodaran_engine_with_none_debt():
    sec = Security("AAPL")
    sec.market.price = 100.0
    sec.fundamentals.shares_outstanding = 10.0
    sec.fundamentals.fcf_ttm = 100.0
    sec.fundamentals.total_debt = None
    sec.market.market_cap = 100.0
    sec.qualitative["segments"] = [Segment("Core", 1000, 100, 1.0, 0.21, 0.02, 50)]
    engine = DamodaranEngine()
    res = engine.compute(sec)
    # debt=None behaves as debt=0
    assert abs(res.assumptions["wacc"] - 0.09) < 1e-5

def test_integration_damodaran_engine_with_none_market_cap():
    sec = Security("AAPL")
    sec.market.price = 100.0
    sec.fundamentals.shares_outstanding = 10.0
    sec.fundamentals.fcf_ttm = 100.0
    sec.fundamentals.total_debt = 50.0
    sec.market.market_cap = None
    sec.qualitative["segments"] = [Segment("Core", 1000, 100, 1.0, 0.21, 0.02, 50)]
    engine = DamodaranEngine()
    res = engine.compute(sec)
    # market_cap=None behaves as market_cap=1.0, giving D/E = 50 / 1.0 = 50.0
    assert res.assumptions["wacc"] > 0.5
