"""Run the valuation pipeline on live data using yfinance."""

from iam.data.providers.yfinance_adapter import YFinanceAdapter
from iam.pipeline.orchestrator import ValuationPipeline


def main():
    adapter = YFinanceAdapter()
    print("Fetching AAPL data...")
    aapl_security = adapter.fetch("AAPL")

    aapl_security.qualitative = {
        "forecast_growth": 0.08,
        "forecast_discount_rate": 0.09,
        "forecast_terminal_growth": 0.025,
    }

    report = ValuationPipeline().run(aapl_security)
    print("\n" + report.explain())


if __name__ == "__main__":
    main()
