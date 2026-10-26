"""The return on equity that prices reinvestment in the FCFE models.

Both FCFE stages charge growth with reinvestment: FCFE = net income x (1 - g / ROE). A
single 15% ROE for every company over-charges high-return firms (a 40% ROE business
needs far less retained capital per point of growth) and under-charges low-return ones.
Damodaran: growth is earned by retention x ROE, measured on the firm's own books and
normalised over several years rather than one.

The company's normalised ROE applies through the high-growth years and fades to the
long-run market ROE by year 10; the terminal value uses the market ROE (excess returns do
not last forever). A user-supplied ``forecast_roe`` overrides everything, flat.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from iam.data.security import Security

# Long-run return on book equity for the market as a whole: the terminal ROE, and the
# fallback when the company has no usable history.
MARKET_ROE = 0.15
# Bounds on the company ROE. Buybacks and write-offs shrink book equity, so book ROE can run
# far above the economics (Apple's exceeds 100%); below 5% almost no growth is affordable.
ROE_BOUNDS: tuple[float, float] = (0.05, 0.50)
MIN_YEARS = 3
MAX_YEARS = 5


@dataclass(frozen=True)
class EquityReturn:
    """The ROE to use, where it came from, and the unclamped value."""

    roe: float
    source: str
    raw: float | None = None
    user: bool = False

    def path(self, years: int = 10, hold: int = 5, terminal: float = MARKET_ROE) -> list[float]:
        """ROE for each forecast year: flat for ``hold`` years, then linear to ``terminal``.

        A user-supplied ROE stays flat.
        """
        if self.user:
            return [self.roe] * years
        fade = max(1, years - hold)
        return [
            self.roe if t <= hold else self.roe + (terminal - self.roe) * (t - hold) / fade
            for t in range(1, years + 1)
        ]

    def terminal(self, market: float = MARKET_ROE) -> float:
        return self.roe if self.user else market


def _normalised(ni: Sequence[float], be: Sequence[float]) -> tuple[float, int] | None:
    """Sum of net income / sum of beginning book equity over consecutive usable years."""
    years: list[tuple[float, float]] = []
    for i in range(min(len(ni), len(be) - 1)):
        if be[i + 1] <= 0:
            break
        years.append((ni[i], be[i + 1]))
        if len(years) == MAX_YEARS:
            break
    if len(years) < MIN_YEARS:
        return None
    total_ni = sum(n for n, _ in years)
    if total_ni <= 0:
        return None
    return total_ni / sum(b for _, b in years), len(years)


def company_roe(security: Security, default: float = MARKET_ROE) -> EquityReturn:
    """The ROE for the FCFE reinvestment charge: user, normalised, trailing, then market."""
    q = security.qualitative or {}
    user = q.get("forecast_roe")
    if user is not None:
        return EquityReturn(float(user), "user forecast_roe", float(user), user=True)

    f = security.fundamentals
    lo, hi = ROE_BOUNDS
    norm = _normalised(f.net_income_history, f.book_equity_history)
    if norm is not None:
        raw, n = norm
        return EquityReturn(min(max(raw, lo), hi), f"normalised ROE over {n} years", raw)
    if f.net_income_ttm is not None and f.book_equity and f.book_equity > 0:
        raw = f.net_income_ttm / f.book_equity
        if raw > 0:
            return EquityReturn(min(max(raw, lo), hi), "trailing ROE", raw)
    return EquityReturn(default, "market ROE default (no usable equity history)")
