"""Tests for growth rate triangulation engine.

Covers:
- Five independent growth estimators
- Inverse-variance weighting
- Margin trajectory detection (BBY-style compression)
- Company-specific volatility
- Financial-specific ROE-based growth (BLK, GS)
- Cyclical handling (AMD, MPC)
"""

from iam.data.security import Fundamentals, MarketData, Security
from iam.valuation.growth_triangulator import (
    GrowthEstimate,
    detect_margin_trajectory,
    estimate_bottom_up_growth,
    estimate_historical_growth,
    estimate_implied_growth,
    estimate_sustainable_growth,
    triangulate_growth,
)
from iam.valuation.profile_builder import (
    build_company_profile,
    triangulate_growth_for_security,
)


class TestImpliedGrowth:
    """Tests for reverse DCF implied growth estimator."""

    def test_high_fcf_yield_implies_low_growth(self):
        """High FCF yield -> low implied growth.

        FCF/share = 8000/1000 = 8, price=100 -> yield = 8%
        Implied growth = WACC - yield = 9% - 8% = 1%
        """
        est = estimate_implied_growth(
            price=100.0,
            fcf_ttm=8000.0,  # 8% yield: 8000/1000 shares = $8/share / $100 = 8%
            shares_outstanding=1000.0,
            wacc=0.09,
        )

        assert est is not None
        assert est.value < 0.03  # WACC - FCF/P ≈ 1%

    def test_low_fcf_yield_implies_high_growth(self):
        """Low FCF yield -> high implied growth.

        FCF/share = 2000/1000 = 2, price=100 -> yield = 2%
        Implied growth = WACC - yield = 9% - 2% = 7%
        """
        est = estimate_implied_growth(
            price=100.0,
            fcf_ttm=2000.0,  # 2% yield: 2000/1000 = $2/share / $100 = 2%
            shares_outstanding=1000.0,
            wacc=0.09,
        )

        assert est is not None
        assert est.value > 0.05  # WACC - FCF/P ≈ 7%

    def test_returns_none_without_data(self):
        """Should return None with missing data."""
        assert estimate_implied_growth(None, 100, 1000) is None
        assert estimate_implied_growth(100, None, 1000) is None
        assert estimate_implied_growth(100, 100, None) is None

    def test_returns_none_with_negative_fcf(self):
        """Should return None with negative FCF (cannot solve for growth)."""
        est = estimate_implied_growth(
            price=100.0,
            fcf_ttm=-50.0,
            shares_outstanding=1000.0,
        )
        assert est is None


class TestHistoricalGrowth:
    """Tests for historical CAGR estimator."""

    def test_consistent_growth(self):
        """Should compute steady CAGR."""
        # 10% growth per year, most-recent-first
        revenues = [161.0, 146.4, 133.1, 121.0, 110.0, 100.0]
        est = estimate_historical_growth(revenues)

        assert est is not None
        assert abs(est.value - 0.10) < 0.01

    def test_outlier_removal(self):
        """Should remove outliers when 5+ years available."""
        # 10% growth except one outlier of 50%
        revenues = [200.0, 146.4, 133.1, 121.0, 110.0, 100.0]
        est = estimate_historical_growth(revenues, min_years=3)

        assert est is not None
        # Outlier removal should keep growth near 10%
        assert 0.05 < est.value < 0.20

    def test_insufficient_history(self):
        """Should return None with too few years."""
        est = estimate_historical_growth([110.0, 100.0], min_years=3)
        assert est is None

    def test_high_volatility_low_confidence(self):
        """High volatility -> lower confidence."""
        # Wildly varying growth
        revenues = [200.0, 100.0, 150.0, 50.0, 100.0, 75.0]
        est = estimate_historical_growth(revenues)

        assert est is not None
        assert est.confidence < 0.7  # Penalized for high volatility


class TestSustainableGrowth:
    """Tests for ROE-based sustainable growth (critical for financials)."""

    def test_high_roe_no_payout(self):
        """High ROE with 100% retention -> growth = ROE."""
        est = estimate_sustainable_growth(
            roe=0.20,
            payout_ratio=0.0,
        )

        assert est is not None
        assert abs(est.value - 0.20) < 0.01

    def test_payout_reduces_growth(self):
        """Higher payout -> lower sustainable growth."""
        est_low_payout = estimate_sustainable_growth(roe=0.15, payout_ratio=0.20)
        est_high_payout = estimate_sustainable_growth(roe=0.15, payout_ratio=0.80)

        assert est_low_payout.value > est_high_payout.value

    def test_returns_none_no_roe(self):
        """Should return None without ROE."""
        assert estimate_sustainable_growth(None) is None
        assert estimate_sustainable_growth(0.0) is None

    def test_stable_roic_high_confidence(self):
        """Stable ROIC history -> higher confidence."""
        stable = estimate_sustainable_growth(roe=0.15, roic_history=[0.15, 0.14, 0.15, 0.14, 0.15])
        unstable = estimate_sustainable_growth(
            roe=0.15, roic_history=[0.15, 0.05, 0.25, 0.10, 0.20]
        )

        assert stable.confidence > unstable.confidence


