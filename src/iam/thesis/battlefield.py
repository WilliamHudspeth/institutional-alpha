"""Stage 8: Valuation Battlefield Engine.

Surfaces Bull, Bear, Base, Market-implied, and Intrinsic theses side-by-side to map out
competing interpretations of business reality under uncertainty, replacing the traditional
single fair-value estimate with a multi-thesis debate matrix.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from iam.data.security import Security
from iam.pipeline.orchestrator import PipelineReport

logger = logging.getLogger(__name__)


@dataclass
class BattlefieldReport:
    """The complete multi-thesis battlefield analysis comparing valuation models side-by-side."""

    ticker: str
    thesis_targets: dict[str, float] = field(default_factory=dict)
    key_disagreement: str = ""
    comparison_matrix: dict[str, dict[str, Any]] = field(default_factory=field)
    verdict_text: str = ""


class ValuationBattlefield:
    """Juxtaposes different structural interpretations of the business side-by-side."""

    @classmethod
    def generate_battlefield(
        cls,
        security: Security,
        pipeline_report: PipelineReport,
    ) -> BattlefieldReport:
        """Constructs a side-by-side comparison of active theses and market expectations."""
        ticker = security.ticker
        matrix: dict[str, dict[str, Any]] = {}
        thesis_targets: dict[str, float] = {}

        # 1. Gather thesis fair values
        # Extract intrinsic fair value
        intrinsic_fv = pipeline_report.intrinsic.fair_value_per_share or 0.0
        thesis_targets["Intrinsic Baseline"] = intrinsic_fv

        # Extract market implied or current price
        price = security.market.price or 0.0
        thesis_targets["Market Expectations"] = price

        # Extract scenarios from Intrinsic DCF
        intrinsic_components = pipeline_report.intrinsic.components
        if "scenarios" in intrinsic_components:
            scenarios = intrinsic_components["scenarios"]
            for label, details in scenarios.items():
                if "target" in details:
                    thesis_targets[label] = details["target"]

        # 2. Build Comparison Matrix of parameters
        # Market Expectations parameters (from reverse DCF results if available)
        reverse_components = pipeline_report.reverse_dcf.components
        market_g = reverse_components.get("implied_growth", 0.08)
        market_margin = security.fundamentals.operating_margin or 0.10
        market_discount = pipeline_report.reverse_dcf.assumptions.get("discount_rate", 0.09)

        matrix["Market Expectations"] = {
            "Fair Value": price,
            "Growth Rate": market_g,
            "Operating Margin": market_margin,
            "Discount Rate": market_discount,
            "Moat Protection": "Implied Market Consensus",
        }

        # Intrinsic parameters
        int_assumptions = pipeline_report.intrinsic.assumptions
        int_g = int_assumptions.get("high_growth", 0.10)
        int_margin = security.fundamentals.operating_margin or 0.10
        int_discount = int_assumptions.get("discount_rate", 0.09)

        matrix["Intrinsic Baseline"] = {
            "Fair Value": intrinsic_fv,
            "Growth Rate": int_g,
            "Operating Margin": int_margin,
            "Discount Rate": int_discount,
            "Moat Protection": "Consistent Operational Baseline",
        }

        # Scenarios
        if "scenarios" in intrinsic_components:
            scenarios = intrinsic_components["scenarios"]
            for label, details in scenarios.items():
                matrix[label] = {
                    "Fair Value": details.get("target", 0.0),
                    "Growth Rate": details.get("g", 0.0),
                    "Operating Margin": details.get("margin", int_margin),
                    "Discount Rate": details.get("wacc", int_discount),
                    "Moat Protection": "Scenario-Specific Bounds",
                }

        # 3. Identify and label the single key disagreement
        disagreement_parts = []
        growth_gap = int_g - market_g
        if abs(growth_gap) > 0.02:
            direction = "exceeds" if growth_gap > 0 else "lags"
            disagreement_parts.append(
                f"Growth Expectation Gap: The Intrinsic model assumes {int_g * 100:.1f}% growth, "
                f"which {direction} the market's implied expectations of {market_g * 100:.1f}% by {abs(growth_gap) * 100:.1f}%."
            )

        # Check margin expectations if forecast is different
        forecast_margin = security.qualitative.get("forecast_margin")
        if forecast_margin is not None and abs(forecast_margin - market_margin) > 0.02:
            margin_gap = forecast_margin - market_margin
            direction = "higher than" if margin_gap > 0 else "lower than"
            disagreement_parts.append(
                f"Margin Disagreement: Intrinsic steady-state margin of {forecast_margin * 100:.1f}% is "
                f"{direction} actual TTM margin of {market_margin * 100:.1f}%."
            )

        if not disagreement_parts:
            disagreement_parts.append(
                "High Convergence: Intrinsic forecasts and market implied consensus are structurally aligned."
            )

        key_disagreement = " | ".join(disagreement_parts)

        # 4. Format verdict output text
        verdict_lines = [
            f"=== {ticker} Valuation Battlefield View ===",
            f"Key Disagreement: {key_disagreement}",
            "",
            "Thesis Comparison Matrix:",
            f"  {'Thesis Scenario':<22} | {'Fair Value':<10} | {'Growth Rate':<11} | {'Margin':<7} | {'Discount':<8}",
            "  " + "-" * 70,
        ]

        for name, params in matrix.items():
            verdict_lines.append(
                f"  {name:<22} | "
                f"${params['Fair Value']:<9.2f} | "
                f"{params['Growth Rate'] * 100:<10.1f}% | "
                f"{params['Operating Margin'] * 100:<6.1f}% | "
                f"{params['Discount Rate'] * 100:<7.1f}%"
            )

        verdict_text = "\n".join(verdict_lines)

        return BattlefieldReport(
            ticker=ticker,
            thesis_targets=thesis_targets,
            key_disagreement=key_disagreement,
            comparison_matrix=matrix,
            verdict_text=verdict_text,
        )
