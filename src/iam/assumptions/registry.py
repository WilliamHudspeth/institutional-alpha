"""Centralized assumption registry with predefined profiles and sector overrides.

Provides standardized assumption sets across Conservative/Base/Aggressive risk profiles
and allows sector-specific customization. Enables reproducible, auditable analysis.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Optional


class RiskProfile(str, Enum):
    """Risk tolerance profiles for assumption selection."""

    CONSERVATIVE = "conservative"
    BASE = "base"
    AGGRESSIVE = "aggressive"


@dataclass
class AssumptionSet:
    """A set of financial assumptions for valuation."""

    # Cost of capital
    risk_free_rate: float  # e.g., 0.04
    market_risk_premium: float  # e.g., 0.055
    wacc: float  # e.g., 0.09
    terminal_growth_rate: float  # e.g., 0.025

    # Forecast horizon and growth
    forecast_years: int  # e.g., 5
    near_term_growth: float  # e.g., 0.08 (next 3 years)
    mid_term_growth: float  # e.g., 0.06 (years 4-5)

    # Quality adjustments
    quality_of_earnings_discount: float  # e.g., 0.95 (5% discount for low quality)
    leverage_penalty_factor: float  # e.g., 0.10 (10% penalty per unit D/E)

    # Valuation bounds
    min_pe_acceptable: float  # e.g., 5.0
    max_pe_acceptable: float  # e.g., 50.0
    min_pb_acceptable: float  # e.g., 0.5
    max_pb_acceptable: float  # e.g., 10.0

    # Sentiment/positioning
    sentiment_reversion_likelihood: float  # e.g., 0.60 (60% chance of reversion)
    crowding_severity_multiplier: float  # e.g., 1.5 (1.5x impact for crowded)

    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return asdict(self)


# ============================================================================
# PREDEFINED PROFILES
# ============================================================================

CONSERVATIVE_PROFILE = AssumptionSet(
    risk_free_rate=0.045,
    market_risk_premium=0.060,
    wacc=0.095,
    terminal_growth_rate=0.020,
    forecast_years=5,
    near_term_growth=0.06,
    mid_term_growth=0.04,
    quality_of_earnings_discount=0.90,
    leverage_penalty_factor=0.15,
    min_pe_acceptable=5.0,
    max_pe_acceptable=40.0,
    min_pb_acceptable=0.5,
    max_pb_acceptable=8.0,
    sentiment_reversion_likelihood=0.70,
    crowding_severity_multiplier=1.8,
    metadata={
        "description": "Conservative assumptions for risk-averse investors",
        "use_case": "Value investing, downside protection focus",
        "bias": "Underestimates upside, assumes mean reversion",
    },
)

BASE_PROFILE = AssumptionSet(
    risk_free_rate=0.040,
    market_risk_premium=0.055,
    wacc=0.090,
    terminal_growth_rate=0.025,
    forecast_years=5,
    near_term_growth=0.08,
    mid_term_growth=0.06,
    quality_of_earnings_discount=0.95,
    leverage_penalty_factor=0.10,
    min_pe_acceptable=8.0,
    max_pe_acceptable=50.0,
    min_pb_acceptable=0.6,
    max_pb_acceptable=10.0,
    sentiment_reversion_likelihood=0.60,
    crowding_severity_multiplier=1.5,
    metadata={
        "description": "Base case assumptions for balanced analysis",
        "use_case": "Fundamental equity research, institutional consensus",
        "bias": "Neutral, balanced risk/reward",
    },
)

AGGRESSIVE_PROFILE = AssumptionSet(
    risk_free_rate=0.035,
    market_risk_premium=0.050,
    wacc=0.085,
    terminal_growth_rate=0.030,
    forecast_years=5,
    near_term_growth=0.12,
    mid_term_growth=0.10,
    quality_of_earnings_discount=0.98,
    leverage_penalty_factor=0.05,
    min_pe_acceptable=12.0,
    max_pe_acceptable=80.0,
    min_pb_acceptable=1.0,
    max_pb_acceptable=15.0,
    sentiment_reversion_likelihood=0.40,
    crowding_severity_multiplier=1.0,
    metadata={
        "description": "Aggressive assumptions for growth-oriented investors",
        "use_case": "Growth investing, conviction-based analysis",
        "bias": "Overestimates upside, assumes trend continuation",
    },
)

# ============================================================================
# SECTOR-SPECIFIC OVERRIDES
# ============================================================================

SECTOR_OVERRIDES: dict[str, dict[RiskProfile, dict[str, float]]] = {
    "Technology": {
        RiskProfile.BASE: {
            "near_term_growth": 0.15,
            "mid_term_growth": 0.10,
            "terminal_growth_rate": 0.035,
            "max_pe_acceptable": 60.0,
            "max_pb_acceptable": 12.0,
        },
        RiskProfile.CONSERVATIVE: {
            "near_term_growth": 0.10,
            "mid_term_growth": 0.06,
            "wacc": 0.105,
        },
        RiskProfile.AGGRESSIVE: {
            "near_term_growth": 0.20,
            "mid_term_growth": 0.15,
            "terminal_growth_rate": 0.040,
            "max_pe_acceptable": 100.0,
        },
    },
    "Financials": {
        RiskProfile.BASE: {
            "near_term_growth": 0.05,
            "mid_term_growth": 0.04,
            "terminal_growth_rate": 0.020,
            "wacc": 0.095,
            "leverage_penalty_factor": 0.08,
        },
        RiskProfile.CONSERVATIVE: {
            "wacc": 0.105,
            "leverage_penalty_factor": 0.20,
            "max_pe_acceptable": 35.0,
        },
        RiskProfile.AGGRESSIVE: {
            "wacc": 0.080,
            "leverage_penalty_factor": 0.02,
            "max_pe_acceptable": 70.0,
        },
    },
    "Healthcare": {
        RiskProfile.BASE: {
            "near_term_growth": 0.08,
            "mid_term_growth": 0.07,
            "terminal_growth_rate": 0.030,
            "max_pe_acceptable": 55.0,
        },
        RiskProfile.CONSERVATIVE: {
            "quality_of_earnings_discount": 0.92,
            "sentiment_reversion_likelihood": 0.65,
        },
        RiskProfile.AGGRESSIVE: {
            "near_term_growth": 0.14,
            "mid_term_growth": 0.12,
            "terminal_growth_rate": 0.040,
        },
    },
    "Utilities": {
        RiskProfile.BASE: {
            "near_term_growth": 0.03,
            "mid_term_growth": 0.03,
            "terminal_growth_rate": 0.025,
            "wacc": 0.075,
            "max_pe_acceptable": 30.0,
        },
        RiskProfile.CONSERVATIVE: {
            "wacc": 0.080,
            "min_pb_acceptable": 0.8,
        },
        RiskProfile.AGGRESSIVE: {
            "wacc": 0.070,
            "near_term_growth": 0.05,
            "max_pe_acceptable": 40.0,
        },
    },
    "Consumer": {
        RiskProfile.BASE: {
            "near_term_growth": 0.05,
            "mid_term_growth": 0.04,
            "terminal_growth_rate": 0.020,
            "sentiment_reversion_likelihood": 0.65,
        },
        RiskProfile.CONSERVATIVE: {
            "quality_of_earnings_discount": 0.88,
            "crowding_severity_multiplier": 2.0,
        },
        RiskProfile.AGGRESSIVE: {
            "near_term_growth": 0.10,
            "mid_term_growth": 0.08,
            "sentiment_reversion_likelihood": 0.40,
        },
    },
    "Energy": {
        RiskProfile.BASE: {
            "near_term_growth": 0.02,
            "mid_term_growth": 0.02,
            "terminal_growth_rate": 0.015,
            "sentiment_reversion_likelihood": 0.50,
            "crowding_severity_multiplier": 2.0,
        },
        RiskProfile.CONSERVATIVE: {
            "wacc": 0.105,
            "quality_of_earnings_discount": 0.85,
            "max_pe_acceptable": 25.0,
        },
        RiskProfile.AGGRESSIVE: {
            "near_term_growth": 0.08,
            "terminal_growth_rate": 0.030,
            "max_pe_acceptable": 40.0,
        },
    },
}


# ============================================================================
# REGISTRY CLASS
# ============================================================================


class AssumptionRegistry:
    """Central registry for assumption profiles and sector overrides."""

    def __init__(self):
        """Initialize with default profiles."""
        self.profiles: dict[RiskProfile, AssumptionSet] = {
            RiskProfile.CONSERVATIVE: CONSERVATIVE_PROFILE,
            RiskProfile.BASE: BASE_PROFILE,
            RiskProfile.AGGRESSIVE: AGGRESSIVE_PROFILE,
        }
        self.sector_overrides = SECTOR_OVERRIDES.copy()
        self._change_log: list[dict] = []

    def get_profile(self, risk_profile: RiskProfile) -> AssumptionSet:
        """Get assumptions for a given risk profile.

        Args:
            risk_profile: Conservative, Base, or Aggressive

        Returns:
            AssumptionSet with all assumptions
        """
        return self.profiles[risk_profile]

    def get_sector_adjusted(self, risk_profile: RiskProfile, sector: str) -> AssumptionSet:
        """Get assumptions with sector-specific overrides applied.

        Args:
            risk_profile: Conservative, Base, or Aggressive
            sector: Sector name (e.g., 'Technology', 'Financials')

        Returns:
            AssumptionSet with sector overrides applied
        """
        base = self.get_profile(risk_profile)
        base_dict = base.to_dict()

        # Apply sector overrides if they exist
        if sector in self.sector_overrides:
            sector_overrides = self.sector_overrides[sector].get(risk_profile, {})
            base_dict.update(sector_overrides)

        return AssumptionSet(**base_dict)

    def register_sector_override(
        self,
        sector: str,
        risk_profile: RiskProfile,
        overrides: dict[str, float],
    ) -> None:
        """Register or update a sector-specific override.

        Args:
            sector: Sector name
            risk_profile: Risk profile to override
            overrides: Dict of {assumption_name: new_value}
        """
        if sector not in self.sector_overrides:
            self.sector_overrides[sector] = {}

        self.sector_overrides[sector][risk_profile] = overrides

        self._change_log.append(
            {
                "action": "register_override",
                "sector": sector,
                "profile": risk_profile.value,
                "overrides": overrides,
            }
        )

    def get_change_log(self) -> list[dict]:
        """Get audit trail of all assumption changes."""
        return self._change_log.copy()

    def compare_profiles(
        self, profile_a: RiskProfile, profile_b: RiskProfile
    ) -> dict[str, tuple[float, float]]:
        """Compare two profiles side-by-side.

        Returns:
            Dict of {assumption_name: (value_a, value_b)}
        """
        assumptions_a = self.get_profile(profile_a).to_dict()
        assumptions_b = self.get_profile(profile_b).to_dict()

        comparison = {}
        for key in assumptions_a:
            if key != "metadata":
                comparison[key] = (assumptions_a[key], assumptions_b[key])

        return comparison

    def generate_report(self, risk_profile: RiskProfile, sector: str | None = None) -> str:
        """Generate a text report of assumptions.

        Args:
            risk_profile: Risk profile to report
            sector: Optional sector for sector-adjusted view

        Returns:
            Formatted text report
        """
        if sector:
            assumptions = self.get_sector_adjusted(risk_profile, sector)
            title = f"{sector.upper()} — {risk_profile.value.upper()} ASSUMPTIONS"
        else:
            assumptions = self.get_profile(risk_profile)
            title = f"{risk_profile.value.upper()} ASSUMPTIONS"

        lines = [
            "=" * 70,
            title,
            "=" * 70,
            "",
            "COST OF CAPITAL",
            f"  Risk-Free Rate:           {assumptions.risk_free_rate:>8.2%}",
            f"  Market Risk Premium:      {assumptions.market_risk_premium:>8.2%}",
            f"  WACC:                     {assumptions.wacc:>8.2%}",
            "",
            "GROWTH & TERMINAL VALUE",
            f"  Forecast Years:           {assumptions.forecast_years:>8}",
            f"  Near-Term Growth:         {assumptions.near_term_growth:>8.2%}",
            f"  Mid-Term Growth:          {assumptions.mid_term_growth:>8.2%}",
            f"  Terminal Growth Rate:     {assumptions.terminal_growth_rate:>8.2%}",
            "",
            "QUALITY & RISK ADJUSTMENTS",
            f"  Quality of Earnings:      {assumptions.quality_of_earnings_discount:>8.2%}",
            f"  Leverage Penalty:         {assumptions.leverage_penalty_factor:>8.2%}",
            f"  Sentiment Reversion:      {assumptions.sentiment_reversion_likelihood:>8.2%}",
            f"  Crowding Multiplier:      {assumptions.crowding_severity_multiplier:>8.2f}x",
            "",
            "VALUATION BOUNDS",
            f"  P/E Range:                {assumptions.min_pe_acceptable:>6.1f}x - {assumptions.max_pe_acceptable:>6.1f}x",
            f"  P/B Range:                {assumptions.min_pb_acceptable:>6.1f}x - {assumptions.max_pb_acceptable:>6.1f}x",
            "=" * 70,
        ]

        return "\n".join(lines)


# Global registry instance
REGISTRY = AssumptionRegistry()
