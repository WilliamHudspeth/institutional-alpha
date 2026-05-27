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

from dataclasses import dataclass
from typing import TYPE_CHECKING

from iam.data.damodaran import DamodaranProvider, MacroBaselines

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
    """
    erp: float
    risk_free_rate: float
    industry_unlevered_beta: float
    cost_of_equity: float

    def __str__(self) -> str:
        return (
            f"Risk Profile: Rf={self.risk_free_rate*100:.2f}% "
            f"ERP={self.erp*100:.2f}% "
            f"U-Beta={self.industry_unlevered_beta:.2f} "
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

    @staticmethod
    def get_macro_baselines() -> MacroBaselines:
        """Get current macro environment (ERP, Risk-Free Rate, Country Premium)."""
        return DamodaranProvider.get_macro_state()

    @staticmethod
    def get_equity_risk_profile(security: Security) -> EquityRiskProfile:
        """
        Synthesizes macro data + industry-standard baselines into
        a coherent risk profile for a specific security.

        This is the core institutional valuation anchor. Every DCF discount rate
        should be calculated using this profile.

        Args:
            security: Security object with sector, industry, debt, market_cap

        Returns:
            EquityRiskProfile with institutional Cost of Equity

        Algorithm:
        1. Get macro baselines (ERP, Rf) from Damodaran
        2. Get industry unlevered beta from Damodaran sector/industry lookup
        3. Re-lever the beta using company's current D/E ratio
        4. Calculate CoE = Rf + Beta * ERP (CAPM)

        Example:
            >>> profile = GroundTruthProvider.get_equity_risk_profile(aapl)
            >>> print(f"AAPL Cost of Equity: {profile.cost_of_equity*100:.2f}%")
            AAPL Cost of Equity: 8.45%
        """
        # 1. Macro Anchor (The 'Ground Truth')
        macro = DamodaranProvider.get_macro_state()

        # 2. Industry Anchor (Sector-specific business risk)
        u_beta = DamodaranProvider.get_industry_unlevered_beta(
            security.sector or "unknown",
            security.industry or "unknown"
        )

        # 3. Calculate Cost of Equity (CAPM with institutional assumptions)
        # Re-lever the industry beta using the security's own D/E ratio
        # This is where the institutional "alpha" lives—using current leverage
        # instead of regression beta's average of 5 years of history
        market_cap = security.market.market_cap or 1.0  # Avoid division by zero
        total_debt = security.fundamentals.total_debt or 0.0
        de_ratio = total_debt / market_cap
        tax_rate = 0.21  # US federal corporate tax rate

        levered_beta = DamodaranProvider.relever_beta(u_beta, de_ratio, tax_rate)
        cost_of_equity = macro.risk_free_rate + (levered_beta * macro.implied_erp)

        return EquityRiskProfile(
            erp=macro.implied_erp,
            risk_free_rate=macro.risk_free_rate,
            industry_unlevered_beta=u_beta,
            cost_of_equity=cost_of_equity,
        )

    @staticmethod
    def get_wacc(
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
        profile = GroundTruthProvider.get_equity_risk_profile(security)

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
