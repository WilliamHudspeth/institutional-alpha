"""Example lens plugin: free-cash-flow-yield valuation.

A small but realistic IA_LensPlugin demonstrating how a third-party plugin
influences a real pipeline run. It values the security as a cash-yield
instrument: the justified price is the price at which the company's TTM free
cash flow equals a required FCF yield (risk-free proxy plus an equity spread).

The plugin returns the dict shape the pipeline's plugin bridge understands
(see ``ValuationPipeline._apply_plugins`` in ``iam.pipeline.orchestrator``):

    {
        "lens_name":        str,
        "fair_value_low":   float | None,
        "fair_value_high":  float | None,
        "implied_move_pct": float | None,
        "confidence":       float,          # in [0, 1]
        "narrative":        str,
        "notes":            list[str],
    }
"""

from __future__ import annotations

from typing import Any, Dict

from iam.plugins.interfaces import IA_LensPlugin

# Required FCF yield = long-run risk-free proxy (4.3%) + 150bp equity spread.
_REQUIRED_FCF_YIELD = 0.058
# Band half-width: value the stream at required yield +/- 75bp.
_YIELD_BAND = 0.0075


class FcfYieldLens(IA_LensPlugin):
    """Values a security off its free-cash-flow yield vs. a required yield."""

    name = "fcf_yield_plugin"

    def analyze(self, data: Dict[str, Any]) -> Dict[str, Any]:
        fundamentals = data.get("fundamentals")
        market = data.get("market")

        price = getattr(market, "price", None) if market else None
        fcf_ttm = getattr(fundamentals, "fcf_ttm", None) if fundamentals else None
        shares = getattr(fundamentals, "shares_outstanding", None) if fundamentals else None

        if not price or not fcf_ttm or not shares or price <= 0 or shares <= 0:
            return {
                "lens_name": self.name,
                "fair_value_low": None,
                "fair_value_high": None,
                "implied_move_pct": None,
                "confidence": 0.0,
                "narrative": "Insufficient data (need price, fcf_ttm, shares_outstanding).",
                "notes": [],
            }

        fcf_per_share = fcf_ttm / shares
        actual_yield = fcf_per_share / price

        # Negative FCF: diagnostic only — a yield model has no justified price.
        if fcf_per_share <= 0:
            return {
                "lens_name": self.name,
                "fair_value_low": None,
                "fair_value_high": None,
                "implied_move_pct": None,
                "confidence": 0.2,
                "narrative": (
                    f"FCF/share is non-positive ({fcf_per_share:.2f}); "
                    "yield-based fair value not meaningful."
                ),
                "notes": [f"actual_fcf_yield={actual_yield:.2%}"],
            }

        # Justified price band: FCF stream valued at required yield +/- band.
        fair_high = fcf_per_share / (_REQUIRED_FCF_YIELD - _YIELD_BAND)
        fair_low = fcf_per_share / (_REQUIRED_FCF_YIELD + _YIELD_BAND)
        fair_mid = (fair_low + fair_high) / 2.0
        implied_move = fair_mid / price - 1.0

        # Confidence: strongest when the actual yield is far from the hurdle
        # (clear signal), tempered so the plugin never dominates core stages.
        signal_strength = min(abs(actual_yield - _REQUIRED_FCF_YIELD) / _REQUIRED_FCF_YIELD, 1.0)
        confidence = round(0.35 + 0.35 * signal_strength, 4)

        direction = "cheap" if actual_yield > _REQUIRED_FCF_YIELD else "expensive"
        narrative = (
            f"FCF yield {actual_yield:.2%} vs required {_REQUIRED_FCF_YIELD:.2%} -> "
            f"{direction} on cash yield; justified price "
            f"${fair_low:,.2f}-${fair_high:,.2f} vs ${price:,.2f} "
            f"({implied_move:+.1%})."
        )

        return {
            "lens_name": self.name,
            "fair_value_low": fair_low,
            "fair_value_high": fair_high,
            "implied_move_pct": implied_move,
            "confidence": confidence,
            "narrative": narrative,
            "notes": [
                f"fcf_per_share={fcf_per_share:.4f}",
                f"actual_fcf_yield={actual_yield:.4%}",
                f"required_fcf_yield={_REQUIRED_FCF_YIELD:.4%}",
            ],
        }
