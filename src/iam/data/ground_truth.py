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

import math
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING

from iam.data.damodaran import DamodaranProvider, MacroBaselines
from iam.data.provenance import attach_provenance

if TYPE_CHECKING:
    from iam.data.security import Security


class GroundTruthProviderError(ValueError):
    """Raised when a ground-truth profile cannot be built from real data.

    A ``ValueError`` subclass: missing market cap / unknown industry is a
    rejection of the input, not a crash.
    """

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
    erp_breakdown: dict[str, dict] = None  # type: ignore
    rf_source: str = ""
    erp_source: str = ""
    tax_rate: float | None = None
    tax_source: str = ""
    debt_to_equity: float | None = None
    defaults_used: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.erp_breakdown is None:
            self.erp_breakdown = {}

    def __str__(self) -> str:
        return (
            f"Risk Profile: Rf={self.risk_free_rate * 100:.2f}% "
            f"ERP={self.erp * 100:.2f}% "
            f"U-Beta={self.industry_unlevered_beta:.2f} "
            f"L-Beta={self.levered_beta:.2f} "
            f"CoE={self.cost_of_equity * 100:.2f}%"
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

    def __init__(self, damodaran: DamodaranProvider | None = None):
        """Initialize with optional Damodaran provider (for dependency injection/testing)."""
        self.damodaran = damodaran or DamodaranProvider()

    def get_macro_baselines(self) -> MacroBaselines:
        """Get current macro environment (ERP, Risk-Free Rate, Country Premium)."""
        return self.damodaran.get_macro_state()

    def get_blended_erp(self, security: Security) -> tuple[float, dict]:
        """Revenue-weighted ERP of the company (owner's "On BLK" method).

        Delegates to :func:`iam.valuation.country_risk.company_erp`:
        Damodaran country/regional ERPs weighted by ``security.revenue_mix``,
        the dataset's US ERP when there is no usable mix.

        Returns:
            (blended_erp, breakdown) where breakdown maps each resolved
            geography to its weight, ERP and contribution.
        """
        # Imported lazily: iam.valuation imports this module at package load.
        from iam.valuation.country_risk import company_erp, revenue_erp_breakdown

        erp, _source = company_erp(security)
        return erp, revenue_erp_breakdown(security)

    def get_equity_risk_profile(self, security: Security) -> EquityRiskProfile | None:
        """Bottom-up cost of equity for a security, or ``None`` without enough data.

        See :meth:`get_equity_risk_profile_with_reason` for the algorithm and for
        the reason a profile could not be built.
        """
        return self.get_equity_risk_profile_with_reason(security)[0]

    def get_equity_risk_profile_with_reason(
        self, security: Security
    ) -> tuple[EquityRiskProfile | None, str]:
        """Bottom-up cost of equity: Rf + relevered industry beta x revenue-weighted ERP.

        Algorithm:
        1. Rf (with source) from the Damodaran macro state.
        2. ERP = ``country_risk.company_erp`` (revenue-weighted, US fallback), with source.
        3. Industry unlevered beta from the Damodaran table.
        4. Relever at the company's CURRENT market D/E (total debt / market cap)
           with the MARGINAL tax rate (``country_tax.company_marginal_tax``).
        5. Ke = Rf + relevered beta x ERP.

        Returns:
            ``(profile, "")`` or ``(None, reason)``. No profile is built when the
            market cap or the industry beta is missing: neither is invented.
        """
        from iam.valuation.country_risk import company_erp, revenue_erp_breakdown
        from iam.valuation.country_tax import company_marginal_tax

        market_cap = security.market.market_cap if security.market else None
        if market_cap is None or not math.isfinite(market_cap) or market_cap <= 0:
            return None, "market cap unavailable: current D/E unknown, no bottom-up cost of equity"

        u_beta = self.damodaran.find_industry_unlevered_beta(security.sector, security.industry)
        if u_beta is None:
            return None, (
                f"industry unlevered beta not found for sector {security.sector!r} / "
                f"industry {security.industry!r}: no bottom-up cost of equity"
            )

        blended_erp, erp_source = company_erp(security)
        erp_breakdown = revenue_erp_breakdown(security)
        macro = self.damodaran.get_macro_state()

        defaults_used: list[str] = []
        total_debt = security.fundamentals.total_debt
        if total_debt is None:
            total_debt = 0.0
            defaults_used.append("total debt unavailable: D/E taken as 0")
        de_ratio = total_debt / market_cap

        # Damodaran's convention: relever beta with the MARGINAL (statutory, revenue-
        # weighted) rate, never the effective rate, even when the company has one.
        tax_rate, tax_source = company_marginal_tax(security)

        levered_beta = self.damodaran.relever_beta(u_beta, de_ratio, tax_rate)
        cost_of_equity = macro.risk_free_rate + levered_beta * blended_erp

        return (
            EquityRiskProfile(
                erp=blended_erp,
                risk_free_rate=macro.risk_free_rate,
                industry_unlevered_beta=u_beta,
                levered_beta=levered_beta,
                cost_of_equity=cost_of_equity,
                erp_breakdown=erp_breakdown,
                rf_source=macro.rf_source,
                erp_source=erp_source,
                tax_rate=tax_rate,
                tax_source=tax_source,
                debt_to_equity=de_ratio,
                defaults_used=defaults_used,
            ),
            "",
        )

    def get_risk_profile(self, security: Security) -> dict:
        """Get risk profile as dict with provenance for auditing.

        This is the audit-friendly version of get_equity_risk_profile.
        Returns the same data but as a plain dict with _provenance attached.

        Args:
            security: Security object with sector, industry, debt, market_cap, revenue_mix

        Returns:
            Dict with erp, risk_free_rate, industry_unlevered_beta, levered_beta,
            cost_of_equity, erp_breakdown, sources and _provenance

        Raises:
            GroundTruthProviderError: market cap or industry beta is missing.

        Example:
            >>> gt = GroundTruthProvider()
            >>> blk = Security(ticker="BLK", sector="...", industry="Asset Management", ...)
            >>> p = gt.get_risk_profile(blk)
            >>> print(f"Blended ERP: {p['erp']:.2%}")
            >>> print(f"Cost of Equity: {p['cost_of_equity']:.2%}")
            >>> print(f"Source: {p['_provenance']['version']}")
        """
        profile, reason = self.get_equity_risk_profile_with_reason(security)
        if profile is None:
            raise GroundTruthProviderError(reason)
        profile_dict = asdict(profile)
        return attach_provenance(profile_dict)

    def get_wacc(
        self,
        security: Security,
        cost_of_debt: float = 0.04,  # Default 4% CoD if not provided
    ) -> float | None:
        """
        Calculate Weighted Average Cost of Capital using institutional baselines.

        Formula: WACC = (E/V)*CoE + (D/V)*(1-Tc)*CoD

        Where:
        - E/V = Equity weight = Market Cap / Enterprise Value
        - D/V = Debt weight = Total Debt / Enterprise Value
        - Tc = Marginal corporate tax rate (revenue-weighted statutory, Damodaran)
        - CoE = Bottom-up cost of equity (from ground truth)
        - CoD = Cost of debt (or default 4%)

        Args:
            security: Security object with debt, market_cap, fundamentals
            cost_of_debt: Cost of debt (use company's actual cost if available)

        Returns:
            WACC as a decimal (0.08 = 8%), or ``None`` when no bottom-up profile
            can be built (missing market cap or industry beta).
        """
        profile = self.get_equity_risk_profile(security)
        if profile is None or profile.tax_rate is None:
            return None

        market_cap = float(security.market.market_cap or 0.0)
        total_debt = security.fundamentals.total_debt or 0.0

        enterprise_value = market_cap + total_debt
        if enterprise_value <= 0:
            return profile.cost_of_equity

        equity_weight = market_cap / enterprise_value
        debt_weight = total_debt / enterprise_value

        return (equity_weight * profile.cost_of_equity) + (
            debt_weight * cost_of_debt * (1.0 - profile.tax_rate)
        )
