"""Damodaran Ground Truth Provider for Macro and Industry Baselines.

This module is your institutional oracle for Cost of Capital. It replaces
noisy regression betas and historical ERPs with:

1. Unlevered Industry Betas: The pure business risk of a sector
2. Implied Equity Risk Premium: Forward-looking market risk premium
3. Country Risk Premiums: International equity premiums
4. Risk-Free Rate: Current Treasury yields

Data source: Aswath Damodaran (NYU Stern), updated monthly.
By using Damodaran's baselines instead of Yahoo Finance regressions,
your DCF valuations become immune to short-term market noise.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


class DamodaranProviderError(Exception):
    """Raised when Damodaran data fetch or calculation fails."""
    pass


@dataclass
class MacroBaselines:
    """The foundational macro environment for institutional valuation."""
    risk_free_rate: float
    implied_erp: float
    mature_market_premium: float


class DamodaranProvider:
    """
    Fetches and normalizes macro baselines and industry defaults
    from Aswath Damodaran (NYU Stern) and live Treasury data.

    This is the single source of truth for institutional cost of capital.
    Replace regression betas with bottom-up unlevered betas.
    Replace historical ERP with implied ERP.
    """

    # Damodaran's Implied Equity Risk Premium (Updated Jan 2026)
    # This is the forward-looking market risk premium derived from current S&P 500 valuation
    # Unlike historical ERP (5.5-6%), Implied ERP reacts to market dislocations
    CURRENT_IMPLIED_ERP = 0.046  # 4.6%

    # Risk-Free Rate (10-Year US Treasury)
    # This should be updated monthly from FRED API or Treasury website
    CURRENT_RISK_FREE_RATE = 0.0425  # 4.25%

    # Unlevered Industry Betas (Damodaran Jan 2026)
    # This is the pure business risk of each industry, stripped of debt effects
    # Retail scripts use 1.0 for everything; we use actual institutional data
    UNLEVERED_BETAS = {
        # Technology
        "software": 1.15,
        "hardware": 1.10,
        "semiconductors": 1.18,
        "internet": 1.20,
        "it services": 1.05,
        "communications equipment": 1.12,

        # Financial Services (note: these are VERY low unlevered because banks are so levered)
        "asset management": 0.59,
        "banks": 0.45,
        "financial services": 0.55,
        "insurance": 0.60,
        "brokerage": 0.65,

        # Healthcare
        "pharmaceuticals": 0.75,
        "medical devices": 0.80,
        "healthcare services": 0.85,
        "biotechnology": 0.95,

        # Consumer
        "consumer cyclical": 0.90,
        "consumer staples": 0.70,
        "food & beverage": 0.75,
        "retail": 0.85,

        # Industrial & Materials
        "industrial": 0.95,
        "machinery": 0.95,
        "materials": 1.00,
        "steel": 1.05,
        "chemicals": 0.95,

        # Energy & Utilities
        "energy": 0.70,
        "oil & gas": 0.75,
        "utilities": 0.40,  # Monopolies have very low pure business risk
        "renewable energy": 0.85,

        # Real Estate & Real Assets
        "real estate": 0.60,
        "reit": 0.65,
        "infrastructure": 0.70,

        # Other
        "transportation": 0.80,
        "hospitality": 0.95,
        "entertainment": 1.10,
        "education": 0.80,
        "telecom": 0.65,
    }

    # Country Equity Risk Premiums (Damodaran Jan 2026)
    # Premium over the US base ERP for emerging markets
    COUNTRY_RISK_PREMIUMS = {
        # Developed Markets (0% premium over US)
        "united states": 0.00,
        "us": 0.00,
        "usa": 0.00,
        "canada": 0.00,
        "united kingdom": 0.00,
        "germany": 0.00,
        "france": 0.00,
        "switzerland": 0.00,
        "japan": 0.00,
        "australia": 0.00,
        "netherlands": 0.00,
        "sweden": 0.00,

        # Emerging Markets
        "china": 0.015,  # 1.5% premium
        "india": 0.020,  # 2.0% premium
        "brazil": 0.025,  # 2.5% premium
        "mexico": 0.015,
        "russia": 0.035,  # Higher risk due to geopolitical factors
        "south korea": 0.010,
        "taiwan": 0.012,
        "thailand": 0.018,
        "vietnam": 0.022,
        "indonesia": 0.025,
        "philippines": 0.022,
        "singapore": 0.008,
    }

    @classmethod
    def get_risk_free_rate(cls) -> float:
        """
        Returns the current 10-Year US Treasury yield.

        In production, this would fetch live data from FRED API or Treasury website.
        For now, we use Damodaran's monthly updates (manually updated).
        """
        return cls.CURRENT_RISK_FREE_RATE

    @classmethod
    def get_macro_state(cls) -> MacroBaselines:
        """Synthesizes the complete macro environment."""
        return MacroBaselines(
            risk_free_rate=cls.get_risk_free_rate(),
            implied_erp=cls.CURRENT_IMPLIED_ERP,
            mature_market_premium=cls.CURRENT_IMPLIED_ERP,
        )

    @classmethod
    def get_country_risk_premium(cls, country_name: str) -> float:
        """
        Returns the Country Risk Premium (CRP) for international equities.

        Args:
            country_name: Country name or code

        Returns:
            Country risk premium as a decimal (0.015 = 1.5% additional premium)

        Example:
            >>> crp = DamodaranProvider.get_country_risk_premium("India")
            >>> # Cost of Equity = Rf + Beta * (ERP + CRP)
        """
        base_erp = cls.CURRENT_IMPLIED_ERP

        # Normalize country name
        country_clean = country_name.lower().strip()

        # Look up the country-specific premium
        for key, premium in cls.COUNTRY_RISK_PREMIUMS.items():
            if key == country_clean or country_clean.startswith(key):
                return premium

        # Default: assume developed market (0% premium)
        logger.warning(f"Country '{country_name}' not found; assuming developed market (0% CRP)")
        return 0.0

    @classmethod
    def get_industry_unlevered_beta(cls, sector: str, industry: str) -> float:
        """
        The Holy Grail of DCF risk pricing.

        Returns the unlevered (debt-adjusted) beta for an industry.
        This is the pure business risk, independent of capital structure.

        Retail DCF scripts use regression beta from Yahoo (incredibly noisy).
        Institutional desks use Damodaran's unlevered industry beta.

        The institutional alpha is in re-levering this with the company's
        actual debt-to-equity ratio, creating a "bottom-up" beta that is
        mathematically sound and stable.

        Args:
            sector: Industry sector (e.g., "Technology", "Healthcare")
            industry: Specific industry (e.g., "Software", "Pharmaceuticals")

        Returns:
            Unlevered beta (typically 0.4 to 1.2 for most industries)

        Example:
            >>> u_beta = DamodaranProvider.get_industry_unlevered_beta("Financial Services", "Asset Management")
            >>> # u_beta is 0.59 (very low pure business risk)
            >>> # But BlackRock's levered beta might be 1.1 due to debt
        """
        sector_clean = sector.lower().strip() if sector else ""
        industry_clean = industry.lower().strip() if industry else ""

        # Try exact matches first, then substring matches
        for key, beta in cls.UNLEVERED_BETAS.items():
            if industry_clean and key == industry_clean:
                logger.debug(f"[BETA] Found exact match for {industry}: {beta}")
                return beta
            if sector_clean and key == sector_clean:
                logger.debug(f"[BETA] Found sector match for {sector}: {beta}")
                return beta

        # Substring matching for partial matches
        search_terms = [industry_clean, sector_clean]
        for term in search_terms:
            if term:
                for key, beta in cls.UNLEVERED_BETAS.items():
                    if key in term or term in key:
                        logger.debug(f"[BETA] Found substring match for '{term}': {beta}")
                        return beta

        # Default: Global average unlevered beta
        logger.warning(
            f"Could not find unlevered beta for {sector} / {industry}; "
            f"using global default (0.85)"
        )
        return 0.85

    @staticmethod
    def relever_beta(unlevered_beta: float, debt_to_equity: float, tax_rate: float = 0.21) -> float:
        """
        Convert unlevered (asset) beta to levered (equity) beta.

        Formula: Levered Beta = Unlevered Beta * [1 + (1 - Tax Rate) * D/E]

        This is where the institutional magic happens. By using:
        1. Unlevered beta from Damodaran (industry standard, not noisy regression)
        2. Company's actual D/E ratio (current capital structure)
        3. Proper tax adjustment

        We create a bottom-up beta that is:
        - Stable (not affected by short-term stock price noise)
        - Forward-looking (reflects current leverage, not 5-year average)
        - Auditable (can explain to a committee exactly why this beta)

        Args:
            unlevered_beta: Industry unlevered beta
            debt_to_equity: Company's debt-to-market-cap ratio (D/E)
            tax_rate: Corporate tax rate (default 21% for US)

        Returns:
            Levered beta reflecting current capital structure
        """
        return unlevered_beta * (1.0 + (1.0 - tax_rate) * debt_to_equity)
