from iam.data.providers.yfinance_adapter import fetch_security
from iam.valuation.damodaran_defaults import DamodaranUniverse
from iam.valuation.relative import RelativeValuation


def main():
    print("Fetching live data for AAPL...")
    security = fetch_security("AAPL")

    # 1. Initialize the Damodaran Universe with Tech Multiples
    # (In a real app, this data would be loaded from a CSV/DB)
    universe = DamodaranUniverse(
        us_erp=0.0503,
        region_erps={"Americas": 0.0503},
        sector_beta_u={"Technology": 1.15, "Consumer Electronics": 1.15},
        sector_multiples={
            "Consumer Electronics": {"ev_ebitda": 18.5, "pe": 24.0},
            "Technology": {"ev_ebitda": 20.0, "pe": 28.0}
        }
    )

    print(f"\nAnalyzing Sector: {security.sector}")

    # 2. Run the Relative Valuation Engine
    engine = RelativeValuation(universe)
    result = engine.compute(security)

    print("\n=== STAGE 2: RELATIVE VALUATION ===")

    ev_ebitda = result.components.get("implied_price_ev_ebitda")
    pe = result.components.get("implied_price_pe")

    print(f"Implied Price (EV/EBITDA): {ev_ebitda:.2f}" if ev_ebitda else "Implied Price (EV/EBITDA): N/A")
    print(f"Implied Price (P/E):       {pe:.2f}" if pe else "Implied Price (P/E): N/A")
    print("-" * 35)
    print(f"Verdict: {result.verdict_text}")

if __name__ == '__main__':
    main()
