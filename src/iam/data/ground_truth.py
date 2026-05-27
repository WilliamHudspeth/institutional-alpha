"""Unified Ground Truth Provider for IAM Valuation Pipeline.

This module is the single source of truth for all institutional assumptions.
It decouples valuation logic from raw data sources and ensures every calculation
is anchored in Damodaran's institutional baselines, not Yahoo Finance's regressions.

Architecture: The Data Firewall
- Valuation engine never hits a raw API
- All requests go through this provider
- Provider decides: cached snapshot or live data
- Auditable: Every calculation can trace back to a specific Damodaran baseline
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import TYPE_CHECKING, Dict, Optional, Tuple

from iam.data.damodaran import DamodaranProvider, MacroBaselines
from iam.data.provenance import attach_provenance

if TYPE_CHECKING:
    from iam.data.security import Security


class GroundTruthProviderError(Exception):
    """Raised when ground truth calculation fails."""
    pass


@dataclass
class EquityRiskProfile:
    """The normalized risk-return anchor for an equity investment.

    This represents the complete risk picture for a security:
    - Macro risk (ERP, risk-free rate)
    - Industry risk (unlevered beta)
    - Company-specific financial risk (leverage, tax rate)

    The Cost of Equity calculated here should never change based on
    short-term stock price movements. It changes only when:
    1. Damodaran's monthly macro update changes ERP
    2. Company structure changes (new debt, new taxes)
    3. Company moves to different industry classification

    For multi-region companies, erp_breakdown shows the weighted ERP
    contribution by geography (useful for auditing international exposure).
    """
    erp: float
    risk_free_rate: float
    industry_unlevered_beta: float
    levered_beta: float
    cost_of_equity: float
    erp_breakdown: Dict[str, dict] = None

    def __post_init__(self) -> None:
        if self.erp_breakdown is None:
            self.erp_breakdown = {}

    def __str__(self) -> str:
        return (
            f"Risk Profile: Rf={self.risk_free_rate*100:.2f}% "
            f"ERP={self.erp*100:.2f}% "
            f"U-Beta={self.industry_unlevered_beta:.2f} "
            f"L-Beta={self.levered_beta:.2f} "
            f"CoE={self.cost_of_equity*100:.2f}%"
        )


class GroundTruthProvider:
    """
    The Single Source of Truth for institutional assumptions.

    Use this provider everywhere your valuation engine needs risk/return data.
    Never calculate WACC or Cost of Equity directly; always route through here.

    This ensures:
    1. Consistency across all valuations
    2. Auditability (every CoE traces back to a specific baseline)
    3. Version control (update Damodaran data once, flows everywhere)
    4. Institutional credibility (using published Damodaran research)
    """

    def __init__(self, damodaran: Optional[DamodaranProvider] = None):
        """Initialize with optional Damodaran provider (for dependency injection/testing)."""
        self.damodaran = damodaran or DamodaranProvider()

    def get_macro_baselines(self) -> MacroBaselines:
        """Get current macro environment (ERP, Risk-Free Rate, Country Premium)."""
        return self.damodaran.get_macro_state()

    def get_blended_erp(self, security: Security) -> Tuple[float, Dict]:
        """Calculate blended ERP from security's revenue_mix (geography weighting).

        For multi-region companies, uses revenue distribution to weight ERPs
        by geography. For single-region or no mix, falls back to country_iso.

        Args:
            security: Security with revenue_mix (optional)

        Returns:
            (blended_erp: float, breakdown: dict)
            Where breakdown shows per-region ERP contributions

        Example:
            nvda = Security(ticker="NVDA", ..., revenue_mix={"US": 0.44, "CN": 0.25, ...})
            erp, breakdown = GroundTruthProvider.get_blended_erp(nvda)
            # erp ~ 0.058 (blended across regions)
            # breakdown = {"us": {weight: 0.44, erp: 0.046, contrib: 0.020}, ...}
        """
        mix = security.normalized_mix()
        if not mix:
            # Fallback: use country_iso if no revenue mix
            erp = self.damodaran.resolve_erp(security.country_iso or "US")
            return erp, {
                (security.country_iso or "US"): {
                    "weight": 1.0,
                    "erp": erp,
                    "contrib": erp,
                    "fallback": True,
                }
            }

        breakdown = {}
        weighted = 0.0
        for token, weight in mix.items():
            erp = self.damodaran.resolve_erp(token)
            contrib = erp * weight
            weighted += contrib
            breakdown[token] = {
                "weight": round(weight, 4),
                "erp": erp,
                "contrib": round(contrib, 5),
            }
        return round(weighted, 4), breakdown

    def get_equity_risk_profile(self, security: Security) -> EquityRiskProfile:
        """
        Synthesizes macro data + industry-standard baselines into
        a coherent risk profile for a specific security.

        This is the core institutional valuation anchor. Every DCF discount rate
        should be calculated using this profile.

        Args:
            security: Security object with sector, industry, debt, market_cap, revenue_mix (optional)

        Returns:
            EquityRiskProfile with institutional Cost of Equity and erp_breakdown

        Algorithm:
        1. Get blended ERP from revenue_mix (geography weighting)
        2. Get macro baselines (Rf) from Damodaran
        3. Get industry unlevered beta from Damodaran sector/industry lookup
        4. Re-lever the beta using company's current D/E ratio
        5. Calculate CoE = Rf + Beta * ERP (CAPM)

        Example:
            >>> gt = GroundTruthProvider()
            >>> profile = gt.get_equity_risk_profile(aapl)
            >>> print(f"AAPL Cost of Equity: {profile.cost_of_equity*100:.2f}%")
            AAPL Cost of Equity: 8.45%
        """
        # 1. Blended ERP from geography
        blended_erp, erp_breakdown = self.get_blended_erp(security)

        # 2. Macro Anchor (The 'Ground Truth')
        macro = self.damodaran.get_macro_state()

        # 3. Industry Anchor (Sector-specific business risk)
        u_beta = self.damodaran.get_industry_unlevered_beta(
            security.sector or "unknown",
            security.industry or "unknown"
        )

        # 4. Calculate Cost of Equity (CAPM with institutional assumptions)
        # Re-lever the industry beta using the security's own D/E ratio
        # This is where the institutional "alpha" lives—using current leverage
        # instead of regression beta's average of 5 years of history
        market_cap = security.market.market_cap or 1.0  # Avoid division by zero
        total_debt = security.fundamentals.total_debt or 0.0
        de_ratio = total_debt / market_cap
        tax_rate = 0.21  # US federal corporate tax rate

        levered_beta = self.damodaran.relever_beta(u_beta, de_ratio, tax_rate)
        cost_of_equity = macro.risk_free_rate + (levered_beta * blended_erp)

        return EquityRiskProfile(
            erp=blended_erp,
            risk_free_rate=macro.risk_free_rate,
            industry_unlevered_beta=u_beta,
            levered_beta=round(levered_beta, 4),
            cost_of_equity=round(cost_of_equity, 4),
            erp_breakdown=erp_breakdown,
        )

    def get_risk_profile(self, security: Security) -> Dict:
        """Get risk profile as dict with provenance for auditing.

        This is the audit-friendly version of get_equity_risk_profile.
        Returns the same data but as a plain dict with _provenance attached.

        Args:
            security: Security object with sector, industry, debt, market_cap, revenue_mix

        Returns:
            Dict with erp, risk_free_rate, industry_unlevered_beta, levered_beta,
            cost_of_equity, erp_breakdown, and _provenance

        Example:
            >>> gt = GroundTruthProvider()
            >>> blk = Security(ticker="BLK", sector="...", industry="Asset Management", ...)
            >>> p = gt.get_risk_profile(blk)
            >>> print(f"Blended ERP: {p['erp']:.2%}")
            >>> print(f"Cost of Equity: {p['cost_of_equity']:.2%}")
            >>> print(f"Source: {p['_provenance']['version']}")
        """
        profile = self.get_equity_risk_profile(security)
        profile_dict = asdict(profile)
        return attach_provenance(profile_dict)

    def get_wacc(
        self,
        security: Security,
        cost_of_debt: float = 0.04,  # Default 4% CoD if not provided
    ) -> float:
        """
        Calculate Weighted Average Cost of Capital using institutional baselines.

        Formula: WACC = (E/V)*CoE + (D/V)*(1-Tc)*CoD

        Where:
        - E/V = Equity weight = Market Cap / Enterprise Value
        - D/V = Debt weight = Total Debt / Enterprise Value
        - Tc = Corporate tax rate (21% for US)
        - CoE = Cost of Equity (from ground truth)
        - CoD = Cost of Debt (or default 4%)

        Args:
            security: Security object with debt, market_cap, fundamentals
            cost_of_debt: Cost of debt (use company's actual cost if available)

        Returns:
            WACC as a decimal (0.08 = 8%)
        """
        profile = self.get_equity_risk_profile(security)

        market_cap = security.market.market_cap or 1.0
        total_debt = security.fundamentals.total_debt or 0.0
        tax_rate = 0.21

        enterprise_value = market_cap + total_debt
        if enterprise_value <= 0:
            return profile.cost_of_equity  # Fallback to CoE if no debt

        equity_weight = market_cap / enterprise_value
        debt_weight = total_debt / enterprise_value

        wacc = (equity_weight * profile.cost_of_equity) + (
            debt_weight * cost_of_debt * (1.0 - tax_rate)
        )

        return wacc