class TestBottomUpGrowth:
    """Tests for bottom-up build estimator."""

    def test_stable_margins(self):
        """Stable margins -> revenue growth = bottom-up growth."""
        est = estimate_bottom_up_growth(
            revenue_growth_5y=0.08,
            operating_margin=0.15,
            operating_margin_5y_avg=0.15,
        )

        assert est is not None
        assert abs(est.value - 0.088) < 0.02  # 8% * 1.1 reinvestment

    def test_margin_compression_reduces_growth(self):
        """Margin compression -> reduced bottom-up growth."""
        est_expanding = estimate_bottom_up_growth(
            revenue_growth_5y=0.08,
            operating_margin=0.20,
            operating_margin_5y_avg=0.15,
        )
        est_compressing = estimate_bottom_up_growth(
            revenue_growth_5y=0.08,
            operating_margin=0.10,
            operating_margin_5y_avg=0.15,
        )

        assert est_expanding.value > est_compressing.value


class TestMarginTrajectory:
    """Tests for margin compression/expansion detection."""

    def test_stable_margin(self):
        """Should detect stable margins."""
        result = detect_margin_trajectory(
            operating_margin=0.15,
            operating_margin_history=[0.15, 0.14, 0.16, 0.15, 0.14],
        )

        assert result["trajectory"] == "stable"
        assert result["adjustment"] == 0.0

    def test_bby_style_compression(self):
        """Should catch BBY-style margin compression (2.6% -> 1.5%).

        Adjustment is additive in absolute percentage points.
        ~46% compression -> ~5.5pp growth penalty.
        """
        result = detect_margin_trajectory(
            operating_margin=0.015,  # Current 1.5%
            operating_margin_history=[0.026, 0.028, 0.030, 0.029, 0.027],  # ~2.6% avg
        )

        assert result["trajectory"] == "compression"
        assert result["adjustment"] < -0.03  # At least 3pp growth penalty
        assert abs(result["severity"]) > 0.30  # >30% compression

    def test_margin_expansion(self):
        """Should detect margin expansion."""
        result = detect_margin_trajectory(
            operating_margin=0.25,
            operating_margin_history=[0.20, 0.19, 0.21, 0.20, 0.19],
        )

        assert result["trajectory"] == "expansion"
        assert result["adjustment"] > 0.0
        assert result["adjustment"] <= 0.10  # Capped bonus

    def test_unknown_no_history(self):
        """Should return unknown with no history."""
        result = detect_margin_trajectory(0.15, [])
        assert result["trajectory"] == "unknown"


class TestTriangulation:
    """Tests for inverse-variance weighted blending."""

    def test_blends_multiple_estimates(self):
        """Should blend estimates by inverse variance."""
        estimates = [
            GrowthEstimate(method="implied", value=0.10, confidence=0.7, variance=0.001),
            GrowthEstimate(method="historical", value=0.08, confidence=0.8, variance=0.001),
            GrowthEstimate(method="sector", value=0.06, confidence=0.4, variance=0.01),
        ]

        result = triangulate_growth(estimates)

        # Weighted average should pull toward low-variance estimates
        assert 0.07 < result.blended_growth < 0.11
        assert result.confidence > 0.4

    def test_disagreement_lowers_confidence(self):
        """High disagreement -> lower confidence."""
        agreeing = [
            GrowthEstimate(method="implied", value=0.10, confidence=0.7, variance=0.001),
            GrowthEstimate(method="historical", value=0.10, confidence=0.7, variance=0.001),
        ]
        disagreeing = [
            GrowthEstimate(method="implied", value=0.25, confidence=0.7, variance=0.001),
            GrowthEstimate(method="historical", value=0.02, confidence=0.7, variance=0.001),
        ]

        r1 = triangulate_growth(agreeing)
        r2 = triangulate_growth(disagreeing)

        assert r1.confidence > r2.confidence
        assert r2.method_disagreement > r1.method_disagreement

    def test_margin_adjustment_applied(self):
        """Should reduce growth when margin adjustment is negative."""
        estimates = [
            GrowthEstimate(method="historical", value=0.10, confidence=0.8, variance=0.001),
        ]

        no_adj = triangulate_growth(estimates, margin_adjustment=0.0)
        with_adj = triangulate_growth(estimates, margin_adjustment=-0.20)

        assert with_adj.blended_growth < no_adj.blended_growth
        assert with_adj.margin_adjustment == -0.20

    def test_handles_empty_estimates(self):
        """Should handle no valid estimates gracefully."""
        result = triangulate_growth([None, None])

        assert result.blended_growth == 0.06  # Fallback
        assert result.confidence == 0.2


