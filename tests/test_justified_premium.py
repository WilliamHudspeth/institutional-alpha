"""Unit tests for Justified Premium module (Relative Reality)."""

import pytest

from iam.data.security import Fundamentals, MarketData, Security
from iam.valuation.damodaran_defaults import DamodaranUniverse
from iam.valuation.justified_premium import calculate_justified_premium


class TestJustifiedPremium:
    """Test suite for justified premium calculations."""

    @pytest.fixture
    def basic_universe(self):
        """Create a basic universe with tech sector data."""
        return DamodaranUniverse(
            us_erp=0.05,
            region_erps={},
            sector_beta_u={"Tech": 1.2},
            sector_multiples={
                "Tech": {
                    "ev_ebitda": 12.0,
                    "pe": 20.0,
                    "roic": 0.15,
                    "operating_margin": 0.20,
                }
            },
        )

    def test_justified_premium_basic(self, basic_universe):
        """Test basic justified premium calculation."""
        security = Security(
            ticker="TEST",
            sector="Tech",
            fundamentals=Fundamentals(
                roic_history=[0.18],
                operating_margin=0.22,
                ebitda_ttm=100,
                total_debt=50,
                cash_and_equivalents=20,
                shares_outstanding=10,
            ),
            market=MarketData(price=150.0, ev_ebitda=12.0),
        )

        result = calculate_justified_premium(security, basic_universe)

        assert result.justified_multiple is not None
        assert result.justified_multiple > 0

        # Company has higher ROIC and margin than sector
        # justified_multiple = 12 * (0.18/0.15) * (0.22/0.20)
        # = 12 * 1.2 * 1.1 = 15.84
        expected_justified = 12.0 * (0.18 / 0.15) * (0.22 / 0.20)
        assert abs(result.justified_multiple - expected_justified) < 0.01

    def test_justified_premium_target_price(self, basic_universe):
        """Test target price calculation from justified multiple."""
        security = Security(
            ticker="TEST",
            sector="Tech",
            fundamentals=Fundamentals(
                roic_history=[0.15],
                operating_margin=0.20,
                ebitda_ttm=100,
                total_debt=0,
                cash_and_equivalents=0,
                shares_outstanding=10,
            ),
            market=MarketData(price=120.0, ev_ebitda=12.0),
        )

        result = calculate_justified_premium(security, basic_universe)

        assert result.target_price is not None
        # justified_multiple = 12 * (0.15/0.15) * (0.20/0.20) = 12
        # target_ev = 100 * 12 = 1200
        # target_eq = 1200 - 0 + 0 = 1200
        # target_price = 1200 / 10 = 120
        assert abs(result.target_price - 120.0) < 0.01

    def test_justified_premium_gap(self, basic_universe):
        """Test premium gap calculation."""
        security = Security(
            ticker="TEST",
            sector="Tech",
            fundamentals=Fundamentals(
                roic_history=[0.18],
                operating_margin=0.22,
                ebitda_ttm=100,
                total_debt=0,
                cash_and_equivalents=0,
                shares_outstanding=10,
            ),
            market=MarketData(price=120.0, ev_ebitda=15.0),
        )

        result = calculate_justified_premium(security, basic_universe)

        assert result.actual_premium is not None
        assert result.deserved_premium is not None
        assert result.premium_gap is not None

        # actual_premium = (15.0 / 12.0) - 1 = 0.25 (25% premium)
        # justified_multiple = 12 * (0.18/0.15) * (0.22/0.20) ≈ 15.84
        # deserved_premium = (15.84 / 12.0) - 1 ≈ 0.32 (32% premium)
        # premium_gap = 0.25 - 0.32 ≈ -0.07 (overvalued by -7%)

        assert abs(result.actual_premium - 0.25) < 0.01
        assert result.premium_gap < 0  # Should be overvalued relative to deserving

    def test_justified_premium_no_sector(self):
        """Test handling when sector is not specified."""
        security = Security(
            ticker="TEST",
            sector=None,
            fundamentals=Fundamentals(roic_history=[0.15], operating_margin=0.20),
            market=MarketData(price=120.0, ev_ebitda=12.0),
        )

        result = calculate_justified_premium(security)

        assert result.justified_multiple is None
        assert any("Sector" in note for note in result.notes)

    def test_justified_premium_missing_price(self):
        """Test handling when price is missing."""
        security = Security(
            ticker="TEST",
            sector="Tech",
            fundamentals=Fundamentals(roic_history=[0.15], operating_margin=0.20),
            market=MarketData(price=None, ev_ebitda=12.0),
        )

        result = calculate_justified_premium(security)

        assert result.justified_multiple is None
        assert any("price" in note.lower() for note in result.notes)

    def test_justified_premium_missing_ev_ebitda(self):
        """Test handling when EV/EBITDA is missing."""
        security = Security(
            ticker="TEST",
            sector="Tech",
            fundamentals=Fundamentals(roic_history=[0.15], operating_margin=0.20),
            market=MarketData(price=120.0, ev_ebitda=None),
        )

        result = calculate_justified_premium(security)

        assert result.justified_multiple is None
        assert any("ev" in note.lower() for note in result.notes)

    def test_justified_premium_no_universe(self):
        """Test handling when universe is not provided."""
        security = Security(
            ticker="TEST",
            sector="Tech",
            fundamentals=Fundamentals(roic_history=[0.15], operating_margin=0.20),
            market=MarketData(price=120.0, ev_ebitda=12.0),
        )

        result = calculate_justified_premium(security, universe=None)

        assert result.justified_multiple is None
        assert any("not available" in note.lower() for note in result.notes)

    def test_justified_premium_missing_sector_data(self, basic_universe):
        """Test handling when sector is not in universe."""
        security = Security(
            ticker="TEST",
            sector="UnknownSector",
            fundamentals=Fundamentals(roic_history=[0.15], operating_margin=0.20),
            market=MarketData(price=120.0, ev_ebitda=12.0),
        )

        result = calculate_justified_premium(security, basic_universe)

        assert result.justified_multiple is None
        assert any("not available" in note.lower() for note in result.notes)

    def test_justified_premium_missing_roic_history(self, basic_universe):
        """Test handling when company ROIC is missing."""
        security = Security(
            ticker="TEST",
            sector="Tech",
            fundamentals=Fundamentals(
                roic_history=[],
                operating_margin=0.20,
                ebitda_ttm=100,
                total_debt=0,
                cash_and_equivalents=0,
                shares_outstanding=10,
            ),
            market=MarketData(price=120.0, ev_ebitda=12.0),
        )

        result = calculate_justified_premium(security, basic_universe)

        # Should still compute justified multiple with only margin adjustment
        assert result.justified_multiple is not None
        # justified_multiple = 12 * 1.0 * (0.20/0.20) = 12
        assert abs(result.justified_multiple - 12.0) < 0.01
        assert any("ROIC" in note for note in result.notes)

    def test_justified_premium_missing_sector_roic(self):
        """Test handling when sector ROIC is missing."""
        universe = DamodaranUniverse(
            us_erp=0.05,
            region_erps={},
            sector_beta_u={"Tech": 1.2},
            sector_multiples={
                "Tech": {
                    "ev_ebitda": 12.0,
                    "pe": 20.0,
                    "operating_margin": 0.20,
                }
            },
        )

        security = Security(
            ticker="TEST",
            sector="Tech",
            fundamentals=Fundamentals(
                roic_history=[0.18],
                operating_margin=0.20,
                ebitda_ttm=100,
                total_debt=0,
                cash_and_equivalents=0,
                shares_outstanding=10,
            ),
            market=MarketData(price=120.0, ev_ebitda=12.0),
        )

        result = calculate_justified_premium(security, universe)

        assert result.justified_multiple is not None
        # Should use only margin adjustment
        # justified_multiple = 12 * 1.0 * (0.20/0.20) = 12
        assert abs(result.justified_multiple - 12.0) < 0.01
        assert any("ROIC" in note for note in result.notes)

    def test_justified_premium_missing_margin(self, basic_universe):
        """Test handling when company margin is missing."""
        security = Security(
            ticker="TEST",
            sector="Tech",
            fundamentals=Fundamentals(
                roic_history=[0.18],
                operating_margin=None,
                ebitda_ttm=100,
                total_debt=0,
                cash_and_equivalents=0,
                shares_outstanding=10,
            ),
            market=MarketData(price=120.0, ev_ebitda=12.0),
        )

        result = calculate_justified_premium(security, basic_universe)

        assert result.justified_multiple is not None
        # justified_multiple = 12 * (0.18/0.15) * 1.0 = 14.4
        expected = 12.0 * (0.18 / 0.15)
        assert abs(result.justified_multiple - expected) < 0.01
        assert any("margin" in note.lower() for note in result.notes)

    def test_justified_premium_below_sector_roic(self, basic_universe):
        """Test when company ROIC is below sector median."""
        security = Security(
            ticker="TEST",
            sector="Tech",
            fundamentals=Fundamentals(
                roic_history=[0.12],
                operating_margin=0.18,
                ebitda_ttm=100,
                total_debt=0,
                cash_and_equivalents=0,
                shares_outstanding=10,
            ),
            market=MarketData(price=120.0, ev_ebitda=12.0),
        )

        result = calculate_justified_premium(security, basic_universe)

        assert result.justified_multiple is not None
        # justified_multiple = 12 * (0.12/0.15) * (0.18/0.20)
        # = 12 * 0.8 * 0.9 = 8.64
        expected = 12.0 * (0.12 / 0.15) * (0.18 / 0.20)
        assert abs(result.justified_multiple - expected) < 0.01

        # Discount should be positive
        assert result.deserved_premium < 0

    def test_justified_premium_with_debt(self, basic_universe):
        """Test target price calculation with debt and cash."""
        security = Security(
            ticker="TEST",
            sector="Tech",
            fundamentals=Fundamentals(
                roic_history=[0.15],
                operating_margin=0.20,
                ebitda_ttm=100,
                total_debt=150,
                cash_and_equivalents=50,
                shares_outstanding=10,
            ),
            market=MarketData(price=120.0, ev_ebitda=12.0),
        )

        result = calculate_justified_premium(security, basic_universe)

        assert result.target_price is not None
        # justified_multiple = 12
        # target_ev = 100 * 12 = 1200
        # target_eq = 1200 - 150 + 50 = 1100
        # target_price = 1100 / 10 = 110
        assert abs(result.target_price - 110.0) < 0.01

    def test_justified_premium_zero_margin_denominator(self):
        """Test handling when sector margin is zero."""
        universe = DamodaranUniverse(
            us_erp=0.05,
            region_erps={},
            sector_beta_u={"Tech": 1.2},
            sector_multiples={
                "Tech": {
                    "ev_ebitda": 12.0,
                    "pe": 20.0,
                    "roic": 0.15,
                    "operating_margin": 0.0,
                }
            },
        )

        security = Security(
            ticker="TEST",
            sector="Tech",
            fundamentals=Fundamentals(
                roic_history=[0.18],
                operating_margin=0.20,
                ebitda_ttm=100,
                total_debt=0,
                cash_and_equivalents=0,
                shares_outstanding=10,
            ),
            market=MarketData(price=120.0, ev_ebitda=12.0),
        )

        result = calculate_justified_premium(security, universe)

        # Should skip margin adjustment when sector margin is zero
        assert result.justified_multiple is not None
        # justified_multiple = 12 * (0.18/0.15) = 14.4
        expected = 12.0 * (0.18 / 0.15)
        assert abs(result.justified_multiple - expected) < 0.01

    def test_justified_premium_empty_roic_history(self, basic_universe):
        """Test handling when roic_history is empty."""
        security = Security(
            ticker="TEST",
            sector="Tech",
            fundamentals=Fundamentals(
                roic_history=[],
                operating_margin=0.20,
                ebitda_ttm=100,
                total_debt=0,
                cash_and_equivalents=0,
                shares_outstanding=10,
            ),
            market=MarketData(price=120.0, ev_ebitda=12.0),
        )

        result = calculate_justified_premium(security, basic_universe)

        assert result.justified_multiple is not None
        # Should only use margin adjustment
        assert abs(result.justified_multiple - 12.0) < 0.01


class TestJustifiedPremiumIntegration:
    """Integration tests with RelativeValuation."""

    def test_relative_valuation_with_justified_premium(self):
        """Test that RelativeValuation properly integrates justified premium."""
        from iam.valuation.relative import RelativeValuation

        universe = DamodaranUniverse(
            us_erp=0.05,
            region_erps={},
            sector_beta_u={"Tech": 1.2},
            sector_multiples={
                "Tech": {
                    "ev_ebitda": 12.0,
                    "pe": 20.0,
                    "roic": 0.15,
                    "operating_margin": 0.20,
                }
            },
        )

        security = Security(
            ticker="TEST",
            sector="Tech",
            fundamentals=Fundamentals(
                roic_history=[0.18],
                operating_margin=0.22,
                ebitda_ttm=100,
                net_income_ttm=50,
                total_debt=0,
                cash_and_equivalents=0,
                shares_outstanding=10,
            ),
            market=MarketData(price=120.0, ev_ebitda=12.0, pe_ttm=24.0),
        )

        engine = RelativeValuation(universe)
        result = engine.compute(security)

        assert result.fair_value_per_share is not None
        assert "implied_price_justified_premium" in result.components
        assert "justified_multiple" in result.components
        assert "premium_gap" in result.components
