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

import logging
from dataclasses import dataclass
from functools import lru_cache

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

    # Regional Equity Risk Premiums (Damodaran Jan 2026)
    REGIONAL_ERPS = {
        "north_america": 0.046,
        "europe": 0.052,
        "apac_developed": 0.048,
        "emerging_markets": 0.075,
        "latin_america": 0.085,
        "middle_east": 0.065,
    }

    # Country ISO Codes to Regional Mapping
    COUNTRY_ERPS = {
        "US": 0.046,
        "CA": 0.046,
        "GB": 0.052,
        "DE": 0.052,
        "FR": 0.052,
        "JP": 0.048,
        "AU": 0.048,
        "SG": 0.048,
        "CN": 0.075,
        "IN": 0.075,
        "KR": 0.048,
        "TW": 0.048,
        "BR": 0.085,
        "MX": 0.085,
    }

    COUNTRY_TO_REGION = {
        "US": "north_america",
        "CA": "north_america",
        "GB": "europe",
        "DE": "europe",
        "FR": "europe",
        "JP": "apac_developed",
        "AU": "apac_developed",
        "SG": "apac_developed",
        "CN": "emerging_markets",
        "IN": "emerging_markets",
        "BR": "latin_america",
        "MX": "latin_america",
    }

    REGION_ALIASES = {
        "americas": "north_america",
        "na": "north_america",
        "emea": "europe",
        "eu": "europe",
        "apac": "apac_developed",
        "asia": "apac_developed",
        "em": "emerging_markets",
        "latam": "latin_america",
    }

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

        Fetches live data from the markets data layer.
        """
        try:
            from iam.data.markets import fetch_market_snapshot

            snapshot = fetch_market_snapshot()
            # Assuming '10Y' is the key for 10-year treasury in the market data
            return float(snapshot.get("10Y", cls.CURRENT_RISK_FREE_RATE))
        except Exception:
            # Fallback to hardcoded value if live fetch fails
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
    @lru_cache(maxsize=512)
    def resolve_erp(cls, key: str) -> float:
        """Resolve ERP from country code, region name, or alias.

        Args:
            key: Country code (US, CN), region (north_america, europe), or alias (NA, APAC)

        Returns:
            ERP as decimal (0.046 = 4.6%)

        Examples:
            >>> cls.resolve_erp("US")      # 0.046
            >>> cls.resolve_erp("CN")      # 0.075
            >>> cls.resolve_erp("north_america")  # 0.046
            >>> cls.resolve_erp("na")      # 0.046 (alias)
        """
        k_lower = key.lower()

        # Try aliases first (including lowercase country names)
        if k_lower in cls.REGION_ALIASES:
            canon = cls.REGION_ALIASES[k_lower]
            return cls.REGIONAL_ERPS[canon]

        # Try 2-letter country codes
        if len(key) == 2:
            k_upper = key.upper()
            if k_upper in cls.COUNTRY_ERPS:
                return cls.COUNTRY_ERPS[k_upper]
            region = cls.COUNTRY_TO_REGION.get(k_upper, "north_america")
            return cls.REGIONAL_ERPS[region]

        # Try region names as last resort
        if k_lower in cls.REGIONAL_ERPS:
            return cls.REGIONAL_ERPS[k_lower]

        # Default to North America
        return cls.REGIONAL_ERPS["north_america"]

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
            >>> # But a leveraged firm's levered beta might be 1.1 due to debt
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
            f"Could not find unlevered beta for {sector} / {industry}; using global default (0.85)"
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
