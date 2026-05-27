from dataclasses import dataclass
from typing import Optional

@dataclass
class MacroConditions:
    rate_change: float = 0.0
    pmi: float = 50.0
    inflation_rate: float = 0.02
    credit_spread: float = 0.01
    gdp_growth: float = 0.02

@dataclass
class MacroShock:
    name: str
    rate_shock_bps: float
    growth_shock_pct: float
    inflation_shock_pct: float

STAGFLATION_SHOCK = MacroShock(name="Stagflation", rate_shock_bps=100.0, growth_shock_pct=-0.03, inflation_shock_pct=0.05)
RECESSION_SHOCK = MacroShock(name="Recession", rate_shock_bps=-100.0, growth_shock_pct=-0.05, inflation_shock_pct=-0.02)
RATE_HIKE_SHOCK = MacroShock(name="Rate Hike", rate_shock_bps=75.0, growth_shock_pct=-0.01, inflation_shock_pct=0.0)