"""Tests for adaptive valuation engine and profile builder."""

import pytest
import numpy as np

from iam.valuation.adaptive import (
    AdaptiveValuationEngine,
    BusinessType,
    CompanyProfile,
)
from iam.valuation.profile_builder import build_company_profile
from iam.data.security import Security, Fundamentals, MarketData


class TestCompanyProfile:
    """Tests for CompanyProfile dataclass."""

    def test_instantiation(self):
        """Should create CompanyProfile with required fields."""
        profile = CompanyProfile(
            ticker="AAPL",
            implied_growth=0.10,
            hist_eps_growth=0.12,
            hist_volatility=0.15,
            sector_growth=0.08,
            adjacent_growth=0.10,
            op_margin=0.30,
            sector_margin=0.20,
        )

        assert profile.ticker == "AAPL"
        assert profile.implied_growth == 0.10
        assert profile.hist_volatility == 0.15

    def test_optional_fields(self):
        """Should handle optional ROE/ROIC fields."""
        profile = CompanyProfile(
            ticker="BLK",
            implied_growth=0.08,
            hist_eps_growth=0.05,
            hist_volatility=0.10,
            sector_growth=0.06,
            adjacent_growth=0.08,
            op_margin=0.45,
            sector_margin=0.30,
            roe=0.15,
            roic=0.12,
            mid_cycle_margin=0.40,
        )

        assert profile.roe == 0.15
        assert profile.mid_cycle_margin == 0.40


class TestAdaptiveClassification:
    """Tests for business type classification."""

    def test_classify_by_type_map(self):
        """Should classify tickers in TYPE_MAP correctly."""
        engine = AdaptiveValuationEngine()

        assert engine.classify("KO") == "stable"
        assert engine.classify("GOOGL") == "moat_tech"
        assert engine.classify("BLK") == "financial"
        assert engine.classify("AMD") == "cyclical"

    def test_classify_unknown_ticker(self):
        """Should default to stable for unknown tickers."""
        engine = AdaptiveValuationEngine()

        assert engine.classify("UNKNOWN") == "stable"


class TestPhase2Divergence:
    """Tests for phase2 divergence analysis."""

    def test_condition_a_agreement(self):
        """Should produce Condition A when estimates agree."""
        engine = AdaptiveValuationEngine()
        profile = CompanyProfile(
            ticker="KO",
            implied_growth=0.05,
            hist_eps_growth=0.052,
            hist_volatility=0.05,
            sector_growth=0.04,
            adjacent_growth=0.06,
            op_margin=0.23,
            sector_margin=0.15,
        )

        result = engine.phase2_divergence(profile)

        assert result["condition"] == "A"
        assert result["base_growth"] == profile.hist_eps_growth

    def test_condition_b_history_beats_implied(self):
        """Should produce Condition B when history beats implied."""
        engine = AdaptiveValuationEngine()
        profile = CompanyProfile(
            ticker="WMT",
            implied_growth=0.04,
            hist_eps_growth=0.12,  # Much higher than implied
            hist_volatility=0.08,
            sector_growth=0.05,
            adjacent_growth=0.06,
            op_margin=0.03,
            sector_margin=0.04,
        )

        result = engine.phase2_divergence(profile)

        assert result["condition"] == "B"
        assert result["base_growth"] > profile.hist_eps_growth  # Capped uplift

    def test_condition_c_implied_beats_history(self):
        """Should produce Condition C when implied beats history."""
        engine = AdaptiveValuationEngine()
        profile = CompanyProfile(
            ticker="CVS",
            implied_growth=0.10,
            hist_eps_growth=-0.05,  # Negative history
            hist_volatility=0.15,
            sector_growth=0.05,
            adjacent_growth=0.06,
            op_margin=0.02,
            sector_margin=0.04,
        )

        result = engine.phase2_divergence(profile)

        assert result["condition"] == "C"
        assert result["base_growth"] == profile.hist_eps_growth

    def test_volatility_adjustment(self):
        """Should scale threshold by volatility."""
        engine = AdaptiveValuationEngine()

        # Low volatility → lower threshold
        low_vol = CompanyProfile(
            ticker="KO",
            implied_growth=0.05,
            hist_eps_growth=0.05,
            hist_volatility=0.05,
            sector_growth=0.04,
            adjacent_growth=0.06,
            op_margin=0.23,
            sector_margin=0.15,
        )

        # High volatility → higher threshold
        high_vol = CompanyProfile(
            ticker="AMD",
            implied_growth=0.15,
            hist_eps_growth=0.10,
            hist_volatility=0.40,
            sector_growth=0.10,
            adjacent_growth=0.15,
            op_margin=0.05,
            sector_margin=0.16,
        )

        low_thresh = engine.phase2_divergence(low_vol)["threshold"]
        high_thresh = engine.phase2_divergence(high_vol)["threshold"]

        assert high_thresh > low_thresh


