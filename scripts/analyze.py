#!/usr/bin/env python3
"""Simple CLI entry point for the IAM framework."""

import argparse
import json
import re
import urllib.parse
import urllib.request

from iam.data.yahoo import fetch_security
from iam.pipeline import ValuationPipeline


def resolve_ticker(query: str) -> tuple[str, str | None]:
    """Attempts to resolve a company name to a ticker using Yahoo Finance search."""
    try:
        safe_query = urllib.parse.quote(query)
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={safe_query}&quotesCount=1&newsCount=0"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
            quotes = data.get("quotes", [])
            if quotes and "symbol" in quotes[0]:
                return quotes[0]["symbol"].upper(), quotes[0].get(
                    "shortname", quotes[0].get("longname")
                )
    except Exception:
        pass
    return query.strip().upper(), None


def analyze_ticker(query: str) -> str:
    """Validates the ticker, calculates a basic recommendation, and returns the full report."""
    query = query.strip()

    # 1. Resolve potential company names to tickers using Yahoo Search
    ticker, resolved_name = resolve_ticker(query)

    # 2. Structural Validation: Ensure the resolved ticker only contains valid characters
    if not re.match(r"^[A-Z0-9\-\.]{1,15}$", ticker):
        return f"[INVALID INPUT] '{query}' could not be resolved to a valid ticker. Tickers should only be alphanumeric, dots, or dashes."

    # 3. Network Validation: Use Yahoo Finance to invalidate missing or delisted tickers
    try:
        sec = fetch_security(ticker)
    except RuntimeError as e:
        return f"[INVALID TICKER] Could not fetch data for '{ticker}'. It may be delisted or misspelled.\nDetails: {e}"
    except ImportError:
        return "[ERROR] yfinance is not installed. Please run `pip install yfinance`."

    current_price = sec.market.price
    if current_price is None:
        return f"[INVALID TICKER] '{ticker}' returned no current price data from Yahoo Finance."

    # 4. Run the advanced valuation pipeline with error handling
    try:
        pipeline = ValuationPipeline()
        report = pipeline.run(sec)
    except Exception as e:
        return f"[PIPELINE ERROR] The valuation pipeline failed for '{ticker}'.\nDetails: {e}"

    # 5. Determine Basic Recommendation
    target_price = None

    # Target price prioritizes the triangulation cluster center; falls back to intrinsic DCF
    if report.triangulation.cluster_center is not None:
        target_price = current_price * (1 + report.triangulation.cluster_center)
    elif report.intrinsic and report.intrinsic.fair_value_per_share is not None:
        target_price = report.intrinsic.fair_value_per_share

    if target_price is not None and current_price > 0:
        upside = (target_price / current_price) - 1

        # Basic threshold logic for Buy/Sell
        if upside > 0.15:
            recommendation = "BUY"
        elif upside < -0.15:
            recommendation = "SELL"
        else:
            recommendation = "HOLD"

        target_str = f"${target_price:.2f}"
        upside_str = f"{upside:+.1%}"
    else:
        recommendation = "INCONCLUSIVE"
        target_str = "N/A"
        upside_str = "N/A"

    # 6. Construct Output
    lines = [
        "=" * 50,
        f" BASIC RECOMMENDATION: {ticker}",
    ]
    if resolved_name and ticker != query.upper():
        lines.append(f" (Resolved from '{query}': {resolved_name})")
    lines.extend(
        [
            "=" * 50,
            f" Current Price  : ${current_price:.2f}",
            f" Target Price   : {target_str} ({upside_str})",
            f" Recommendation : {recommendation}",
            "",
            "=" * 50,
            f" ADVANCED PIPELINE REPORT: {ticker}",
            "=" * 50,
            report.explain(),
        ]
    )

    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Analyze a stock ticker or company name using IAM."
    )
    parser.add_argument(
        "ticker", type=str, help="The stock ticker symbol or company name (e.g., AAPL, Apple)"
    )
    args = parser.parse_args()

    result = analyze_ticker(args.ticker)
    print(result)
