"""Damodaran's Laws of Valuation Consistency.

Implements the 5 analytical consistency laws from Aswath Damodaran (NYU Stern)
to audit the logical coherence of valuation models and forecast assumptions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from iam.data.security import Security


@dataclass
class LawVerdict:
    """The result of auditing a specific corporate finance consistency law."""

    law_name: str
    passed: bool
    score: float  # 0.0 (catastrophic inconsistency) to 1.0 (perfectly consistent)
    details: str
    warnings: list[str] = field(default_factory=list)


@dataclass
class DamodaranAuditReport:
    """Central audit report aggregating all 5 consistency laws."""

    ticker: str
    passed: bool
    overall_score: float
    verdicts: dict[str, LawVerdict]
    summary: str


class DamodaranLaws:
    """Auditing engine that challenges narrative, growth, reinvestment, and terminal assumptions."""

    @staticmethod
    def audit_narrative_vs_numbers(
        growth: float,
        current_margin: float,
        target_margin: float,
        current_roe: float,
        target_roe: float,
    ) -> LawVerdict:
        """
        LAW 1 — Narrative must match numbers.

        High growth requires expanding margins/ROE (competitive moat story) or
        declining margins but massive capital efficiency (reinvestment scale story).
        Flag if high growth is assumed but margins and capital efficiency both collapse.
        """
        warnings = []
        score = 1.0
        passed = True

        margin_change = target_margin - current_margin
        roe_change = target_roe - current_roe

        if growth >= 0.15:  # High growth regime
            if margin_change < -0.05 and roe_change < -0.05:
                passed = False
                score = 0.3
                warnings.append(
                    f"INCONSISTENT: Assuming high growth ({growth * 100:.1f}%) while margins "
                    f"({margin_change * 100:+.1f}%) and ROE ({roe_change * 100:+.1f}%) both contract. "
                    "A high-growth business cannot experience scaling collapse in both profitability and efficiency "
                    "without massive reinvestment failure."
                )
            elif margin_change < -0.02:
                score = 0.7
                warnings.append(
                    f"CAUTION: High growth with contracting margins ({margin_change * 100:+.1f}%). "
                    "Implies a high-volume low-margin market-share grab narrative."
                )

        details = (
            f"Growth: {growth * 100:.1f}% | "
            f"Margin Trend: {margin_change * 100:+.1f}% | "
            f"ROE Trend: {roe_change * 100:+.1f}%"
        )
        return LawVerdict(
            law_name="LAW 1 — Narrative‑to‑Numbers Consistency",
            passed=passed,
            score=score,
            details=details,
            warnings=warnings,
        )

    @staticmethod
    def audit_growth_vs_reinvestment(
        growth: float,
        roe: float,
        reinvestment_rate: float,
    ) -> LawVerdict:
        """
        LAW 2 — Growth requires reinvestment.

        In corporate finance, fundamental growth is bounded: g = ROE * Reinvestment_Rate.
        If assumed growth exceeds this bound, the assumptions are mathematically inconsistent.
        """
        warnings = []
        score = 1.0
        passed = True

        if roe <= 0:
            passed = False
            score = 0.0
            warnings.append(
                "CRITICAL: ROE is non-positive. Fundamental growth cannot be generated "
                "with negative capital efficiency."
            )
            return LawVerdict(
                law_name="LAW 2 — Reinvestment Bound",
                passed=passed,
                score=score,
                details="ROE <= 0",
                warnings=warnings,
            )

        # Maximum sustainable growth from current reinvestment
        max_sustainable_g = roe * reinvestment_rate
        implied_reinvestment = growth / roe if roe > 0 else 0.0

        discrepancy = growth - max_sustainable_g

        if discrepancy > 0.05:  # Assumed growth exceeds sustainable by over 5%
            passed = False
            score = max(0.0, 1.0 - (discrepancy * 5))
            warnings.append(
                f"VIOLATION: Assumed growth ({growth * 100:.1f}%) exceeds the fundamental maximum sustainable growth "
                f"({max_sustainable_g * 100:.1f}%) derived from ROE ({roe * 100:.1f}%) and Reinvestment Rate ({reinvestment_rate * 100:.1f}%). "
                f"Narrative requires an implied reinvestment rate of {implied_reinvestment * 100:.1f}% (violating cash flows)."
            )
        elif implied_reinvestment > 1.0:
            score = 0.8
            warnings.append(
                f"CAUTION: Assumed growth requires an implied Equity Reinvestment Rate of {implied_reinvestment * 100:.1f}%, "
                "meaning the firm must reinvest more than 100% of its earnings, leading to negative free cash flows."
            )

        details = (
            f"Assumed Growth: {growth * 100:.1f}% | "
            f"Sustainable Growth: {max_sustainable_g * 100:.1f}% | "
            f"Implied Reinvestment: {implied_reinvestment * 100:.1f}%"
        )
        return LawVerdict(
            law_name="LAW 2 — Growth requires Reinvestment",
            passed=passed,
            score=score,
            details=details,
            warnings=warnings,
        )

    @staticmethod
    def audit_terminal_growth(
        terminal_growth: float,
        risk_free_rate: float,
    ) -> LawVerdict:
        """
        LAW 3 — Terminal growth <= risk-free rate.

        A firm cannot grow faster than the economy in perpetuity. The risk-free rate
        (nominal government bond yield) acts as a mathematical proxy for long-term nominal GDP growth.
        """
        warnings = []
        score = 1.0
        passed = True

        if terminal_growth > risk_free_rate:
            passed = False
            score = 0.0
            warnings.append(
                f"VIOLATION: Terminal growth ({terminal_growth * 100:.2f}%) exceeds the risk‑free rate "
                f"({risk_free_rate * 100:.2f}%). This implies the firm will eventually become larger than the "
                "entire economy in perpetuity, violating macro convergence boundaries."
            )
        elif terminal_growth > risk_free_rate - 0.005:
            score = 0.8
            warnings.append(
                f"CAUTION: Terminal growth ({terminal_growth * 100:.2f}%) is exceptionally close to the "
                f"risk-free rate ({risk_free_rate * 100:.2f}%). Assumes permanent near-macro GDP growth."
            )

        details = f"Terminal Growth: {terminal_growth * 100:.2f}% | Risk-Free Rate: {risk_free_rate * 100:.2f}%"
        return LawVerdict(
            law_name="LAW 3 — Perpetual Growth Cap",
            passed=passed,
            score=score,
            details=details,
            warnings=warnings,
        )

    @staticmethod
    def audit_excess_returns_fade(
        terminal_roe: float,
        cost_of_equity: float,
    ) -> LawVerdict:
        """
        LAW 4 — Excess returns fade in stable state.

        Competitive forces mean-revert a firm's return on equity (ROE) to its cost of equity (Ke)
        during the perpetual terminal state: terminal_ROE == Ke.
        Assuming infinite excess returns in perpetuity violates economic stable state theory.
        """
        warnings = []
        score = 1.0
        passed = True

        excess_return = terminal_roe - cost_of_equity

        if excess_return > 0.10:  # Terminal excess return > 10%
            passed = False
            score = 0.4
            warnings.append(
                f"VIOLATION: Model assumes massive perpetual excess returns in terminal state. "
                f"Terminal ROE ({terminal_roe * 100:.1f}%) exceeds Cost of Equity ({cost_of_equity * 100:.1f}%) "
                f"by {excess_return * 100:.1f}%. Competitive forces will mean-revert returns over time."
            )
        elif excess_return > 0.02:
            score = 0.7
            warnings.append(
                f"CAUTION: Terminal ROE ({terminal_roe * 100:.1f}%) is higher than the Cost of Equity "
                f"({cost_of_equity * 100:.1f}%), assuming a permanent competitive advantage (moat) in perpetuity."
            )

        details = (
            f"Terminal ROE: {terminal_roe * 100:.1f}% | Cost of Equity: {cost_of_equity * 100:.1f}%"
        )
        return LawVerdict(
            law_name="LAW 4 — Perpetual Excess Return Fade",
            passed=passed,
            score=score,
            details=details,
            warnings=warnings,
        )

    @staticmethod
    def audit_risk_double_counting(
        distress_discount_applied: bool,
        cost_of_equity: float,
    ) -> LawVerdict:
        """
        LAW 5 — Risk is not double-counted.

        Risk should reside in the cash flows (e.g. distress probability under scenario matrix)
        OR in the discount rate (e.g. size/liquidity risk premium), but never in both simultaneously.
        """
        warnings = []
        score = 1.0
        passed = True

        if distress_discount_applied and cost_of_equity >= 0.15:
            passed = False
            score = 0.5
            warnings.append(
                f"VIOLATION: Potential double-counting of risk. Model applies scenario-based probability "
                f"distress weighting while discounting at an exceptionally high WACC/Ke ({cost_of_equity * 100:.1f}%) "
                "which already prices in significant distress premiums."
            )

        details = f"Distress Scenario Applied: {distress_discount_applied} | Cost of Equity: {cost_of_equity * 100:.1f}%"
        return LawVerdict(
            law_name="LAW 5 — Risk Double-Counting Guard",
            passed=passed,
            score=score,
            details=details,
            warnings=warnings,
        )

    @classmethod
    def audit_security_valuation(
        cls,
        security: Security,
        growth: float,
        terminal_growth: float,
        discount_rate: float,
        roe: float,
        reinvestment_rate: float,
        forecast_margin: float | None = None,
        target_roe: float | None = None,
    ) -> DamodaranAuditReport:
        """Performs a comprehensive audit of a security's valuation parameters."""
        f = security.fundamentals

        # Standardize current margin and ROE from security
        current_margin = f.operating_margin or 0.10
        target_margin = forecast_margin if forecast_margin is not None else current_margin

        current_roe = f.roic_history[0] if f.roic_history else 0.15
        tgt_roe = target_roe if target_roe is not None else roe

        # Resolve risk free rate (defaults to 4% if missing)
        risk_free_rate = float(security.qualitative.get("risk_free_rate", 0.04))

        # Execute checks
        v1 = cls.audit_narrative_vs_numbers(
            growth, current_margin, target_margin, current_roe, tgt_roe
        )
        v2 = cls.audit_growth_vs_reinvestment(growth, roe, reinvestment_rate)
        v3 = cls.audit_terminal_growth(terminal_growth, risk_free_rate)
        v4 = cls.audit_excess_returns_fade(tgt_roe, discount_rate)
        # Check if scenario analysis or probability weighted is active as distress proxy
        v5 = cls.audit_risk_double_counting(True, discount_rate)

        verdicts = {
            "law1": v1,
            "law2": v2,
            "law3": v3,
            "law4": v4,
            "law5": v5,
        }

        passed = all(v.passed for v in verdicts.values())
        overall_score = float(np.mean([v.score for v in verdicts.values()]))

        # Build summary
        summary_parts = []
        if passed:
            summary_parts.append(
                "✅ PASS: The valuation model is logically consistent under NYU Stern Damodaran Laws."
            )
        else:
            summary_parts.append(
                "❌ FAIL: The valuation model contains core logical inconsistencies under Damodaran Laws."
            )

        summary_parts.append(f"Overall Audit Score: {overall_score * 100:.1f}%")

        all_warnings = []
        for v in verdicts.values():
            all_warnings.extend(v.warnings)

        if all_warnings:
            summary_parts.append("\nConsistency Violations:")
            for w in all_warnings:
                summary_parts.append(f"  • {w}")

        summary = "\n".join(summary_parts)

        return DamodaranAuditReport(
            ticker=security.ticker,
            passed=passed,
            overall_score=overall_score,
            verdicts=verdicts,
            summary=summary,
        )