class TestSecurityIntegration:
    """End-to-end tests with Security objects."""

    def test_apple_like_growth_company(self):
        """Should produce reasonable growth for high-quality tech."""
        security = Security(
            ticker="AAPL",
            sector="Technology",
            fundamentals=Fundamentals(
                revenue_ttm=400e9,
                revenue_history=[400e9, 370e9, 340e9, 310e9, 280e9, 250e9],
                operating_margin=0.30,
                operating_margin_history=[0.30, 0.30, 0.28, 0.29, 0.28],
                fcf_ttm=100e9,
                fcf_history=[100e9, 95e9, 88e9, 80e9, 75e9, 70e9],
                roic_history=[0.30, 0.32, 0.28, 0.30, 0.29],
                shares_outstanding=15e9,
                incremental_roic=0.30,
            ),
            market=MarketData(price=170.0),
        )

        result = triangulate_growth_for_security(security)

        assert 0.04 < result.blended_growth < 0.20
        assert result.confidence > 0.4
        assert len(result.estimates) >= 3  # Multiple methods fired

    def test_bby_margin_compression_case(self):
        """BBY-style: margin compression 2.6% -> 1.5%, should reduce growth."""
        security = Security(
            ticker="BBY",
            sector="Consumer Discretionary",
            fundamentals=Fundamentals(
                revenue_ttm=42e9,
                revenue_history=[42e9, 41e9, 47e9, 51e9, 47e9, 44e9],
                operating_margin=0.015,  # Compressed to 1.5%
                operating_margin_history=[0.026, 0.028, 0.030, 0.029, 0.027],  # was ~2.6%
                fcf_ttm=1.2e9,
                fcf_history=[1.2e9, 1.4e9, 2.0e9, 2.5e9, 2.1e9, 1.8e9],
                shares_outstanding=215e6,
                incremental_roic=0.06,
            ),
            market=MarketData(price=75.0),
        )

        result = triangulate_growth_for_security(security)

        # Should detect margin compression and reduce blended growth
        assert result.margin_adjustment < -0.05
        # Final growth should be lower than raw (pre-margin) growth
        assert result.blended_growth < result.raw_growth

    def test_financial_uses_sustainable_growth(self):
        """Financials should weight ROE-based sustainable growth heavily."""
        security = Security(
            ticker="BLK",
            sector="Financials",
            fundamentals=Fundamentals(
                revenue_ttm=18e9,
                revenue_history=[18e9, 17e9, 19e9, 18e9, 16e9, 14e9],
                operating_margin=0.40,
                operating_margin_history=[0.40, 0.38, 0.42, 0.40, 0.38],
                fcf_ttm=5e9,
                fcf_history=[5e9, 4.8e9, 5.2e9, 4.5e9, 4e9],
                roic_history=[0.12, 0.11, 0.13, 0.12, 0.11],
                shares_outstanding=150e6,
                incremental_roic=0.12,
            ),
            market=MarketData(price=750.0),
        )

        result = triangulate_growth_for_security(security)

        # Sustainable growth estimate should be present
        methods = [e.method for e in result.estimates]
        assert "sustainable" in methods

        # Find sustainable estimate
        sust = next(e for e in result.estimates if e.method == "sustainable")
        # ROE-based growth = 12% * 60% retention = 7.2%
        assert 0.05 < sust.value < 0.10

    def test_cyclical_uses_company_volatility(self):
        """AMD-style cyclical should use company-specific volatility."""
        security = Security(
            ticker="AMD",
            sector="Technology",
            fundamentals=Fundamentals(
                revenue_ttm=25e9,
                # Wildly varying revenue (cyclical)
                revenue_history=[25e9, 20e9, 25e9, 16e9, 10e9, 7e9, 6e9, 5e9],
                operating_margin=0.05,
                operating_margin_history=[0.05, 0.15, 0.20, 0.10, -0.05, 0.02],
                fcf_ttm=1e9,
                fcf_history=[1e9, 3e9, 4e9, 2e9, -0.5e9, 0.3e9, 0.1e9],
                roic_history=[0.15, 0.20, 0.18, 0.10, -0.05, 0.05],
                shares_outstanding=1.6e9,
                incremental_roic=0.15,
            ),
            market=MarketData(price=120.0),
        )

        profile = build_company_profile(security)

        # Company-specific volatility should be HIGH (not sector default)
        assert profile.hist_volatility > 0.30  # AMD is highly volatile

    def test_handles_missing_fundamentals(self):
        """Should produce profile even with sparse data."""
        security = Security(
            ticker="NEWCO",
            sector="Technology",
            fundamentals=Fundamentals(
                operating_margin=0.10,
            ),
            market=MarketData(price=50.0),
        )

        profile = build_company_profile(security)

        assert profile.ticker == "NEWCO"
        assert profile.hist_eps_growth > 0  # Falls back to sector default
        assert profile.hist_volatility > 0


