"""Sector / industry from SEC submissions (SIC code), in the engine's Damodaran vocabulary.

``sic`` and ``sicDescription`` come from ``data.sec.gov/submissions/CIK##########.json``.
:data:`SIC_TABLE` maps SIC ranges to a ``(sector, industry)`` pair where ``industry`` is
always a key of ``DamodaranProvider.UNLEVERED_BETAS`` (so the bottom-up beta lookup finds
it) and ``sector`` is a yfinance-style broad sector name.

Constraint (enforced by a test): ``find_industry_unlevered_beta(sector, industry)`` must
return the beta of ``industry``. That lookup checks the table in order and accepts an exact
match on EITHER argument, so a sector label that is itself a table key must not precede the
intended industry key. This is why finance entries use the label "Financials" (not the key
"financial services") and oil and gas maps to the ``energy`` key.

SIC is a registry classification assigned to each filer, not an economic analysis: e.g. SIC
6211 (security brokers) covers BlackRock, an asset manager, and maps to ``brokerage``. A SIC
with no entry (blank-check shells 6770, holding offices 67xx, agriculture 01xx, 9995, ...) gives
``sector=None`` plus a reason: never an "Unknown" placeholder and never a guessed industry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from iam.data.edgar.client import EdgarClient


@dataclass(frozen=True)
class SicRange:
    low: int
    high: int  # inclusive
    sector: str
    industry: str  # always a DamodaranProvider.UNLEVERED_BETAS key


# Sorted, non-overlapping (checked by a test). Ranges follow the SEC SIC code list
# (https://www.sec.gov/search-filings/standard-industrial-classification-sic-code-list).
SIC_TABLE: tuple[SicRange, ...] = (
    SicRange(1000, 1099, "Basic Materials", "materials"),
    SicRange(1200, 1399, "Energy", "energy"),
    SicRange(1400, 1499, "Basic Materials", "materials"),
    SicRange(1500, 1799, "Industrials", "industrial"),
    SicRange(2000, 2099, "Consumer Defensive", "food & beverage"),
    SicRange(2100, 2199, "Consumer Defensive", "consumer staples"),
    SicRange(2200, 2399, "Consumer Cyclical", "consumer cyclical"),
    SicRange(2400, 2499, "Basic Materials", "materials"),
    SicRange(2500, 2599, "Consumer Cyclical", "consumer cyclical"),
    SicRange(2600, 2699, "Basic Materials", "materials"),
    SicRange(2700, 2799, "Communication Services", "entertainment"),
    SicRange(2800, 2829, "Basic Materials", "chemicals"),
    SicRange(2830, 2834, "Healthcare", "pharmaceuticals"),
    SicRange(2835, 2835, "Healthcare", "medical devices"),
    SicRange(2836, 2836, "Healthcare", "biotechnology"),
    SicRange(2840, 2844, "Consumer Defensive", "consumer staples"),
    SicRange(2845, 2899, "Basic Materials", "chemicals"),
    SicRange(2900, 2999, "Energy", "energy"),
    SicRange(3000, 3099, "Basic Materials", "materials"),
    SicRange(3100, 3199, "Consumer Cyclical", "consumer cyclical"),
    SicRange(3200, 3299, "Basic Materials", "materials"),
    SicRange(3300, 3329, "Basic Materials", "steel"),
    SicRange(3330, 3399, "Basic Materials", "materials"),
    SicRange(3400, 3499, "Industrials", "industrial"),
    SicRange(3500, 3569, "Industrials", "machinery"),
    SicRange(3570, 3575, "Technology", "hardware"),
    SicRange(3576, 3576, "Technology", "communications equipment"),
    SicRange(3577, 3579, "Technology", "hardware"),
    SicRange(3580, 3599, "Industrials", "machinery"),
    SicRange(3600, 3659, "Industrials", "industrial"),
    SicRange(3660, 3669, "Technology", "communications equipment"),
    SicRange(3670, 3673, "Technology", "hardware"),
    SicRange(3674, 3674, "Technology", "semiconductors"),
    SicRange(3675, 3699, "Technology", "hardware"),
    SicRange(3700, 3719, "Consumer Cyclical", "consumer cyclical"),
    SicRange(3720, 3799, "Industrials", "industrial"),
    SicRange(3800, 3839, "Industrials", "industrial"),
    SicRange(3840, 3859, "Healthcare", "medical devices"),
    SicRange(3900, 3999, "Consumer Cyclical", "consumer cyclical"),
    SicRange(4000, 4799, "Industrials", "transportation"),
    SicRange(4800, 4829, "Communication Services", "telecom"),
    SicRange(4830, 4841, "Communication Services", "entertainment"),
    SicRange(4890, 4899, "Communication Services", "telecom"),
    SicRange(4900, 4949, "Utilities", "utilities"),
    SicRange(4950, 4959, "Industrials", "industrial"),
    SicRange(4960, 4999, "Utilities", "utilities"),
    SicRange(5000, 5099, "Industrials", "industrial"),
    SicRange(5100, 5119, "Consumer Defensive", "consumer staples"),
    SicRange(5120, 5129, "Healthcare", "healthcare services"),
    SicRange(5130, 5199, "Consumer Defensive", "consumer staples"),
    SicRange(5200, 5399, "Consumer Discretionary", "retail"),
    SicRange(5400, 5499, "Consumer Defensive", "consumer staples"),
    SicRange(5500, 5799, "Consumer Discretionary", "retail"),
    SicRange(5800, 5899, "Consumer Discretionary", "hospitality"),
    SicRange(5900, 5999, "Consumer Discretionary", "retail"),
    SicRange(6000, 6099, "Financials", "banks"),
    SicRange(6100, 6199, "Financials", "financial services"),
    SicRange(6200, 6281, "Financials", "brokerage"),
    SicRange(6282, 6282, "Financials", "asset management"),
    SicRange(6283, 6299, "Financials", "brokerage"),
    SicRange(6300, 6499, "Financials", "insurance"),
    SicRange(6500, 6599, "Real Estate", "real estate"),
    SicRange(6720, 6729, "Financials", "asset management"),
    SicRange(6798, 6798, "REIT", "reit"),
    SicRange(7000, 7099, "Consumer Discretionary", "hospitality"),
    SicRange(7200, 7299, "Consumer Cyclical", "consumer cyclical"),
    SicRange(7370, 7370, "Communication Services", "internet"),
    SicRange(7371, 7371, "Technology", "it services"),
    SicRange(7372, 7372, "Technology", "software"),
    SicRange(7373, 7379, "Technology", "it services"),
    SicRange(7380, 7399, "Industrials", "industrial"),
    SicRange(7500, 7599, "Consumer Cyclical", "consumer cyclical"),
    SicRange(7600, 7699, "Industrials", "industrial"),
    SicRange(7800, 7899, "Communication Services", "entertainment"),
    SicRange(7900, 7999, "Consumer Discretionary", "entertainment"),
    SicRange(8000, 8099, "Healthcare", "healthcare services"),
    SicRange(8200, 8299, "Consumer Discretionary", "education"),
    SicRange(8700, 8730, "Industrials", "industrial"),
    SicRange(8731, 8731, "Healthcare", "biotechnology"),
    SicRange(8732, 8799, "Industrials", "industrial"),
)


@dataclass(frozen=True)
class SectorMapping:
    sic: str | None
    sector: str | None
    industry: str | None
    reason: str | None  # why sector/industry are None; None when mapped


@dataclass(frozen=True)
class FormerName:
    name: str
    from_: str | None
    to: str | None


@dataclass(frozen=True)
class CompanySector:
    cik: int
    name: str
    sic: str | None
    sic_description: str | None
    sector: str | None
    industry: str | None
    reason: str | None
    former_names: tuple[FormerName, ...] = field(default_factory=tuple)


def sector_for_sic(sic: str | int | None) -> SectorMapping:
    """Map a SIC code to ``(sector, industry)``; unmapped codes give None plus a reason."""
    text = "" if sic is None else str(sic).strip()
    if not text.isdigit():
        return SectorMapping(text or None, None, None, f"no usable SIC code ({sic!r})")
    code = int(text)
    for entry in SIC_TABLE:
        if entry.low <= code <= entry.high:
            return SectorMapping(text, entry.sector, entry.industry, None)
    return SectorMapping(text, None, None, f"SIC {text} has no mapping to a Damodaran industry")


def company_sector(submissions: dict[str, Any]) -> CompanySector:
    """Build the sector record (and CIK/name history) from a submissions JSON document."""
    mapping = sector_for_sic(submissions.get("sic"))
    former = tuple(
        FormerName(str(f.get("name", "")), f.get("from"), f.get("to"))
        for f in submissions.get("formerNames") or []
    )
    return CompanySector(
        cik=int(submissions["cik"]),
        name=str(submissions.get("name", "")),
        sic=mapping.sic,
        sic_description=submissions.get("sicDescription"),
        sector=mapping.sector,
        industry=mapping.industry,
        reason=mapping.reason,
        former_names=former,
    )


def fetch_company_sector(cik: int, client: EdgarClient | None = None) -> CompanySector:
    """Fetch submissions for ``cik`` (cached) and map the SIC code."""
    return company_sector((client or EdgarClient()).submissions(cik))
