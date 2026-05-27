"""Damodaran Jan 2026 regression-based fair-multiple predictions.

Each regression takes a set of fundamentals and predicts what a stock's
multiple *should* be given those fundamentals — not what the peer median
happens to be today.  Comparing the predicted multiple to the actual
multiple surfaces whether a stock is cheap or expensive *relative to its own
fundamentals*, independent of whether the whole sector is stretched.

Source: Aswath Damodaran, January 2026 market-wide regressions.
Inputs are always in decimal form: 12% = 0.12.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, Optional

Region = Literal["US", "Europe", "Japan", "Emerging", "Global"]
Multiple = Literal["PE", "PEG", "PBV", "EV_IC", "EV_Sales", "EV_EBITDA"]

# ---------------------------------------------------------------------------
# Regression coefficient table
# Each entry: { "const": intercept, variable_name: coefficient, ... }
# The special key "ln_gEPS" means the coefficient applies to ln(gEPS).
# ---------------------------------------------------------------------------
REGRESSIONS: dict[Region, dict[Multiple, dict[str, float]]] = {
    "US": {
        "PE":       {"const": 13.12, "Beta": 10.52, "gEPS": 36.47, "Payout": 8.46},
        "PEG":      {"const": -0.60, "Payout": 0.56, "ln_gEPS": -1.48, "Beta": 0.23},
        "PBV":      {"const": -0.79, "gEPS": -0.47, "Beta": 1.49, "ROE": 20.90, "Payout": 0.17},
        "EV_IC":    {"const": 5.75, "g": 1.12, "ROIC": -0.01, "DFR": -0.06},
        "EV_Sales": {"const": 6.77, "g": 9.51, "OperMargin": 0.36, "DFR": -0.02, "TaxRate": -0.12},
        "EV_EBITDA":{"const": 18.82, "g": 39.30, "DFR": -0.20, "ROIC": 1.77},
    },
    "Europe": {
        "PE":       {"const": 9.72, "Beta": 2.99, "gEPS": 49.82, "Payout": 7.98},
        "PEG":      {"const": -0.91, "Payout": 0.76, "ln_gEPS": -1.57},
        "PBV":      {"const": 0.73, "gEPS": 3.92, "Beta": 0.13, "ROE": 10.75, "Payout": -0.25},
        "EV_IC":    {"const": 4.46, "g": 0.90, "ROIC": 1.50, "DFR": -0.05},
        "EV_Sales": {"const": 5.08, "g": 4.03, "OperMargin": 2.99, "DFR": -0.02, "TaxRate": -0.09},
        "EV_EBITDA":{"const": 18.15, "g": 35.25, "DFR": -0.11, "TaxRate": -0.12, "ROIC": 2.29},
    },
    "Japan": {
        "PE":       {"const": 4.51, "Beta": 4.28, "gEPS": 42.26, "Payout": 10.46},
        "PEG":      {"const": -0.70, "Payout": 0.35, "ln_gEPS": -1.19, "Beta": 0.23},
        "PBV":      {"const": -0.55, "gEPS": 4.64, "Beta": 0.38, "ROE": 14.23},
        "EV_IC":    {"const": 3.01, "g": 8.96, "ROIC": 0.16, "DFR": -0.04},
        "EV_Sales": {"const": 2.48, "g": 11.54, "OperMargin": 0.44, "DFR": -0.01, "TaxRate": -0.03},
        "EV_EBITDA":{"const": 10.94, "g": 35.22, "DFR": -0.05, "ROIC": 1.22},
    },
    "Emerging": {
        "PE":       {"const": 14.47, "Beta": -0.51, "gEPS": 52.25, "Payout": 2.22},
        "PEG":      {"const": -0.78, "Payout": 0.82, "ln_gEPS": -1.43, "Beta": -0.09},
        "PBV":      {"const": 1.32, "gEPS": 2.73, "Beta": 0.43, "ROE": 4.53},
        "EV_IC":    {"const": 3.42, "g": 2.74, "ROIC": 0.11, "DFR": -0.04},
        "EV_Sales": {"const": 4.10, "g": 3.17, "OperMargin": 0.65, "DFR": -0.01, "TaxRate": -0.03},
        "EV_EBITDA":{"const": 21.24, "g": 33.07, "DFR": -0.12, "TaxRate": -0.19, "ROIC": -4.88},
    },
    "Global": {
        "PE":       {"const": 21.11, "Beta": 2.22, "gEPS": 21.49, "Payout": 0.89},
        "PEG":      {"const": -0.12, "Payout": 0.56, "ln_gEPS": 0.48, "Beta": -0.13},
        "PBV":      {"const": 0.71, "gEPS": 1.13, "Beta": -0.12, "ROE": 16.72, "Payout": -0.11},
        "EV_IC":    {"const": 4.67, "g": 1.53, "ROIC": 0.04, "DFR": -0.05},
        "EV_Sales": {"const": 5.44, "g": 4.97, "OperMargin": 0.38, "DFR": -0.01, "TaxRate": -0.07},
        "EV_EBITDA":{"const": 21.79, "g": 30.86, "DFR": -0.13, "TaxRate": -0.24, "ROIC": 2.72},
    },
}


@dataclass
class RegressionInputs:
    """Fundamentals bundle fed into the Damodaran regressions.

    All rates are decimals (0.12 = 12%).  Defaults are US-market averages and
    are intentionally conservative — missing inputs reduce signal quality rather
    than crashing the pipeline.

    Construct manually or via ``iam.data.yahoo.build_regression_inputs(ticker)``.
    """
    region: Region = "US"
    beta: float = 1.0
    g_eps: float = 0.10       # expected EPS growth rate
    payout: float = 0.0       # dividend payout ratio
    roe: float = 0.15         # return on equity
    g: float = 0.10           # revenue / FCFE growth
    roic: float = 0.12        # return on invested capital
    dfr: float = 0.20         # debt / (debt + market cap)
    oper_margin: float = 0.15 # operating margin
    tax_rate: float = 0.21    # effective tax rate

    def to_dict(self) -> dict[str, float]:
        return {
            "Beta": self.beta,
            "gEPS": self.g_eps,
            "Payout": self.payout,
            "ROE": self.roe,
            "g": self.g,
            "ROIC": self.roic,
            "DFR": self.dfr,
            "OperMargin": self.oper_margin,
            "TaxRate": self.tax_rate,
        }


def predict_multiple(region: Region, multiple: Multiple, inputs: dict[str, float]) -> float:
    """Predict a fair multiple from fundamentals via the Damodaran Jan 2026 regression.

    Raises KeyError for unknown region/multiple.
    Raises ValueError when PEG is requested with gEPS <= 0 (ln is undefined).
    """
    coeffs = REGRESSIONS[region][multiple]
    value = coeffs.get("const", 0.0)
    for key, coeff in coeffs.items():
        if key == "const":
            continue
        if key == "ln_gEPS":
            g_eps = inputs.get("gEPS", 0.0)
            if g_eps <= 0:
                raise ValueError(
                    f"PEG regression requires gEPS > 0 (got {g_eps}). "
                    "Pass a positive expected growth rate."
                )
            value += coeff * math.log(g_eps)
        else:
            value += coeff * inputs.get(key, 0.0)
    return round(value, 4)


def predict_all(region: Region, inputs: dict[str, float]) -> dict[str, Optional[float]]:
    """Predict all six multiples for a region.

    PEG is set to None when gEPS <= 0 rather than raising.  All other
    multiples always return a value.
    """
    results: dict[str, Optional[float]] = {}
    for multiple in REGRESSIONS[region]:
        try:
            results[multiple] = predict_multiple(region, multiple, inputs)
        except ValueError:
            results[multiple] = None
    return results
