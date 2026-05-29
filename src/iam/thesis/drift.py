"""Thesis Drift Detection Engine.

Tracks the operational assumptions (growth, margin, ROIC, leverage) supporting active
investment theses and compares them against current operational actuals to measure
the fragility of the investment thesis.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from iam.data.security import Security

logger = logging.getLogger(__name__)


@dataclass
class ThesisDriftReport:
    """The result of auditing investment thesis drift and operational fragility."""

    ticker: str
    overall_fragility: float  # 0.0 (perfectly robust) to 1.0 (extremely fragile / broken)
    thesis_fragilities: dict[str, float] = field(default_factory=dict)
    drift_warnings: list[str] = field(default_factory=list)
    drift_details: dict[str, list[str]] = field(default_factory=dict)


class ThesisDriftDetector:
    """Monitors margins, growth, and leverage drift to detect structural thesis decay."""

    @classmethod
    def detect_drift(cls, security: Security) -> ThesisDriftReport:
        """Audits all registered theses for assumption drifts vs actual fundamentals."""
        ticker = security.ticker
        f = security.fundamentals
        m = security.market

        thesis_fragilities: dict[str, float] = {}
        drift_details: dict[str, list[str]] = {}
        drift_warnings = []

        if not security.theses:
            return ThesisDriftReport(
                ticker=ticker,
                overall_fragility=0.0,
                drift_warnings=["No active theses registered for drift detection."],
            )

        # Get actual operational benchmarks
        actual_growth = 0.05  # Default baseline fallback
        if f.revenue_history and len(f.revenue_history) >= 2:
            # Most recent revenue growth
            actual_growth = (f.revenue_history[0] / f.revenue_history[1]) - 1.0

        actual_margin = f.operating_margin or 0.10
        actual_roe = f.roic_history[0] if f.roic_history else 0.12

        total_debt = f.total_debt or 0.0
        cash = f.cash_and_equivalents or 0.0
        net_debt = max(0.0, total_debt - cash)
        ebitda = f.ebitda_ttm or 0.0
        actual_leverage = (net_debt / ebitda) if ebitda > 0 else 0.0

        for thesis in security.theses:
            thesis_warnings = []
            score_discrepancies = []

            for assumption in thesis.assumptions:
                name = assumption.name.lower()
                val = assumption.value

                if not isinstance(val, (int, float)):
                    continue

                # 1. Growth assumption drift
                if any(x in name for x in ["growth", "cagr"]):
                    # If assumption growth is much higher than actual growth
                    if val > actual_growth:
                        diff = val - actual_growth
                        severity = min(1.0, diff / 0.10)  # normalized per 10% gap
                        score_discrepancies.append(severity)
                        if diff > 0.05:
                            thesis_warnings.append(
                                f"Growth Drift: Assumed {val * 100:.1f}% growth vs {actual_growth * 100:.1f}% actual TTM trend."
                            )
                    else:
                        score_discrepancies.append(0.0)

                # 2. Margin assumption drift
                elif "margin" in name:
                    if val > actual_margin:
                        diff = val - actual_margin
                        severity = min(1.0, diff / 0.05)  # normalized per 5% margin gap
                        score_discrepancies.append(severity)
                        if diff > 0.03:
                            thesis_warnings.append(
                                f"Margin Drift: Assumed steady-state margin of {val * 100:.1f}% vs {actual_margin * 100:.1f}% actual."
                            )
                    else:
                        score_discrepancies.append(0.0)

                # 3. ROIC/ROE assumption drift
                elif any(x in name for x in ["roic", "roe"]):
                    if val > actual_roe:
                        diff = val - actual_roe
                        severity = min(1.0, diff / 0.08)  # normalized per 8% return gap
                        score_discrepancies.append(severity)
                        if diff > 0.05:
                            thesis_warnings.append(
                                f"Capital Return Drift: Assumed return of {val * 100:.1f}% vs {actual_roe * 100:.1f}% actual."
                            )
                    else:
                        score_discrepancies.append(0.0)

                # 4. Leverage / Debt drift
                elif any(x in name for x in ["leverage", "debt_to_ebitda"]):
                    if val < actual_leverage:
                        diff = actual_leverage - val
                        severity = min(1.0, diff / 2.0)  # normalized per 2.0x leverage turn gap
                        score_discrepancies.append(severity)
                        if diff > 1.0:
                            thesis_warnings.append(
                                f"Leverage Drift: Assumed limit of {val:.1f}x leverage vs {actual_leverage:.1f}x actual Net Debt/EBITDA."
                            )
                    else:
                        score_discrepancies.append(0.0)

            # Compute fragility for this specific thesis
            fragility = (
                float(sum(score_discrepancies) / len(score_discrepancies))
                if score_discrepancies
                else 0.0
            )
            thesis_fragilities[thesis.label] = fragility
            drift_details[thesis.label] = thesis_warnings

            # Aggregate warnings
            for w in thesis_warnings:
                drift_warnings.append(f"[{thesis.label} Thesis] {w}")

        # Overall fragility is the average fragility of the theses
        overall_fragility = (
            float(sum(thesis_fragilities.values()) / len(thesis_fragilities))
            if thesis_fragilities
            else 0.0
        )

        return ThesisDriftReport(
            ticker=ticker,
            overall_fragility=overall_fragility,
            thesis_fragilities=thesis_fragilities,
            drift_warnings=drift_warnings,
            drift_details=drift_details,
        )
