"""Stage 3b: Business Reality Engine (Engine 3).

Evaluates the logical consistency and financial durability of forecast assumptions
against historical trends and fundamental realities (revenue stability, cash flow durability,
growth quality, and capital allocation discipline) backed by Aswath Damodaran's 5 laws.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from iam.data.security import Security
from iam.validation.damodaran_laws import DamodaranAuditReport, DamodaranLaws
from iam.valuation.types import Method, ValuationResult

logger = logging.getLogger(__name__)


@dataclass
class BusinessRealityReport:
    """Detailed diagnostic audit report of a business's operational reality."""

    ticker: str
    overall_score: float  # 0.0 to 1.0

    # 1. Revenue Quality
    revenue_quality_classification: (
        str  # "Highly Recurring" | "Moderate / Stable" | "Cyclical / Volatile"
    )
    revenue_quality_score: float
    revenue_quality_details: str

    # 2. Cash-Flow Durability
    fcf_durability_classification: (
        str  # "High Durability" | "Mean Reverting" | "Capital Markets Dependent"
    )
    fcf_durability_score: float
    fcf_durability_details: str

    # 3. Growth Quality
    growth_quality_classification: (
        str  # "High-Moat Organic" | "Moderate / Stable" | "Low-Quality Aggressive Scaling"
    )
    growth_quality_score: float
    growth_quality_details: str

    # 4. Capital Allocation
    capital_allocation_classification: (
        str  # "Share Buyback Discipline" | "Stable Capital Structure" | "Share Dilution"
    )
    capital_allocation_score: float
    capital_allocation_details: str

    # Damodaran Consistency Laws Audit
    damodaran_audit: DamodaranAuditReport

    warnings: list[str] = field(default_factory=list)