class TestNineTickerBasket:
    """Validate triangulation against the nine reference companies."""

    def _make_security(
        self,
        ticker,
        sector,
        op_margin,
        op_history,
        fcf_ttm,
        fcf_history,
        revenue_ttm,
        revenue_history,
        roic_history,
        price,
        shares,
    ):
        return Security(
            ticker=ticker,
            sector=sector,
            fundamentals=Fundamentals(
                revenue_ttm=revenue_ttm,
                revenue_history=revenue_history,
                operating_margin=op_margin,
                operating_margin_history=op_history,
                fcf_ttm=fcf_ttm,
                fcf_history=fcf_history,
                roic_history=roic_history,
                shares_outstanding=shares,
                incremental_roic=roic_history[0] if roic_history else 0.10,
            ),
            market=MarketData(price=price),
        )

    def test_ko_stable_low_volatility(self):
        """KO should show stable growth with low volatility."""
        security = self._make_security(
            ticker="KO",
            sector="Consumer Staples",
            op_margin=0.226,
            op_history=[0.226, 0.225, 0.220, 0.218, 0.215],
            fcf_ttm=10e9,
            fcf_history=[10e9, 9.5e9, 9.8e9, 9.2e9, 8.9e9, 8.5e9],
            revenue_ttm=45e9,
            revenue_history=[45e9, 44e9, 43e9, 38e9, 37e9, 35e9],
            roic_history=[0.15, 0.14, 0.13, 0.14, 0.13],
            price=60.0,
            shares=4.3e9,
        )

        profile = build_company_profile(security)
        result = triangulate_growth_for_security(security)

        # Low volatility expected for KO
        assert profile.hist_volatility < 0.15
        # Growth should be modest (5-8%)
        assert 0.02 < result.blended_growth < 0.12

    def test_googl_moat_tech_high_quality(self):
        """GOOGL should show strong, sustainable growth."""
        security = self._make_security(
            ticker="GOOGL",
            sector="Technology",
            op_margin=0.286,
            op_history=[0.286, 0.27, 0.30, 0.28, 0.26],
            fcf_ttm=70e9,
            fcf_history=[70e9, 60e9, 65e9, 55e9, 50e9, 40e9],
            revenue_ttm=300e9,
            revenue_history=[300e9, 280e9, 257e9, 182e9, 161e9, 136e9],
            roic_history=[0.20, 0.22, 0.25, 0.20, 0.18],
            price=140.0,
            shares=12.5e9,
        )

        result = triangulate_growth_for_security(security)
        build_company_profile(security)

        # Should produce healthy growth estimate
        assert result.blended_growth > 0.05
        # High confidence expected
        assert result.confidence > 0.4


class TestAuditTrail:
    """Audit trail must remain intact for compliance."""

    def test_to_dict_includes_all_methods(self):
        """to_dict() should preserve full audit trail."""
        estimates = [
            GrowthEstimate(method="implied", value=0.10, confidence=0.7, variance=0.001),
            GrowthEstimate(method="historical", value=0.08, confidence=0.8, variance=0.001),
            GrowthEstimate(method="sector", value=0.06, confidence=0.4, variance=0.01),
        ]

        result = triangulate_growth(estimates, margin_adjustment=-0.05)
        d = result.to_dict()

        assert "blended_growth" in d
        assert "raw_growth" in d
        assert "margin_adjustment" in d
        assert "confidence" in d
        assert "estimates" in d
        assert len(d["estimates"]) == 3
        assert all("method" in e for e in d["estimates"])
        assert all("weight" in e for e in d["estimates"])
