#!/usr/bin/env python3
"""Validation script: run growth triangulation on synthetic profiles.

Demonstrates that the triangulation model produces sensible growth estimates
for nine reference companies plus BBY (margin compression case).

Usage:
    python scripts/validate_growth_model.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add src/ to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from iam.data.security import Fundamentals, MarketData, Security
from iam.valuation.adaptive import AdaptiveValuationEngine
from iam.valuation.probabilistic_growth import build_engine_from_security
from iam.valuation.profile_builder import (
    build_company_profile,
    triangulate_growth_for_security,
)


def make_security(
    ticker,
    name,
    sector,
    price,
    shares,
    op_margin,
    op_history,
    revenue_ttm,
    revenue_history,
    fcf_ttm,
    fcf_history,
    roic_history,
):
    """Build a Security object from raw inputs."""
    return Security(
        ticker=ticker,
        name=name,
        sector=sector,
        fundamentals=Fundamentals(
            revenue_ttm=revenue_ttm,
            revenue_history=revenue_history,
            operating_margin=op_margin,
            operating_margin_history=op_history,
            fcf_ttm=fcf_ttm,
            fcf_history=fcf_history,
            roic_history=roic_history,
            shares_outstanding=shares,
            incremental_roic=roic_history[0] if roic_history else 0.10,
        ),
        market=MarketData(price=price),
    )


def get_test_basket():
    """Return curated synthetic test cases."""
    return [
        # KO: stable, low volatility
        make_security(
            "KO",
            "Coca-Cola",
            "Consumer Staples",
            60.0,
            4.3e9,
            op_margin=0.226,
            op_history=[0.226, 0.225, 0.220, 0.218, 0.215],
            revenue_ttm=45e9,
            revenue_history=[45e9, 44e9, 43e9, 38e9, 37e9, 35e9],
            fcf_ttm=10e9,
            fcf_history=[10e9, 9.5e9, 9.8e9, 9.2e9, 8.9e9, 8.5e9],
            roic_history=[0.15, 0.14, 0.13, 0.14, 0.13],
        ),
        # GOOGL: moat-tech, sustainable high growth
        make_security(
            "GOOGL",
            "Alphabet",
            "Technology",
            140.0,
            12.5e9,
            op_margin=0.286,
            op_history=[0.286, 0.27, 0.30, 0.28, 0.26],
            revenue_ttm=300e9,
            revenue_history=[300e9, 280e9, 257e9, 182e9, 161e9, 136e9],
            fcf_ttm=70e9,
            fcf_history=[70e9, 60e9, 65e9, 55e9, 50e9, 40e9],
            roic_history=[0.20, 0.22, 0.25, 0.20, 0.18],
        ),
        # META: moat-tech, high quality
        make_security(
            "META",
            "Meta Platforms",
            "Technology",
            350.0,
            2.5e9,
            op_margin=0.38,
            op_history=[0.38, 0.30, 0.40, 0.35, 0.30],
            revenue_ttm=130e9,
            revenue_history=[130e9, 117e9, 116e9, 86e9, 71e9, 56e9],
            fcf_ttm=40e9,
            fcf_history=[40e9, 30e9, 50e9, 25e9, 20e9, 15e9],
            roic_history=[0.25, 0.20, 0.30, 0.25, 0.22],
        ),
        # BLK: financial, ROE-based
        make_security(
            "BLK",
            "BlackRock",
            "Financials",
            750.0,
            150e6,
            op_margin=0.40,
            op_history=[0.40, 0.38, 0.42, 0.40, 0.38],
            revenue_ttm=18e9,
            revenue_history=[18e9, 17e9, 19e9, 18e9, 16e9, 14e9],
            fcf_ttm=5e9,
            fcf_history=[5e9, 4.8e9, 5.2e9, 4.5e9, 4e9],
            roic_history=[0.12, 0.11, 0.13, 0.12, 0.11],
        ),
        # AMD: cyclical, high volatility
        make_security(
            "AMD",
            "Advanced Micro Devices",
            "Technology",
            120.0,
            1.6e9,
            op_margin=0.05,
            op_history=[0.05, 0.15, 0.20, 0.10, -0.05, 0.02],
            revenue_ttm=25e9,
            revenue_history=[25e9, 20e9, 25e9, 16e9, 10e9, 7e9, 6e9],
            fcf_ttm=1e9,
            fcf_history=[1e9, 3e9, 4e9, 2e9, -0.5e9, 0.3e9, 0.1e9],
            roic_history=[0.15, 0.20, 0.18, 0.10, -0.05, 0.05],
        ),
        # BBY: margin compression case
        make_security(
            "BBY",
            "Best Buy",
            "Consumer Discretionary",
            75.0,
            215e6,
            op_margin=0.015,  # Current 1.5%
            op_history=[0.026, 0.028, 0.030, 0.029, 0.027],  # was ~2.6% avg
            revenue_ttm=42e9,
            revenue_history=[42e9, 41e9, 47e9, 51e9, 47e9, 44e9],
            fcf_ttm=1.2e9,
            fcf_history=[1.2e9, 1.4e9, 2.0e9, 2.5e9, 2.1e9, 1.8e9],
            roic_history=[0.06, 0.10, 0.15, 0.12, 0.10],
        ),
    ]


def print_header(label, width=86):
    print()
    print("=" * width)
    print(f"  {label}")
    print("=" * width)


def validate_security(security):
    """Run full validation on one security."""
    print(f"\n  {'-' * 84}")
    print(f"  {security.name} ({security.ticker}) - {security.sector}")
    print(f"  Current Price: ${security.market.price:.2f}")
    print(f"  {'-' * 84}")

    # Triangulation
    tri = triangulate_growth_for_security(security)
    print(f"\n  GROWTH TRIANGULATION")
    print(f"  Blended Growth:    {tri.blended_growth:>+7.2%}")
    print(f"  Raw Growth:        {tri.raw_growth:>+7.2%}")
    print(f"  Margin Adjustment: {tri.margin_adjustment:>+7.3%}")
    print(f"  Confidence:        {tri.confidence:>7.1%}")
    print(f"  Disagreement σ:    {tri.method_disagreement:>7.2%}")
    print(f"  Dominant Method:   {tri.dominant_method}")

    print(f"\n  ESTIMATOR BREAKDOWN")
    print(f"  {'Method':<14} {'Growth':>8} {'Conf':>6} {'Weight':>8} Notes")
    for e in tri.estimates:
        print(f"  {e.method:<14} {e.value:>+8.2%} {e.confidence:>6.2f} {e.weight:>8.1f}  {e.notes}")

    # Adaptive engine
    profile = build_company_profile(security)
    engine = AdaptiveValuationEngine()
    result = engine.run(profile)

    print(f"\n  ADAPTIVE ENGINE")
    print(f"  Business Type:    {result['type']}")
    print(f"  Confidence Grade: {result['confidence']}")
    print(f"  Volatility:       {profile.hist_volatility:>7.2%}")
    print(f"  Year 1 Growth:    {result['fade_path'][0]:>+7.2%}")
    print(f"  Year 10 Growth:   {result['fade_path'][-1]:>+7.2%}")

    # Verdict
    rating = (
        "BUY" if result["confidence"] == "A" else "HOLD" if result["confidence"] == "B" else "SELL"
    )
    print(f"\n  → {rating}")

    # Probabilistic engine comparison
    prob_eng = build_engine_from_security(security, moat_durability=0.7)
    prob_result = prob_eng.blended_growth()
    print(f"\n  PROBABILISTIC ENGINE (brentq + regime-aware)")
    print(f"  Mean Growth:      {prob_result.mean_growth:>+7.2%}")
    print(f"  Std Dev:          {prob_result.std_dev:>7.2%}")
    print(f"  Growth Haircut:   {prob_result.growth_haircut:>7.2%}x")
    print(f"  Terminal Haircut: {prob_result.terminal_haircut:>7.2%}x")
    print(f"  Fade: {' → '.join(f'{g:+.1%}' for g in prob_result.fade_path[::3])}")


def main():
    print_header("GROWTH TRIANGULATION MODEL VALIDATION")
    print("\n  Running 6 synthetic test cases through the triangulation engine.")
    print("  Each case demonstrates a different valuation scenario:")
    print("    KO    - Stable, low volatility (Consumer Staples)")
    print("    GOOGL - High-quality tech (moat)")
    print("    META  - High-quality tech (moat)")
    print("    BLK   - Financial (ROE-based growth)")
    print("    AMD   - Cyclical, high volatility")
    print("    BBY   - Margin compression case (-46%)")

    for security in get_test_basket():
        validate_security(security)

    print()
    print("=" * 86)
    print("  VALIDATION COMPLETE")
    print("=" * 86)
    print()


if __name__ == "__main__":
    main()