class BusinessRealityEngine:
    """Interrogates financial quality and penalizes/boosts model confidence based on operational realities."""

    @classmethod
    def analyze_security(
        cls,
        security: Security,
        forecast_growth: float,
        terminal_growth: float,
        discount_rate: float,
        roe: float,
    ) -> BusinessRealityReport:
        """Runs a comprehensive analysis of the security's fundamentals to rate business reality."""
        f = security.fundamentals
        warnings = []

        # 1. Revenue Quality Audit
        rev_history = f.revenue_history
        if rev_history and len(rev_history) >= 3:
            mean_rev = float(sum(rev_history) / len(rev_history))
            if mean_rev > 0:
                variance = sum((x - mean_rev) ** 2 for x in rev_history) / len(rev_history)
                std_rev = variance**0.5
                cv = std_rev / mean_rev

                if cv < 0.10:
                    rev_class = "Highly Recurring"
                    rev_score = 1.0
                elif cv <= 0.20:
                    rev_class = "Moderate / Stable"
                    rev_score = 0.8
                else:
                    rev_class = "Cyclical / Volatile"
                    rev_score = 0.5
                    warnings.append(
                        f"REVENUE WARNING: High historical revenue volatility (CV = {cv * 100:.1f}%). "
                        "High forecast growth might be fragile due to cyclicality."
                    )
                rev_details = f"Coef of Variation: {cv * 100:.1f}% over {len(rev_history)} years"
            else:
                rev_class = "Cyclical / Volatile"
                rev_score = 0.3
                rev_details = "Historical revenue mean is non-positive"
        else:
            rev_class = "Moderate / Stable"
            rev_score = 0.7
            rev_details = (
                f"Limited revenue history ({len(rev_history) if rev_history else 0} years)"
            )
            warnings.append(
                "REVENUE NOTE: Limited revenue history. Defaulting to moderate stability."
            )

        # 2. Cash-Flow Durability Audit
        fcf_history = f.fcf_history
        total_debt = f.total_debt or 0.0
        cash = f.cash_and_equivalents or 0.0
        net_debt = max(0.0, total_debt - cash)
        ebitda = f.ebitda_ttm or 0.0
        leverage = (net_debt / ebitda) if ebitda > 0 else 0.0

        if fcf_history and len(fcf_history) >= 2:
            all_positive = all(x > 0 for x in fcf_history)
            any_positive = any(x > 0 for x in fcf_history)

            if leverage > 4.0:
                fcf_class = "Capital Markets Dependent"
                fcf_score = 0.3
                warnings.append(
                    f"CASH FLOW WARNING: Leverage is exceptionally high ({leverage:.1f}x Net Debt/EBITDA). "
                    "Operational viability is dependent on capital markets."
                )
            elif all_positive:
                fcf_class = "High Durability"
                fcf_score = 1.0
            elif any_positive:
                fcf_class = "Mean Reverting"
                fcf_score = 0.6
                warnings.append(
                    "CASH FLOW NOTE: Free cash flow exhibits historical volatility/negative years."
                )
            else:
                fcf_class = "Capital Markets Dependent"
                fcf_score = 0.2
                warnings.append(
                    "CASH FLOW CRITICAL: Free cash flow consistently negative in historical years."
                )
            fcf_details = (
                f"History: {[round(x / 1e6, 1) for x in fcf_history]}M | Leverage: {leverage:.1f}x"
            )
        else:
            # Fallback using FCF TTM and leverage
            fcf_ttm = f.fcf_ttm or 0.0
            if leverage > 4.0:
                fcf_class = "Capital Markets Dependent"
                fcf_score = 0.3
            elif fcf_ttm > 0:
                fcf_class = "High Durability"
                fcf_score = 0.8
            else:
                fcf_class = "Capital Markets Dependent"
                fcf_score = 0.4
                warnings.append("CASH FLOW WARNING: TTM FCF is non-positive with no history.")
            fcf_details = f"TTM FCF: {fcf_ttm / 1e6:.1f}M | Leverage: {leverage:.1f}x"

        # 3. Growth Quality Audit
        roic_hist = f.roic_history
        current_roe = roic_hist[0] if roic_hist else 0.15

        if roic_hist and len(roic_hist) >= 2:
            # Expanding vs contracting ROIC
            trend = roic_hist[0] - roic_hist[-1]
            if current_roe >= 0.15 and trend > 0.01:
                growth_class = "High-Moat Organic"
                growth_score = 1.0
            elif current_roe >= 0.10 and trend >= -0.02:
                growth_class = "Moderate / Stable"
                growth_score = 0.8
            else:
                growth_class = "Low-Quality Aggressive Scaling"
                growth_score = 0.5
                warnings.append(
                    f"GROWTH WARNING: Historical return on capital (ROIC/ROE) is contracting ({trend * 100:+.1f}%). "
                    "Indicates potential growth dilution or competitive moat decay."
                )
            growth_details = f"Current ROIC: {current_roe * 100:.1f}% | Trend: {trend * 100:+.1f}%"
        else:
            growth_class = "Moderate / Stable"
            growth_score = 0.7
            growth_details = f"Current ROIC proxy: {current_roe * 100:.1f}%"

        # 4. Capital Allocation & Management Signals
        shares_hist = f.shares_outstanding_history
        if shares_hist and len(shares_hist) >= 2:
            # Index 0 is newest, last index is oldest
            dilution_rate = (shares_hist[0] / shares_hist[-1]) - 1.0

            if dilution_rate < -0.01:
                cap_class = "Share Buyback Discipline"
                cap_score = 1.0
            elif dilution_rate <= 0.01:
                cap_class = "Stable Capital Structure"
                cap_score = 0.8
            else:
                cap_class = "Share Dilution"
                cap_score = 0.4
                warnings.append(
                    f"CAPITAL WARNING: Significant shareholder dilution detected ({dilution_rate * 100:+.1f}%). "
                    "Management relies on equity issuance."
                )
            cap_details = (
                f"Dilution Rate: {dilution_rate * 100:+.1f}% over {len(shares_hist)} years"
            )
        else:
            cap_class = "Stable Capital Structure"
            cap_score = 0.7
            cap_details = "Limited share count history"

        # Additional capital discipline check: ROIC vs discount rate
        if current_roe < discount_rate:
            warnings.append(
                f"CAPITAL WARNING: Capital efficiency ({current_roe * 100:.1f}%) is below the cost of capital "
                f"({discount_rate * 100:.1f}%). High growth under this regime destroys economic value."
            )

        # Run Damodaran Consistency Laws Audit
        reinvestment_rate = min(forecast_growth / current_roe, 1.0) if current_roe > 0 else 1.0
        damodaran_report = DamodaranLaws.audit_security_valuation(
            security=security,
            growth=forecast_growth,
            terminal_growth=terminal_growth,
            discount_rate=discount_rate,
            roe=roe,
            reinvestment_rate=reinvestment_rate,
            forecast_margin=security.qualitative.get("forecast_margin"),
            target_roe=roe,
        )

        # Merge Damodaran warnings
        for verdict in damodaran_report.verdicts.values():
            warnings.extend(verdict.warnings)

        # Compute overall operational score
        scores = [rev_score, fcf_score, growth_score, cap_score, damodaran_report.overall_score]
        overall_score = float(sum(scores) / len(scores))

        return BusinessRealityReport(
            ticker=security.ticker,
            overall_score=overall_score,
            revenue_quality_classification=rev_class,
            revenue_quality_score=rev_score,
            revenue_quality_details=rev_details,
            fcf_durability_classification=fcf_class,
            fcf_durability_score=fcf_score,
            fcf_durability_details=fcf_details,
            growth_quality_classification=growth_class,
            growth_quality_score=growth_score,
            growth_quality_details=growth_details,
            capital_allocation_classification=cap_class,
            capital_allocation_score=cap_score,
            capital_allocation_details=cap_details,
            damodaran_audit=damodaran_report,
            warnings=warnings,
        )

    @classmethod
    def compute(
        cls,
        security: Security,
        forecast_growth: float,
        terminal_growth: float,
        discount_rate: float,
        roe: float,
    ) -> ValuationResult:
        """Executes the lens as a pipeline ValuationResult component."""
        report = cls.analyze_security(
            security=security,
            forecast_growth=forecast_growth,
            terminal_growth=terminal_growth,
            discount_rate=discount_rate,
            roe=roe,
        )

        # Build verdict lines
        verdict_lines = [
            f"Business Reality Quality Score: {report.overall_score * 100:.1f}%",
            f"  • Revenue Quality    : {report.revenue_quality_classification} ({report.revenue_quality_details})",
            f"  • Cash-Flow Durability: {report.fcf_durability_classification} ({report.fcf_durability_details})",
            f"  • Growth Quality      : {report.growth_quality_classification} ({report.growth_quality_details})",
            f"  • Capital Discipline  : {report.capital_allocation_classification} ({report.capital_allocation_details})",
            f"  • Damodaran Audit     : {report.damodaran_audit.overall_score * 100:.1f}% ({'PASSED' if report.damodaran_audit.passed else 'FAILED'})",
        ]

        if report.warnings:
            verdict_lines.append("")
            verdict_lines.append("⚠️ Operational Warnings & Inconsistencies:")
            for w in report.warnings:
                verdict_lines.append(f"  - {w}")

        return ValuationResult(
            method=Method.INTRINSIC,
            confidence=report.overall_score,  # Expose the overall reality score as the confidence metric
            components={"business_reality_report": report},
            assumptions={
                "forecast_growth": forecast_growth,
                "terminal_growth": terminal_growth,
                "discount_rate": discount_rate,
                "roe": roe,
            },
            notes=[f"Reality Score: {report.overall_score * 100:.1f}%"],
            verdict_text="\n".join(verdict_lines),
        )
