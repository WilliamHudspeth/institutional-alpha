"""Relative Reality: Justified Premium.

Calculates what EV/EBITDA multiple a security deserves relative to its sector
median, based on fundamental differences in ROIC and operating margin.

Formula:
  Justified Multiple = Sector Median EV/EBITDA
                       * (Company ROIC / Sector Median ROIC)
                       * (Company Operating Margin / Sector Median Margin)

The "Justified Premium Gap" measures the difference between the actual observed
premium/discount vs the premium/discount the company deserves.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from iam.data.security import Security
    from iam.valuation.damodaran_defaults import DamodaranUniverse


@dataclass
class JustifiedPremiumResult:
    """Output of justified premium calculation."""

    justified_multiple: float | None = None
    target_price: float | None = None
    actual_premium: float | None = None
    deserved_premium: float | None = None
    premium_gap: float | None = None
    notes: list[str] = None  # type: ignore

    def __post_init__(self):
        if self.notes is None:
            self.notes = []


def calculate_justified_premium(
    security: Security,
    universe: DamodaranUniverse | None = None,
) -> JustifiedPremiumResult:
    """Calculate justified premium/discount for a security.

    Args:
        security: Security object with fundamentals and market data
        universe: DamodaranUniverse containing sector medians

    Returns:
        JustifiedPremiumResult with justified multiple, target price, and gaps
    """
    result = JustifiedPremiumResult()

    m = security.market
    f = security.fundamentals

    if not security.sector:
        result.notes.append("Sector not specified.")
        return result

    if m.price is None or m.price <= 0:
        result.notes.append("Valid current price required for premium calculation.")
        return result

    if m.ev_ebitda is None or m.ev_ebitda <= 0:
        result.notes.append("Current EV/EBITDA required for premium calculation.")
        return result

    sector_medians = {}
    if universe and security.sector in universe.sector_multiples:
        sector_medians = universe.sector_multiples[security.sector]

    if "ev_ebitda" not in sector_medians:
        result.notes.append(f"Sector '{security.sector}' EV/EBITDA median not available.")
        return result

    sector_ev_ebitda = sector_medians.get("ev_ebitda")
    if sector_ev_ebitda is None or sector_ev_ebitda <= 0:
        result.notes.append("Sector EV/EBITDA median must be positive.")
        return result

    # Get company ROIC (most recent)
    company_roic = None
    if f.roic_history and len(f.roic_history) > 0:
        company_roic = f.roic_history[0]

    sector_roic = sector_medians.get("roic")

    # Get company operating margin
    company_margin = f.operating_margin

    sector_margin = sector_medians.get("operating_margin")

    # Build justified multiple
    justified_multiple = sector_ev_ebitda

    # Adjust for ROIC if available
    if company_roic is not None and sector_roic is not None and sector_roic != 0:
        roic_adjustment = company_roic / sector_roic
        justified_multiple *= roic_adjustment
    elif company_roic is not None or sector_roic is not None:
        result.notes.append("Sector ROIC median missing; ROIC adjustment skipped.")

    # Adjust for operating margin if available
    if company_margin is not None and sector_margin is not None and sector_margin != 0:
        margin_adjustment = company_margin / sector_margin
        justified_multiple *= margin_adjustment
    elif company_margin is not None or sector_margin is not None:
        result.notes.append("Sector operating margin median missing; margin adjustment skipped.")

    # Durability adjustment — sticky cash flows deserve a premium
    try:
        from iam.elasticity.durability import DurabilityScorer

        dur_score = DurabilityScorer().score(security)  # 0-1
        # map durability onto a ±20% multiple adjustment: 0.5 → 1.0×, 1.0 → 1.2×, 0.0 → 0.8×
        durability_adjustment = 0.8 + 0.4 * dur_score
        justified_multiple *= durability_adjustment
        result.notes.append(
            f"Durability adjustment: {durability_adjustment:.2f}x (score={dur_score:.2f})"
        )
    except Exception:
        result.notes.append("Durability adjustment skipped (scorer unavailable).")

    # Cyclicality discount — cyclical businesses deserve lower multiples
    revenue_mix = getattr(security, "revenue_mix", None) or {}
    cyclical_sectors = {"Industrials", "Materials", "Energy", "Consumer Discretionary"}
    is_cyclical = security.sector in cyclical_sectors if security.sector else False
    if is_cyclical:
        cyclicality_discount = 0.90  # 10% discount for cyclical names
        justified_multiple *= cyclicality_discount
        result.notes.append("Cyclicality discount: 0.90x (cyclical sector)")

    result.justified_multiple = justified_multiple

    # Calculate target price based on justified multiple
    if f.ebitda_ttm and f.ebitda_ttm > 0 and f.shares_outstanding and f.shares_outstanding > 0:
        target_ev = f.ebitda_ttm * justified_multiple
        target_eq = target_ev - (f.total_debt or 0) + (f.cash_and_equivalents or 0)
        result.target_price = target_eq / f.shares_outstanding

    # Calculate actual premium (current multiple vs sector median)
    actual_premium = (m.ev_ebitda / sector_ev_ebitda) - 1

    # Calculate deserved premium (justified multiple vs sector median)
    deserved_premium = (justified_multiple / sector_ev_ebitda) - 1

    # Calculate gap (actual vs deserved)
    premium_gap = actual_premium - deserved_premium

    result.actual_premium = actual_premium
    result.deserved_premium = deserved_premium
    result.premium_gap = premium_gap

    return result
