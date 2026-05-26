"""Penalty factors. Convention: returned ``value`` is in [0, 1], where
higher = more penalty (subtracted from the composite)."""

from __future__ import annotations

from iam.factors.base import PenaltyFactor, FactorContribution
from iam.data.security import Security


class FragilityPenalty(PenaltyFactor):
    """How vulnerable is the multiple to a small growth disappointment?

    fragility = pe_multiple / normalized_growth

    High fragility = small misses cause large multiple compression. This is
    the penalty that catches late-stage momentum trades.
    """
    name = "fragility_penalty"

    def compute(self, security: Security) -> FactorContribution:
        components: dict[str, float] = {}
        notes: list[str] = []
        confidence = 1.0
        m = security.market
        f = security.fundamentals

        if m.pe_forward is None and m.pe_ttm is None:
            return FactorContribution(name=self.name, value=0.0, confidence=0.3,
                                      notes=["No P/E available."])

        pe = m.pe_forward if m.pe_forward is not None else m.pe_ttm

        # Normalized growth — use trailing revenue CAGR as a proxy
        if len(f.revenue_history) >= 3 and f.revenue_history[-1] > 0:
            cagr = (f.revenue_history[0] / f.revenue_history[-1]) ** (1 / (len(f.revenue_history) - 1)) - 1
            growth_pct = max(cagr * 100, 1.0)  # floor at 1% to avoid div blow-ups
        else:
            confidence *= 0.6
            growth_pct = 10.0  # neutral assumption
            notes.append("No revenue history; assuming 10% growth for fragility.")

        # PEG-style fragility: pe / growth_pct
        peg = pe / growth_pct
        components["peg_like"] = peg
        # PEG 1.0 = neutral (0 penalty), 2.0 = high (0.5), 4.0+ = severe (1.0)
        penalty = max(0.0, min(1.0, (peg - 1.0) / 3.0))

        return FactorContribution(
            name=self.name,
            value=penalty,
            confidence=confidence,
            components=components,
            notes=notes,
        )


class LeveragePenalty(PenaltyFactor):
    """Balance sheet stress and refinancing risk."""
    name = "leverage_penalty"

    def compute(self, security: Security) -> FactorContribution:
        components: dict[str, float] = {}
        notes: list[str] = []
        confidence = 1.0
        f = security.fundamentals

        # Net debt / EBITDA
        if f.total_debt is not None and f.cash_and_equivalents is not None and f.ebitda_ttm and f.ebitda_ttm > 0:
            nd_ebitda = (f.total_debt - f.cash_and_equivalents) / f.ebitda_ttm
            # 0 = clean, 2 = OK, 4 = stressed, 6+ = distress
            components["net_debt_ebitda"] = max(0.0, min(1.0, (nd_ebitda - 1.0) / 5.0))
        else:
            confidence *= 0.7

        # Interest coverage = EBITDA / interest expense
        if f.ebitda_ttm and f.interest_expense_ttm and f.interest_expense_ttm > 0:
            cover = f.ebitda_ttm / f.interest_expense_ttm
            # >10x great (0 penalty), 3x neutral (0.5), <1.5x severe (1.0)
            components["interest_coverage"] = max(0.0, min(1.0, (5 - cover) / 4))
        else:
            confidence *= 0.85

        # Refinancing risk — % of debt maturing within 24m
        if f.debt_maturity_within_24m is not None and f.total_debt and f.total_debt > 0:
            maturity_pct = f.debt_maturity_within_24m / f.total_debt
            components["refinancing_risk"] = max(0.0, min(1.0, (maturity_pct - 0.2) * 2.5))

        # Liquidity (current ratio)
        if f.current_ratio is not None:
            # <1 stressed, 1.5 neutral, 2+ fine
            components["liquidity_ratio"] = max(0.0, min(1.0, (1.5 - f.current_ratio) / 1.0))

        if not components:
            return FactorContribution(name=self.name, value=0.0, confidence=0.3,
                                      notes=["No leverage inputs."])

        # Take the weighted average across what's available
        weights = {
            "net_debt_ebitda":  0.35,
            "interest_coverage": 0.30,
            "refinancing_risk": 0.20,
            "liquidity_ratio":  0.15,
        }
        total_w = sum(w for k, w in weights.items() if k in components)
        penalty = sum(components[k] * w for k, w in weights.items() if k in components) / total_w if total_w else 0.0

        return FactorContribution(
            name=self.name,
            value=penalty,
            confidence=confidence,
            components=components,
            notes=notes,
        )


class ExecutionRiskPenalty(PenaltyFactor):
    """Operational, supply chain, regulatory, geographic, and integration risk.

    Mostly qualitative — expected to come from ``security.qualitative``."""
    name = "execution_risk_penalty"

    QUALITATIVE_KEYS = [
        ("operational_complexity",   0.25),
        ("supply_chain_dependency",  0.20),
        ("regulatory_risk",          0.20),
        ("geographic_risk",          0.20),
        ("integration_risk",         0.15),
    ]

    def compute(self, security: Security) -> FactorContribution:
        components: dict[str, float] = {}
        notes: list[str] = []
        confidence = 1.0

        total_weight = 0.0
        weighted_sum = 0.0
        for key, weight in self.QUALITATIVE_KEYS:
            raw = security.qualitative.get(key)
            if raw is None:
                confidence *= 0.85
                notes.append(f"qualitative['{key}'] not provided")
                continue
            # Qualitative risk inputs in [0, 1] where 1 = high risk
            score = max(0.0, min(1.0, raw))
            components[key] = score
            weighted_sum += score * weight
            total_weight += weight

        value = weighted_sum / total_weight if total_weight > 0 else 0.0

        return FactorContribution(
            name=self.name,
            value=value,
            confidence=confidence,
            components=components,
            notes=notes,
        )
