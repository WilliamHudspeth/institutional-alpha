from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from iam.data.security import MacroContext

# MacroContext.real_rate_trend / .pmi_direction are categorical ("rising" /
# "contracting" / ...); MacroRegimeClassifier only reads the *sign* of
# rate_change and where pmi sits relative to PMI_CONTRACTION_CEILING (50.0),
# so these proxies just need to land on the right side of those thresholds,
# not be numerically precise.
_RATE_TREND_TO_CHANGE = {"rising": 0.0025, "falling": -0.0025}
_PMI_DIRECTION_TO_VALUE = {"contracting": 45.0, "expanding": 55.0}


@dataclass
class MacroConditions:
    rate_change: float = 0.0
    pmi: float = 50.0
    inflation_rate: float = 0.02
    credit_spread: float = 0.01
    gdp_growth: float = 0.02

    @classmethod
    def from_context(cls, context: "MacroContext | None") -> "MacroConditions":
        """Map a Security's MacroContext (categorical) onto MacroConditions
        (numeric) for MacroRegimeClassifier. inflation_rate/gdp_growth have no
        MacroContext equivalent and stay at the neutral defaults above.
        """
        if context is None:
            return cls()
        return cls(
            rate_change=_RATE_TREND_TO_CHANGE.get(context.real_rate_trend, 0.0),
            pmi=_PMI_DIRECTION_TO_VALUE.get(context.pmi_direction, 50.0),
            credit_spread=(
                context.credit_spread_hy if context.credit_spread_hy is not None else cls().credit_spread
            ),
        )


@dataclass
class MacroShock:
    name: str
    rate_shock_bps: float
    growth_shock_pct: float
    inflation_shock_pct: float


STAGFLATION_SHOCK = MacroShock(
    name="Stagflation", rate_shock_bps=100.0, growth_shock_pct=-0.03, inflation_shock_pct=0.05
)
RECESSION_SHOCK = MacroShock(
    name="Recession", rate_shock_bps=-100.0, growth_shock_pct=-0.05, inflation_shock_pct=-0.02
)
RATE_HIKE_SHOCK = MacroShock(
    name="Rate Hike", rate_shock_bps=75.0, growth_shock_pct=-0.01, inflation_shock_pct=0.0
)