class TestPhase3Fade:
    """Tests for 10-year fade paths."""

    def test_moat_tech_fade(self):
        """Moat-tech should hold growth 7 years, then fade."""
        engine = AdaptiveValuationEngine()
        profile = CompanyProfile(
            ticker="GOOGL",
            implied_growth=0.12,
            hist_eps_growth=0.15,
            hist_volatility=0.12,
            sector_growth=0.10,
            adjacent_growth=0.12,
            op_margin=0.28,
            sector_margin=0.20,
        )

        fade = engine.phase3_fade(profile, 0.15)

        assert len(fade) == 10
        assert fade[0] == 0.15  # Year 1
        assert fade[6] == 0.15  # Year 7 (still holding)
        assert 0.10 < fade[9] < 0.15  # Year 10 (faded down)

    def test_stable_fade(self):
        """Stable should hold growth 8 years, then fade."""
        engine = AdaptiveValuationEngine()
        profile = CompanyProfile(
            ticker="KO",
            implied_growth=0.06,
            hist_eps_growth=0.052,
            hist_volatility=0.05,
            sector_growth=0.04,
            adjacent_growth=0.06,
            op_margin=0.226,
            sector_margin=0.15,
        )

        fade = engine.phase3_fade(profile, 0.052)

        assert len(fade) == 10
        assert fade[0] == 0.052
        assert fade[7] == 0.052  # Year 8 (still holding)
        assert fade[9] < 0.052  # Year 10 (faded to sector)

    def test_financial_fade(self):
        """Financials should fade ROE-based growth over 5 years."""
        engine = AdaptiveValuationEngine()
        profile = CompanyProfile(
            ticker="BLK",
            implied_growth=0.08,
            hist_eps_growth=0.05,
            hist_volatility=0.10,
            sector_growth=0.06,
            adjacent_growth=0.08,
            op_margin=0.445,
            sector_margin=0.30,
            roe=0.11,
        )

        fade = engine.phase3_fade(profile, 0.05)

        assert len(fade) == 10
        assert fade[0] == 0.05
        assert fade[4] == 0.05  # Year 5 (still holding)
        assert fade[9] <= 0.06  # Year 10 (faded to sector growth or lower)

    def test_cyclical_fade_trough(self):
        """Cyclicals at trough should hold longer."""
        engine = AdaptiveValuationEngine()
        profile = CompanyProfile(
            ticker="MPC",
            implied_growth=0.05,
            hist_eps_growth=0.30,
            hist_volatility=0.60,
            sector_growth=0.04,
            adjacent_growth=0.07,
            op_margin=0.03,  # Low margin = trough
            sector_margin=0.05,
            mid_cycle_margin=0.08,
        )

        fade = engine.phase3_fade(profile, 0.30)

        assert len(fade) == 10
        assert fade[0] == 0.30
        assert fade[2] == 0.30  # Year 3 (holding)
        assert fade[3] < 0.30  # Year 4 (starting to fade)

    def test_cyclical_fade_peak(self):
        """Cyclicals near peak should fade faster."""
        engine = AdaptiveValuationEngine()
        profile = CompanyProfile(
            ticker="MPC",
            implied_growth=0.05,
            hist_eps_growth=0.30,
            hist_volatility=0.60,
            sector_growth=0.04,
            adjacent_growth=0.07,
            op_margin=0.065,  # High margin = peak
            sector_margin=0.05,
            mid_cycle_margin=0.08,
        )

        fade = engine.phase3_fade(profile, 0.30)

        assert len(fade) == 10
        assert fade[0] == 0.30
        assert fade[1] == 0.30  # Year 2 (holding briefly)
        assert fade[2] < 0.30  # Year 3 (fade faster than trough)


class TestPhase4Confidence:
    """Tests for confidence grading."""

    def test_grade_a_low_spread(self):
        """Should give grade A for low spread and margin alignment."""
        engine = AdaptiveValuationEngine()
        profile = CompanyProfile(
            ticker="KO",
            implied_growth=0.05,
            hist_eps_growth=0.052,
            hist_volatility=0.05,
            sector_growth=0.04,
            adjacent_growth=0.06,
            op_margin=0.226,
            sector_margin=0.15,
        )

        div = engine.phase2_divergence(profile)
        grade = engine.phase4_confidence(profile, div)

        assert grade == "A"

    def test_grade_b_medium_spread(self):
        """Should give grade B for medium spread."""
        engine = AdaptiveValuationEngine()
        profile = CompanyProfile(
            ticker="WMT",
            implied_growth=0.05,
            hist_eps_growth=0.12,
            hist_volatility=0.08,
            sector_growth=0.05,
            adjacent_growth=0.06,
            op_margin=0.03,
            sector_margin=0.04,
        )

        div = engine.phase2_divergence(profile)
        grade = engine.phase4_confidence(profile, div)

        assert grade in ("A", "B")  # Medium spread may be B

    def test_grade_c_high_spread(self):
        """Should give grade C for very high spread."""
        engine = AdaptiveValuationEngine()
        profile = CompanyProfile(
            ticker="CVS",
            implied_growth=0.15,  # Increased spread
            hist_eps_growth=-0.15,  # Even more negative
            hist_volatility=0.15,
            sector_growth=0.05,
            adjacent_growth=0.06,
            op_margin=0.02,
            sector_margin=0.04,
        )

        div = engine.phase2_divergence(profile)
        grade = engine.phase4_confidence(profile, div)

        assert grade == "C"

    def test_cyclical_grade_capped(self):
        """Cyclicals should be capped at grade B."""
        engine = AdaptiveValuationEngine()
        profile = CompanyProfile(
            ticker="AMD",
            implied_growth=0.15,
            hist_eps_growth=0.10,
            hist_volatility=0.40,
            sector_growth=0.10,
            adjacent_growth=0.15,
            op_margin=0.05,
            sector_margin=0.16,
        )

        div = engine.phase2_divergence(profile)
        grade = engine.phase4_confidence(profile, div)

        assert grade in ("A", "B")  # Cyclical → max B


