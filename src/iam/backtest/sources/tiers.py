"""Tiered, capability-aware data routing.

The existing `CompositeDataSource` is a flat first-success chain. It has one real
correctness problem: a fundamentals request (`fetch_debt`) is offered to every
source in order, including price-only sources like Stooq whose `fetch_debt`
returns 0.0 by construction — so a *missing* fundamental is silently indistinguishable
from a genuine zero. That contaminates leverage/fragility penalties downstream.

This module adds a routing layer that selects sources by **(tier, capability)**:

  - **Tier** ranks sources by authority/quality (PREMIUM < OFFICIAL < COMMUNITY
    < FALLBACK; lower is better). Premium paid feeds answer first when present.
  - **Capability** declares what a source can actually serve (PRICE, DEBT,
    FUNDAMENTALS, HISTORY, POINT_IN_TIME). A field is only routed to sources that
    declare it — so `fetch_debt` never touches a price-only source, and a missing
    fundamental surfaces as "no capable source" rather than a fake 0.0.

Every answer records **provenance** (which source/tier served it and whether the
result is degraded — i.e. a more authoritative configured tier existed but was
unavailable or failed). `audit_summary()` is designed to be folded into the
backtest `manifest.json`, so a run that leaned on a degraded tier is visible and
reproducible rather than invisible.

Backward compatible: existing sources need no edits (their tier/capabilities are
resolved from `DEFAULT_REGISTRY` by `name`). New sources may instead declare
`tier`/`capabilities` as class attributes. `CompositeDataSource` is untouched.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Flag, IntEnum, auto

import pandas as pd

from .base import DataSource, DataSourceError


class DataTier(IntEnum):
    """Authority ranking; lower is more authoritative / preferred."""

    PREMIUM = 0   # paid, point-in-time, authoritative: FMP, Tiingo, Bloomberg
    OFFICIAL = 1  # free authoritative public filings: SEC EDGAR
    COMMUNITY = 2 # free best-effort: yfinance
    FALLBACK = 3  # degraded, price-only: Stooq


class Capability(Flag):
    NONE = 0
    PRICE = auto()
    DEBT = auto()
    FUNDAMENTALS = auto()
    HISTORY = auto()
    POINT_IN_TIME = auto()


@dataclass(frozen=True)
class SourceMeta:
    tier: DataTier
    capabilities: Capability


# Default tier/capability assignment for known sources, keyed by `DataSource.name`.
# Override per source via class attrs or by passing a registry to TieredDataSource.
DEFAULT_REGISTRY: dict[str, SourceMeta] = {
    "fmp": SourceMeta(
        DataTier.PREMIUM,
        Capability.PRICE | Capability.DEBT | Capability.FUNDAMENTALS
        | Capability.HISTORY | Capability.POINT_IN_TIME,
    ),
    "tiingo": SourceMeta(DataTier.PREMIUM, Capability.PRICE | Capability.HISTORY),
    "sec_edgar": SourceMeta(
        DataTier.OFFICIAL,
        Capability.FUNDAMENTALS | Capability.DEBT | Capability.POINT_IN_TIME,
    ),
    "yfinance": SourceMeta(
        DataTier.COMMUNITY,
        Capability.PRICE | Capability.DEBT | Capability.FUNDAMENTALS | Capability.HISTORY,
    ),
    "stooq": SourceMeta(DataTier.FALLBACK, Capability.PRICE | Capability.HISTORY),
}

_DEFAULT_META = SourceMeta(DataTier.COMMUNITY, Capability.PRICE | Capability.HISTORY)


@dataclass
class Provenance:
    """Record of which source answered a single field request."""

    field: str
    ticker: str
    source: str
    tier: DataTier
    degraded: bool


def _resolve_meta(source: DataSource, registry: dict[str, SourceMeta]) -> SourceMeta:
    """Tier/capabilities precedence: explicit class attrs > registry > default."""
    tier = getattr(source, "tier", None)
    caps = getattr(source, "capabilities", None)
    if isinstance(tier, DataTier) and isinstance(caps, Capability):
        return SourceMeta(tier, caps)
    return registry.get(source.name, _DEFAULT_META)


class TieredDataSource(DataSource):
    """Routes each request to the best tier among capability-eligible sources."""

    name = "tiered"

    def __init__(
        self,
        sources: list[DataSource],
        registry: dict[str, SourceMeta] | None = None,
        record_provenance: bool = True,
    ):
        if not sources:
            raise ValueError("TieredDataSource requires at least one source")
        reg = registry or DEFAULT_REGISTRY
        # (source, meta) sorted by tier ascending (best first)
        self._entries: list[tuple[DataSource, SourceMeta]] = sorted(
            ((s, _resolve_meta(s, reg)) for s in sources),
            key=lambda e: e[1].tier,
        )
        self.record_provenance = record_provenance
        self.provenance: list[Provenance] = []

    # -- capability helpers -------------------------------------------------- #
    def _configured_tiers(self, cap: Capability) -> list[DataTier]:
        return [m.tier for _, m in self._entries if cap in m.capabilities]

    def _eligible(self, cap: Capability) -> list[tuple[DataSource, SourceMeta]]:
        return [
            (s, m)
            for s, m in self._entries
            if cap in m.capabilities and s.is_available()
        ]

    def _record(self, field_name: str, ticker: str, meta: SourceMeta, cap: Capability) -> None:
        if not self.record_provenance:
            return
        configured = self._configured_tiers(cap)
        best = min(configured) if configured else meta.tier
        self.provenance.append(
            Provenance(
                field=field_name,
                ticker=ticker,
                source=next(s.name for s, m in self._entries if m is meta),
                tier=meta.tier,
                degraded=meta.tier > best,
            )
        )

    def is_available(self) -> bool:
        return any(s.is_available() for s, _ in self._entries)

    # -- routed methods ------------------------------------------------------ #
    def fetch_price(self, ticker: str, as_of: pd.Timestamp) -> float:
        errors: list[str] = []
        for source, meta in self._eligible(Capability.PRICE):
            try:
                price = source.fetch_price(ticker, as_of)
                self._record("price", ticker, meta, Capability.PRICE)
                return price
            except DataSourceError as e:
                errors.append(f"{source.name}: {e.reason}")
            except Exception as e:  # noqa: BLE001 — never let one source kill the chain
                errors.append(f"{source.name}: unexpected {e}")
        raise DataSourceError(self.name, ticker, f"no PRICE source succeeded: {'; '.join(errors) or 'none eligible'}")

    def fetch_debt(self, ticker: str, as_of: pd.Timestamp) -> float:
        """Route ONLY to DEBT-capable sources, preferring higher tiers.

        Returns 0.0 only when a capable source explicitly reports no debt — never
        because a price-only source was consulted. If no DEBT-capable source is
        configured/available, raises so the caller can decide, rather than
        fabricating a zero.
        """
        eligible = self._eligible(Capability.DEBT)
        if not eligible:
            raise DataSourceError(
                self.name, ticker,
                "no DEBT-capable source available (refusing to fabricate 0.0 "
                "from a price-only source)",
            )
        last_err = None
        for source, meta in eligible:
            try:
                debt = source.fetch_debt(ticker, as_of)
                self._record("debt", ticker, meta, Capability.DEBT)
                return debt  # an explicit 0.0 from a capable source is a real answer
            except Exception as e:  # noqa: BLE001
                last_err = e
                continue
        raise DataSourceError(self.name, ticker, f"all DEBT sources failed: {last_err}")

    def download_history(self, ticker: str, start: str, end: str) -> pd.DataFrame | None:
        for source, meta in self._eligible(Capability.HISTORY):
            df = source.download_history(ticker, start, end)
            if df is not None and not df.empty:
                self._record("history", ticker, meta, Capability.HISTORY)
                return df
        return None

    # -- audit --------------------------------------------------------------- #
    def degraded_fields(self) -> list[Provenance]:
        return [p for p in self.provenance if p.degraded]

    def audit_summary(self) -> dict:
        """Compact, manifest-ready summary of which tiers served the run."""
        by_source: dict[str, int] = {}
        by_tier: dict[str, int] = {}
        for p in self.provenance:
            by_source[p.source] = by_source.get(p.source, 0) + 1
            by_tier[p.tier.name] = by_tier.get(p.tier.name, 0) + 1
        degraded = self.degraded_fields()
        return {
            "requests": len(self.provenance),
            "by_source": by_source,
            "by_tier": by_tier,
            "degraded_count": len(degraded),
            "degraded_examples": [
                {"field": p.field, "ticker": p.ticker, "source": p.source, "tier": p.tier.name}
                for p in degraded[:10]
            ],
            "source_order": [s.name for s, _ in self._entries],
        }

    def __repr__(self) -> str:
        chain = " < ".join(f"{s.name}[{m.tier.name}]" for s, m in self._entries)
        return f"<TieredDataSource: {chain}>"


def build_tiered_source(
    *,
    include_premium: bool = True,
    extra_sources: list[DataSource] | None = None,
) -> TieredDataSource:
    """Assemble the default tiered chain, dropping unavailable sources.

    Zero-config preserved: premium sources gate on an API key via is_available(),
    so without keys they are simply skipped and the chain falls through to the
    free community/fallback tiers. With keys present, they take priority.
    """
    from .stooq_source import StooqSource
    from .yfinance_source import YFinanceSource

    sources: list[DataSource] = []
    if include_premium:
        # Imported lazily so missing optional deps never break the free path.
        try:
            from .fmp_source import FMPSource

            sources.append(FMPSource())
        except Exception:  # noqa: BLE001
            pass
        try:
            from .tiingo_source import TiingoSource

            sources.append(TiingoSource())
        except Exception:  # noqa: BLE001
            pass
    # SEC EDGAR: free, keyless, OFFICIAL-tier fundamentals/debt (no prices).
    try:
        from .sec_edgar_source import SecEdgarSource

        sources.append(SecEdgarSource())
    except Exception:  # noqa: BLE001
        pass
    sources.extend([YFinanceSource(), StooqSource()])
    if extra_sources:
        sources.extend(extra_sources)

    # Keep only sources that are actually usable right now.
    usable = [s for s in sources if s.is_available()]
    if not usable:  # pragma: no cover — yfinance/stooq effectively always usable
        usable = sources
    return TieredDataSource(usable)
