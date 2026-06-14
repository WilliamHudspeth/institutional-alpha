from iam.data.macro import MacroConditions
from iam.data.providers.yfinance_adapter import fetch_security
from iam.pipeline.orchestrator import ValuationPipeline


def main():
    print("Fetching live data for AAPL...")
    security = fetch_security("AAPL")

    # Set up a massive 75 bps rate shock
    macro_shock = MacroConditions(rate_shock_bps=75.0)

    print("\nRunning pipeline through the Macro Overlay...")
    report = ValuationPipeline().run(security, macro=macro_shock)

    print("\n=== PIPELINE RESULTS ===")
    print(report.summary)

if __name__ == '__main__':
    main()
