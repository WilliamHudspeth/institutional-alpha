#!/usr/bin/env python3
"""Example: Integrating Institutional Terminal UI with Pipeline Output

Shows how to:
1. Run the valuation pipeline
2. Extract key metrics
3. Display results using the institutional ASCII UI
"""

from iam.data.security import Fundamentals, MarketData, Security
from iam.pipeline.orchestrator import ValuationPipeline
from iam.ui import print_institutional_ui, print_pipeline_summary


def format_ui_data_from_pipeline(ticker: str, report) -> dict:
    """Convert PipelineReport into UI data dictionary.

    Args:
        ticker: Stock symbol
        report: PipelineReport from ValuationPipeline.run()

    Returns:
        Dictionary formatted for print_institutional_ui()
    """
    # Extract scenario data from intrinsic DCF components
    scenarios = []
    scenario_data = report.intrinsic.components.get("scenarios", {})

    for scenario_name, scenario_info in scenario_data.items():
        scenarios.append({
            "name": scenario_name.replace(" Case", ""),
            "prob": f"{scenario_info['prob']*100:.0f}%",
            "target": scenario_info["target"],
            "upside": f"{scenario_info['upside']*100:+.0f}%",
            "thesis": scenario_name,
        })

    # Extract signals
    signals = {
        "reverse_dcf": f"{report.reverse_dcf.verdict_text.split('(')[0].strip()}",
        "relative": report.relative.verdict_text.split("(")[0].strip(),
        "intrinsic": f"PWEV ${report.intrinsic.fair_value_per_share:.0f}",
        "triangulation": report.triangulation.verdict.upper(),
    }

    # Build UI data dictionary
    ui_data = {
        "ticker": ticker,
        "name": "Company Name",  # Would come from security.name
        "price": report.triangulation.cluster_center,  # Use triangulation as reference
        "verdict": report.final_verdict.rating if report.final_verdict else "HOLD",
        "growth": f"{report.intrinsic.assumptions.get('high_growth', 0.08)*100:.0f}%",
        "wacc": f"{report.intrinsic.assumptions.get('discount_rate', 0.09)*100:.2f}%",
        "terminal": f"{report.intrinsic.assumptions.get('terminal_growth', 0.025)*100:.1f}%",
        "pwev": report.intrinsic.fair_value_per_share,
        "synthesis": report.synthesis_upside or "N/A",
        "confidence": report.final_verdict.confidence_band if report.final_verdict else "N/A",
        "scenarios": scenarios,
        "signals": signals,
    }

    return ui_data


# Example usage with mock data
if __name__ == "__main__":
    # Create test security
    test_security = Security(
        ticker="TEST",
        name="Test Company",
        sector="Technology",
        fundamentals=Fundamentals(
            net_income_ttm=1000.0,
            fcf_ttm=900.0,
            shares_outstanding=100.0,
            revenue_ttm=5000.0,
            total_debt=1000.0,
            ebitda_ttm=1500.0,
        ),
        market=MarketData(
            price=100.0,
            market_cap=10000.0,
        ),
        qualitative={
            "forecast_growth": 0.12,
            "forecast_terminal_growth": 0.025,
            "forecast_discount_rate": 0.09,
        }
    )

    # Run pipeline
    print("Running valuation pipeline...")
    pipeline = ValuationPipeline()
    report = pipeline.run(test_security)

    # Convert to UI format
    ui_data = format_ui_data_from_pipeline("TEST", report)

    # Display
    print("\nRendering institutional UI...\n")
    print_institutional_ui(ui_data)

    # Also show quick summary
    print_pipeline_summary(
        "TEST",
        report.intrinsic.fair_value_per_share,
        report.intrinsic.fair_value_per_share,
        report.final_verdict.rating if report.final_verdict else "HOLD",
        report.final_verdict.confidence_band if report.final_verdict else "N/A"
    )

    print("\n" + "="*60)
    print("✓ Complete pipeline output with institutional UI")
    print("="*60 + "\n")