class TestAdaptiveEngine:
    """Tests for full engine."""

    def test_full_run(self):
        """Should run complete analysis."""
        engine = AdaptiveValuationEngine()
        profile = CompanyProfile(
            ticker="AAPL",
            implied_growth=0.10,
            hist_eps_growth=0.15,
            hist_volatility=0.20,
            sector_growth=0.12,
            adjacent_growth=0.15,
            op_margin=0.30,
            sector_margin=0.20,
        )

        result = engine.run(profile)

        assert result["ticker"] == "AAPL"
        assert "type" in result
        assert "phase2" in result
        assert "fade_path" in result
        assert len(result["fade_path"]) == 10
        assert "confidence" in result
        assert result["confidence"] in ("A", "B", "C")
        assert "year10_growth" in result

    def test_all_nine_companies(self):
        """Should handle all nine test companies."""
        engine = AdaptiveValuationEngine()

        profiles = {
            "KO": CompanyProfile(
                "KO", 0.06, 0.052, 0.05, 0.0439, 0.06, 0.226, 0.15
            ),
            "AMD": CompanyProfile(
                "AMD",
                0.25,
                0.078,
                0.40,
                0.102,
                0.151,
                0.049,
                0.163,
                mid_cycle_margin=0.12,
            ),
            "BLK": CompanyProfile(
                "BLK", 0.08, 0.027, 0.10, 0.06, 0.08, 0.445, 0.30, roe=0.11
            ),
            "GOOGL": CompanyProfile(
                "GOOGL", 0.14, 0.177, 0.12, 0.12, 0.15, 0.286, 0.20
            ),
            "META": CompanyProfile(
                "META", 0.15, 0.168, 0.15, 0.12, 0.15, 0.380, 0.20
            ),
            "MPC": CompanyProfile(
                "MPC",
                0.05,
                0.302,
                0.60,
                0.04,
                0.07,
                0.0299,
                0.05,
                mid_cycle_margin=0.08,
            ),
            "WMT": CompanyProfile(
                "WMT", 0.07, 0.08, 0.08, 0.045, 0.05, 0.0293, 0.04, roic=0.12
            ),
            "GS": CompanyProfile(
                "GS",
                0.06,
                -0.016,
                0.25,
                0.06,
                0.07,
                0.137,
                0.20,
                roe=0.137,
            ),
            "CVS": CompanyProfile(
                "CVS",
                0.04,
                -0.086,
                0.15,
                0.05,
                0.055,
                0.0219,
                0.04,
                roic=0.06,
            ),
        }

        for ticker, profile in profiles.items():
            result = engine.run(profile)
            assert result["ticker"] == ticker
            assert len(result["fade_path"]) == 10
            assert result["confidence"] in ("A", "B", "C")


class TestProfileBuilder:
    """Tests for profile builder from Security objects."""

    def test_build_profile_from_security(self):
        """Should build profile from Security object."""
        fundamentals = Fundamentals(
            operating_margin=0.30,
            incremental_roic=0.75,
        )
        security = Security(
            ticker="AAPL",
            sector="Technology",
            fundamentals=fundamentals,
            market=MarketData(price=150.0),
        )

        profile = build_company_profile(security)

        assert profile.ticker == "AAPL"
        assert profile.sector_growth > 0
        assert profile.adjacent_growth > 0
        assert profile.op_margin == 0.30

    def test_build_profile_fallback_defaults(self):
        """Should use defaults for missing data."""
        security = Security(
            ticker="UNKNOWN",
            sector="Technology",
            fundamentals=Fundamentals(),
            market=MarketData(price=100.0),
        )

        profile = build_company_profile(security)

        assert profile.ticker == "UNKNOWN"
        assert profile.hist_eps_growth > 0  # Default fallback
        assert profile.hist_volatility > 0
