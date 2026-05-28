#!/usr/bin/env python3
"""Interactive CLI for the multi-lens valuation engine.

Gathers all results from the lenses + pipeline silently, then renders
them through the typographic institutional UI in one clean pass.

Run from the repo root:
    python run.py
"""

from __future__ import annotations

import sys
from typing import Any, Optional

from iam.validation import parse_growth_rate


def _classify_signal(upside: Optional[float], threshold: float = 0.05) -> str:
    """Map a fractional upside to BULLISH / NEUTRAL / BEARISH."""
    if upside is None:
        return "N/A"
    if upside > threshold:
        return f"BULLISH ({upside * 100:+.1f}%)"
    if upside < -threshold:
        return f"BEARISH ({upside * 100:+.1f}%)"
    return f"NEUTRAL ({upside * 100:+.1f}%)"


def _build_scenarios(intrinsic_components: dict) -> list[dict]:
    """Extract the probabilistic scenario matrix from the intrinsic DCF result."""
    raw = intrinsic_components.get("scenarios", {}) or {}
    formatted: list[dict] = []
    for name, data in raw.items():
        formatted.append(
            {
                "name": name,
                "prob": f"{data['prob'] * 100:.0f}%",
                "target": data["target"],
                "upside": f"{data['upside'] * 100:+.1f}%",
                "thesis": _scenario_thesis(name),
            }
        )
    return formatted


def _scenario_thesis(name: str) -> str:
    """Short label per scenario (mirrors fcfe_dcf scenario definitions)."""
    name_lower = name.lower()
    if "bear" in name_lower:
        return "Stressed execution"
    if "bull" in name_lower:
        return "Platform leverage"
    return "Anchor assumptions"


def _gather_lens_results(security) -> tuple[Optional[float], Optional[str]]:
    """Run the multi-lens engine silently. Returns (synthesis_upside, error)."""
    try:
        from iam.lenses.rate_sensitive import RateSensitiveLens
        from iam.lenses.platform_compounder import PlatformCompounderLens
        from iam.lenses.expectations_difficulty import ExpectationsDifficultyLens
        from iam.lenses.damodaran_base import DamodaranBaseLens
        from iam.lenses.synthesis import synthesize_lenses

        lens_results = [
            RateSensitiveLens().compute(security),
            PlatformCompounderLens().compute(security),
            ExpectationsDifficultyLens().compute(security),
            DamodaranBaseLens().compute(security),
        ]
        synthesis = synthesize_lenses(lens_results)
        return synthesis.weighted_implied_move_pct, None
    except Exception as exc:
        return None, str(exc)


def _gather_pipeline_report(security, synthesis_upside: Optional[float]):
    """Run the 7-stage pipeline silently. Returns (report, error)."""
    try:
        from iam.pipeline.orchestrator import ValuationPipeline

        report = ValuationPipeline().run(security, synthesis_upside=synthesis_upside)
        return report, None
    except Exception as exc:
        return None, str(exc)


def _build_ui_data(
    security,
    growth: float,
    synthesis_upside: Optional[float],
    report,
) -> dict[str, Any]:
    """Assemble the dict consumed by print_institutional_ui()."""
    # PWEV + scenarios come from intrinsic DCF components
    intrinsic_components = report.intrinsic.components if report else {}
    intrinsic_assumptions = report.intrinsic.assumptions if report else {}

    pwev = float(intrinsic_components.get("pwev_target", 0.0) or 0.0)
    wacc_value = intrinsic_assumptions.get("discount_rate")
    terminal_value = intrinsic_assumptions.get("terminal_growth")

    # Verdict + confidence
    verdict_text = "—"
    confidence_band = "MODERATE"
    if report and report.final_verdict:
        verdict_text = report.final_verdict.rating
        confidence_band = report.final_verdict.confidence_band

    # Macro overlay status (text-mined from report.summary)
    summary_lower = (report.summary or "").lower() if report else ""
    if "macro trigger" in summary_lower or "rate shock" in summary_lower:
        macro_signal = "TRIGGERED"
    elif "macro check" in summary_lower:
        macro_signal = "PASS"
    else:
        macro_signal = "PASS"

    wacc_info = security.qualitative.get("wacc_info") if security.qualitative else None

    return {
        "ticker": security.ticker,
        "name": security.name or security.ticker,
        "price": security.market.price or 0.0,
        "verdict": verdict_text,
        "growth": f"{growth * 100:.1f}%",
        "wacc": f"{wacc_value * 100:.2f}%" if wacc_value else "—",
        "terminal": f"{terminal_value * 100:.1f}%" if terminal_value else "2.5%",
        "pwev": pwev,
        "synthesis": (
            f"{synthesis_upside * 100:+.1f}%" if synthesis_upside is not None else None
        ),
        "confidence": confidence_band,
        "scenarios": _build_scenarios(intrinsic_components),
        "wacc_info": wacc_info,
        "signals": {
            "reverse_dcf": _classify_signal(report.reverse_dcf.fair_value_to_price)
            if report
            else "N/A",
            "platform_compounder": _classify_signal(synthesis_upside),
            "relative_valuation": _classify_signal(report.relative.fair_value_to_price)
            if report
            else "N/A",
            "macro_overlay": macro_signal,
        },
    }


def main() -> None:
    from iam.ui.institutional_terminal import print_institutional_ui

    # ----- Input -----
    ticker = input("Ticker symbol: ").strip().upper()
    if not ticker:
        print("No ticker entered. Exiting.")
        sys.exit(0)

    g_input = input(
        "Forecast growth (e.g. 13 or 0.13 for 13%) [Enter for default 8%]: "
    ).strip()

    # ----- Silent data fetch -----
    try:
        from iam.data.yahoo import fetch_security

        security = fetch_security(ticker)
    except (ImportError, RuntimeError) as exc:
        print(f"\nERROR: {exc}")
        sys.exit(1)
    except Exception as exc:
        print(f"\nUnexpected error: {exc}")
        sys.exit(1)

    # Apply optional growth override
    growth = 0.08
    if g_input:
        try:
            growth = parse_growth_rate(g_input, default=0.08)
            if security.qualitative is None:
                security.qualitative = {}
            security.qualitative["forecast_growth"] = growth
        except ValueError as exc:
            print(f"Invalid growth input: {exc} — using default 8%.")

    # ----- Silent engine runs -----
    synthesis_upside, lens_error = _gather_lens_results(security)
    report, pipeline_error = _gather_pipeline_report(security, synthesis_upside)

    if report is None:
        # The pipeline is mandatory; if it failed, show why and stop.
        print(f"\nPipeline error: {pipeline_error}")
        sys.exit(1)

    if lens_error:
        # Lens failure is non-fatal; just note it before rendering.
        print(f"(Lens analysis unavailable: {lens_error})")

    # ----- Single unified render -----
    ui_data = _build_ui_data(security, growth, synthesis_upside, report)
    print_institutional_ui(ui_data)


if __name__ == "__main__":
    main()
