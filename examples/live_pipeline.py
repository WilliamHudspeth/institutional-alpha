"""Run the valuation pipeline on live data using yfinance."""

from iam.pipeline.orchestrator import ValuationPipeline
from iam.data.providers.yfinance_adapter import YFinanceAdapter

def main():
    # 1. Fetch live data
    adapter = YFinanceAdapter()
    print("Fetching AAPL data...")
    aapl_security = adapter.fetch("AAPL")
    
    # 2. Inject your thesis (qualitative data)
    # Let's assume you think Apple can grow FCFE at 8% for the next decade
    aapl_security.qualitative = {
        "forecast_growth": 0.08,
        "forecast_discount_rate": 0.09,
        "forecast_terminal_growth": 0.025
    }
    
    # 3. Run the pipeline
    report = ValuationPipeline().run(aapl_security)
    print("\n" + report.explain())

if __name__ == "__main__":
    main()
