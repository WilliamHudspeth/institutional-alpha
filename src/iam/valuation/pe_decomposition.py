"""P/E decomposition: the no-growth (commodity) value and the franchise premium.

Owner's valuation paper section 2.1 splits the price in two:

    EPS               = net_income_ttm / shares_outstanding
    commodity P/E     = 1 / Ke
    steady-state value= EPS / Ke            (what the earnings are worth with no growth)
    franchise premium = price - steady-state value
    PVGO share        = franchise premium / price

Ke is the Stage 1 consensus cost of equity the report actually used. Nothing is
defaulted: if EPS, price or Ke is missing (or EPS <= 0), :func:`decompose_pe`
returns ``(None, reason)``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PEDecomposition:
    eps: float
    price: float
    ke: float
    pe: float  # price / EPS
    commodity_pe: float  # 1 / Ke
    franchise_pe: float  # pe - commodity_pe
    steady_state_value: float  # EPS / Ke, per share
    franchise_premium: float  # price - steady_state_value, per share
    pvgo_share: float  # franchise_premium / price
    ke_source: str
    eps_source: str


def decompose_pe(
    *,
    net_income_ttm: float | None,
    shares_outstanding: float | None,
    price: float | None,
    ke: float | None,
    ke_source: str,
) -> tuple[PEDecomposition | None, str | None]:
    """Return ``(decomposition, None)`` or ``(None, reason)``."""
    if (
        net_income_ttm is None
        or shares_outstanding is None
        or shares_outstanding <= 0
        or net_income_ttm <= 0
    ):
        return None, "P/E decomposition needs positive EPS (net_income_ttm / shares_outstanding)"
    if price is None or price <= 0:
        return None, "P/E decomposition needs a market price"
    if ke is None or ke <= 0:
        return None, "P/E decomposition needs the Stage 1 consensus Ke"

    eps = net_income_ttm / shares_outstanding
    commodity_pe = 1.0 / ke
    steady_state = eps / ke
    premium = price - steady_state
    pe = price / eps
    return (
        PEDecomposition(
            eps=eps,
            price=price,
            ke=ke,
            pe=pe,
            commodity_pe=commodity_pe,
            franchise_pe=pe - commodity_pe,
            steady_state_value=steady_state,
            franchise_premium=premium,
            pvgo_share=premium / price,
            ke_source=ke_source,
            eps_source="net_income_ttm / shares_outstanding",
        ),
        None,
    )
