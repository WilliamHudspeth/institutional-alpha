"""Growth rate triangulation: five independent estimators, confidence-weighted blend.

No single growth estimate is reliable. This module combines five independent
estimators of forward growth, each weighted by its company-specific variance,
producing a final estimate with calibrated confidence.

Estimators:
    1. Implied growth (reverse DCF)    — what the market prices now
    2. Historical CAGR (smoothed)      — what the company actually did
    3. Sustainable growth (ROE-based)  — what is mathematically possible
    4. Bottom-up build                 — what fundamentals support
    5. Sector median                   — industry baseline prior

Weighting: w_i = 1 / sigma_i^2, where sigma_i is the estimator's variance.
Bayesian shrinkage: posterior = (Sum w_i * g_i) / (Sum w_i + tau_prior)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional
import math

import numpy as np


GrowthMethod = Literal[
    "implied", "historical", "sustainable", "bottom_up", "sector"
]


@dataclass
class GrowthEstimate:
    """Single growth estimate with diagnostic metadata."""

    method: GrowthMethod
    value: float  # Annual growth rate, e.g., 0.08 for 8%
    confidence: float  # 0.0 to 1.0, higher = more reliable
    variance: float  # Estimator variance, lower = more reliable
    notes: str = ""

    @property
    def weight(self) -> float:
        """Inverse-variance weight for blending."""
        if self.variance <= 0:
            return 0.0
        return 1.0 / self.variance


@dataclass
class TriangulatedGrowth:
    """Final triangulated growth estimate with full audit trail."""

    blended_growth: float
    confidence: float  # 0.0 to 1.0
    estimates: list[GrowthEstimate] = field(default_factory=list)
    method_disagreement: float = 0.0  # Std dev across estimators
    dominant_method: Optional[GrowthMethod] = None
    margin_adjustment: float = 0.0  # Applied margin trajectory penalty/bonus
    raw_growth: float = 0.0  # Before margin adjustment

    def to_dict(self) -> dict:
        return {
            "blended_growth": round(self.blended_growth, 4),
            "raw_growth": round(self.raw_growth, 4),
            "margin_adjustment": round(self.margin_adjustment, 4),
            "confidence": round(self.confidence, 3),
            "method_disagreement": round(self.method_disagreement, 4),
            "dominant_method": self.dominant_method,
            "estimates": [
                {
                    "method": e.method,
                    "value": round(e.value, 4),
                    "confidence": round(e.confidence, 3),
                    "weight": round(e.weight, 2),
                    "notes": e.notes,
                }
                for e in self.estimates
            ],
        }


def estimate_implied_growth(
    price: Optional[float],
    fcf_ttm: Optional[float],
    shares_outstanding: Optional[float],
    wacc: float = 0.09,
    terminal_growth: float = 0.025,
) -> Optional[GrowthEstimate]:
    """Solve for implied growth that justifies current price.

    Uses a 2-stage DCF: 5 years of high growth + perpetual terminal.

    Args:
        price: Current stock price
        fcf_ttm: TTM free cash flow per share (or total FCF)
        shares_outstanding: Share count
        wacc: Cost of capital
        terminal_growth: Long-term growth rate

    Returns:
        GrowthEstimate or None if inputs insufficient
    """
    if not (price and fcf_ttm and shares_outstanding):
        return None

    if fcf_ttm <= 0 or price <= 0 or shares_outstanding <= 0:
        return None

    fcf_per_share = fcf_ttm / shares_outstanding
    if fcf_per_share <= 0:
        return None

    fcf_yield = fcf_per_share / price

    if fcf_yield <= 0:
        return None

    # Gordon Growth approximation: P = FCF / (r - g)  =>  g = r - FCF/P
    implied_g = wacc - fcf_yield

    # Constrain to plausible range
    implied_g = max(-0.05, min(0.30, implied_g))

    # Confidence based on FCF yield (very high or very low = less confident)
    fcf_yield_normalized = abs(fcf_yield - 0.05) / 0.05
    confidence = max(0.3, 1.0 - fcf_yield_normalized * 0.3)

    # Variance: higher when far from terminal growth or when FCF yield is extreme
    variance = max(0.0001, 0.0025 + (implied_g - terminal_growth) ** 2)

    return GrowthEstimate(
        method="implied",
        value=implied_g,
        confidence=confidence,
        variance=variance,
        notes=f"FCF yield: {fcf_yield:.2%}, WACC: {wacc:.2%}",
    )


def estimate_historical_growth(
    revenue_history: list[float],
    fcf_history: Optional[list[float]] = None,
    min_years: int = 3,
) -> Optional[GrowthEstimate]:
    """Compute smoothed historical CAGR with outlier removal.

    Uses log-CAGR to reduce sensitivity to endpoints. Drops top/bottom 10%
    of annual growth rates if 5+ years available.

    Args:
        revenue_history: Most-recent-first revenue values
        fcf_history: Most-recent-first FCF values (preferred if available)
        min_years: Minimum years of history required

    Returns:
        GrowthEstimate or None if insufficient history
    """
    series = fcf_history if fcf_history and len(fcf_history) >= min_years else revenue_history
    if not series or len(series) < min_years:
        return None

    # Clean: drop NaN and negative values (can't take log)
    clean = [x for x in series if x is not None and x > 0]
    if len(clean) < min_years:
        return None

    # Annual growth rates (year-over-year)
    growth_rates = []
    for i in range(len(clean) - 1):
        # Most recent first, so series[i+1] is older
        if clean[i + 1] > 0:
            g = clean[i] / clean[i + 1] - 1
            growth_rates.append(g)

    if not growth_rates:
        return None

    # Remove outliers if 5+ years
    if len(growth_rates) >= 5:
        sorted_g = sorted(growth_rates)
        # Drop top and bottom 10%
        trim = max(1, len(sorted_g) // 10)
        growth_rates = sorted_g[trim:-trim] if trim < len(sorted_g) // 2 else sorted_g

    median_growth = float(np.median(growth_rates))
    growth_std = float(np.std(growth_rates))

    # Confidence: higher with more years, lower with high volatility
    n_years = len(growth_rates)
    base_confidence = min(0.95, 0.5 + n_years * 0.05)
    vol_penalty = min(0.4, growth_std / 0.30)  # Penalize if std > 30%
    confidence = max(0.3, base_confidence - vol_penalty)

    # Variance from actual data
    variance = max(0.0001, growth_std**2 / n_years)

    return GrowthEstimate(
        method="historical",
        value=median_growth,
        confidence=confidence,
        variance=variance,
        notes=f"{n_years} years, std: {growth_std:.2%}",
    )


def estimate_sustainable_growth(
    roe: Optional[float],
    payout_ratio: Optional[float] = None,
    roic_history: Optional[list[float]] = None,
) -> Optional[GrowthEstimate]:
    """Compute sustainable growth from ROE and retention rate.

    Formula: g = ROE * (1 - payout_ratio)
    Critical for financials (BLK, GS, JPM) where ROE is the primary driver.

    Args:
        roe: Return on equity (e.g., 0.15 for 15%)
        payout_ratio: Dividend payout ratio (e.g., 0.40 for 40%)
        roic_history: Historical ROIC values for confidence assessment

    Returns:
        GrowthEstimate or None if ROE unavailable
    """
    if roe is None or roe <= 0:
        return None

    # Default retention if payout unknown (use 40% payout as base case)
    retention = 1.0 - (payout_ratio if payout_ratio is not None else 0.4)
    retention = max(0.0, min(1.0, retention))

    sustainable_g = roe * retention

    # Confidence: high if ROE is stable across history
    if roic_history and len(roic_history) >= 3:
        clean_roic = [r for r in roic_history if r is not None and r > 0]
        if clean_roic:
            roic_std = float(np.std(clean_roic))
            stability_score = max(0.0, 1.0 - roic_std / 0.10)  # 10% std = 0 confidence
            confidence = 0.4 + 0.5 * stability_score
        else:
            confidence = 0.5
    else:
        confidence = 0.5

    # Variance based on ROE stability
    if roic_history and len(roic_history) >= 3:
        clean_roic = [r for r in roic_history if r is not None and r > 0]
        if clean_roic:
            variance = max(0.0001, float(np.var(clean_roic)))
        else:
            variance = 0.01
    else:
        variance = 0.01

    return GrowthEstimate(
        method="sustainable",
        value=sustainable_g,
        confidence=confidence,
        variance=variance,
        notes=f"ROE: {roe:.2%}, retention: {retention:.2%}",
    )


def estimate_bottom_up_growth(
    revenue_growth_5y: Optional[float],
    operating_margin: Optional[float],
    operating_margin_5y_avg: Optional[float],
    reinvestment_rate: float = 0.5,
) -> Optional[GrowthEstimate]:
    """Bottom-up build: revenue growth x margin trajectory x reinvestment.

    Args:
        revenue_growth_5y: 5-year revenue CAGR
        operating_margin: Current operating margin
        operating_margin_5y_avg: 5-year average operating margin
        reinvestment_rate: Fraction of earnings reinvested

    Returns:
        GrowthEstimate or None if insufficient data
    """
    if revenue_growth_5y is None or operating_margin is None:
        return None

    # Margin expansion/compression factor
    if operating_margin_5y_avg and operating_margin_5y_avg > 0:
        margin_factor = operating_margin / operating_margin_5y_avg
        margin_factor = max(0.5, min(1.5, margin_factor))  # Cap at +/- 50%
    else:
        margin_factor = 1.0

    # Bottom-up growth = revenue growth * margin factor * reinvestment efficiency
    bottom_up_g = revenue_growth_5y * margin_factor * (1.0 + reinvestment_rate * 0.2)
    bottom_up_g = max(-0.10, min(0.40, bottom_up_g))

    confidence = 0.65 if operating_margin_5y_avg else 0.45
    variance = 0.005

    return GrowthEstimate(
        method="bottom_up",
        value=bottom_up_g,
        confidence=confidence,
        variance=variance,
        notes=f"Rev growth: {revenue_growth_5y:.2%}, margin factor: {margin_factor:.2f}",
    )


def estimate_sector_growth(
    sector: str,
    sector_growth_table: Optional[dict[str, float]] = None,
) -> GrowthEstimate:
    """Sector-median growth as prior baseline.

    Args:
        sector: Sector name (e.g., 'Technology', 'Financials')
        sector_growth_table: Optional override table

    Returns:
        GrowthEstimate (always returns; this is the prior)
    """
    default_table = {
        "Technology": 0.12,
        "Healthcare": 0.08,
        "Financials": 0.05,
        "Consumer": 0.05,
        "Consumer Discretionary": 0.06,
        "Consumer Staples": 0.04,
        "Industrials": 0.05,
        "Utilities": 0.03,
        "Energy": 0.04,
        "Materials": 0.04,
        "Real Estate": 0.04,
        "Communication Services": 0.07,
    }
    table = sector_growth_table or default_table
    sector_g = table.get(sector, 0.06)

    # Low confidence (prior only)
    return GrowthEstimate(
        method="sector",
        value=sector_g,
        confidence=0.4,
        variance=0.01,  # Wide variance — used as anchor
        notes=f"Sector: {sector}",
    )


def detect_margin_trajectory(
    operating_margin: Optional[float],
    operating_margin_history: list[float],
    threshold: float = 0.10,
) -> dict[str, float | str]:
    """Detect margin trajectory: compression, stable, or expansion.

    Returns an ADDITIVE adjustment to growth rate (in absolute percentage
    points), e.g., -0.03 means subtract 3pp from growth.

    Args:
        operating_margin: Current operating margin
        operating_margin_history: Most-recent-first history
        threshold: Significance threshold (10% = significant)

    Returns:
        Dict with trajectory, severity, adjustment (additive pp)
    """
    if not operating_margin or not operating_margin_history:
        return {
            "trajectory": "unknown",
            "severity": 0.0,
            "adjustment": 0.0,
            "notes": "Insufficient margin history",
        }

    clean = [m for m in operating_margin_history if m is not None and m != 0]
    if len(clean) < 2:
        return {
            "trajectory": "unknown",
            "severity": 0.0,
            "adjustment": 0.0,
            "notes": "Insufficient margin history",
        }

    # Use 5-year average (or all available) as baseline
    baseline = float(np.mean(clean[: min(5, len(clean))]))
    if baseline <= 0:
        return {
            "trajectory": "unknown",
            "severity": 0.0,
            "adjustment": 0.0,
            "notes": "Baseline margin non-positive",
        }

    # Severity: relative change vs baseline (-0.42 means 42% compression)
    severity = (operating_margin - baseline) / baseline

    if abs(severity) < threshold:
        trajectory = "stable"
        adjustment = 0.0
    elif severity < -threshold:
        trajectory = "compression"
        # Additive penalty in percentage points (BBY: -42% -> -0.05)
        # Scale: 10% compression -> -1pp, 50% compression -> -5pp (capped)
        adjustment = -min(0.08, abs(severity) * 0.12)
    else:
        trajectory = "expansion"
        # Additive bonus (capped at +2pp)
        adjustment = min(0.02, severity * 0.05)

    return {
        "trajectory": trajectory,
        "severity": severity,
        "adjustment": adjustment,
        "baseline": baseline,
        "notes": f"Current: {operating_margin:.2%}, 5y avg: {baseline:.2%}, change: {severity:+.1%}",
    }


def triangulate_growth(
    estimates: list[Optional[GrowthEstimate]],
    margin_adjustment: float = 0.0,
    prior_strength: float = 0.5,
) -> TriangulatedGrowth:
    """Blend multiple growth estimates using inverse-variance weighting.

    Args:
        estimates: List of GrowthEstimate (None values dropped)
        margin_adjustment: Adjustment from margin trajectory (-0.30 to +0.10)
        prior_strength: Bayesian shrinkage toward sector prior

    Returns:
        TriangulatedGrowth with blended estimate and full audit trail
    """
    valid = [e for e in estimates if e is not None]

    if not valid:
        return TriangulatedGrowth(
            blended_growth=0.06,
            confidence=0.2,
            estimates=[],
            method_disagreement=0.0,
            raw_growth=0.06,
            margin_adjustment=margin_adjustment,
        )

    # Inverse-variance weighted average
    total_weight = sum(e.weight for e in valid)

    if total_weight <= 0:
        # Fallback: simple confidence-weighted average
        total_conf = sum(e.confidence for e in valid)
        if total_conf <= 0:
            raw_g = float(np.mean([e.value for e in valid]))
        else:
            raw_g = sum(e.value * e.confidence for e in valid) / total_conf
    else:
        raw_g = sum(e.value * e.weight for e in valid) / total_weight

    # Method disagreement: std dev across estimators
    method_disagreement = float(np.std([e.value for e in valid])) if len(valid) > 1 else 0.0

    # Dominant method (highest weight)
    dominant = max(valid, key=lambda e: e.weight).method if valid else None

    # Apply margin adjustment ADDITIVELY (handles negative growth correctly)
    blended_g = raw_g + margin_adjustment
    blended_g = max(-0.10, min(0.40, blended_g))

    # Confidence: high when methods agree, low when they disagree
    avg_confidence = float(np.mean([e.confidence for e in valid]))
    # Softer disagreement penalty: 5pp std -> 0.15 penalty, 15pp -> 0.45
    disagreement_penalty = min(0.45, method_disagreement * 3.0)
    confidence = max(0.2, avg_confidence - disagreement_penalty)

    return TriangulatedGrowth(
        blended_growth=blended_g,
        raw_growth=raw_g,
        margin_adjustment=margin_adjustment,
        confidence=confidence,
        estimates=valid,
        method_disagreement=method_disagreement,
        dominant_method=dominant,
    )
