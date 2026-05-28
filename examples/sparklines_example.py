#!/usr/bin/env python3
"""ANSI sparklines and inline data visualization.

Demonstrates:
- Line sparklines for price movement
- Volatility visualization
- Progress bars and ranges
- Intraday OHLC visualization
- Trend indicators
- Heatmap colors
"""

from iam.ui.sparklines import (
    HeatmapColor,
    MiniChart,
    ProgressBar,
    Sparkline,
    format_price_movement,
    format_volatility_context,
)


def main() -> None:
    """Run sparklines example."""

    print("\n" + "=" * 80)
    print("ANSI SPARKLINES AND DATA VISUALIZATION")
    print("=" * 80 + "\n")

    # 1. Line sparklines
    print("1. PRICE MOVEMENT SPARKLINES")
    print("-" * 80)

    securities = {
        "MSFT": [350, 352, 351, 355, 353, 358, 360, 357, 361, 365, 368, 367, 370, 375, 378],
        "AAPL": [140, 138, 135, 137, 136, 140, 142, 139, 138, 135, 133, 130, 128, 125, 122],
        "JPM": [160, 161, 162, 160, 159, 161, 163, 162, 161, 162, 164, 163, 162, 161, 160],
    }

    for ticker, prices in securities.items():
        current = prices[-1]
        previous = prices[0]
        change = current - previous
        change_pct = (change / previous * 100)
        trend = Sparkline.trend(prices)

        sparkline = Sparkline.line(prices, width=30)
        print(f"{ticker:<6} {sparkline} {trend} {current:>7.2f} ({change:+6.2f}, {change_pct:+5.1f}%)")

    print("")

    # 2. Intraday OHLC
    print("\n2. INTRADAY OHLC VISUALIZATION")
    print("-" * 80)

    intraday_data = {
        "MSFT": {"open": 370, "high": 378, "low": 368, "close": 375},
        "AAPL": {"open": 122, "high": 125, "low": 120, "close": 121},
        "GOOG": {"open": 140, "high": 143, "low": 138, "close": 141},
    }

    print(f"{'Ticker':<8} {'Open':<8} {'High':<8} {'Low':<8} {'Close':<8} {'Chart':<10} {'Status':<15}")
    print("-" * 80)

    for ticker, data in intraday_data.items():
        o = data["open"]
        h = data["high"]
        l = data["low"]
        c = data["close"]

        chart = MiniChart.intraday(o, h, l, c)
        status = "↑ Up" if c > o else "↓ Down" if c < o else "→ Flat"

        print(f"{ticker:<8} {o:<8.2f} {h:<8.2f} {l:<8.2f} {c:<8.2f} {chart:<10} {status:<15}")

    print("")

    # 3. Volatility visualization
    print("\n3. VOLATILITY SPARKLINES")
    print("-" * 80)

    return_series = {
        "MSFT": [0.01, 0.02, -0.01, 0.03, 0.02, 0.04, -0.01, 0.03, 0.02, 0.01, -0.02, 0.03],
        "AAPL": [0.02, -0.03, 0.01, -0.02, 0.04, -0.03, 0.02, -0.04, 0.03, -0.02, 0.01, -0.03],
        "JPM": [0.005, 0.01, 0.002, 0.015, -0.005, 0.012, 0.008, 0.01, 0.005, 0.002, 0.008, 0.01],
    }

    vol_data = {
        "MSFT": 0.022,
        "AAPL": 0.028,
        "JPM": 0.009,
    }

    historical_avg_vol = 0.015

    for ticker, returns in return_series.items():
        current_vol = vol_data[ticker]
        sparkline = Sparkline.volatility_bars(returns, width=20)
        ratio = current_vol / historical_avg_vol

        if ratio > 1.5:
            indicator = "🔴"
            level = "HIGH"
        elif ratio > 1.1:
            indicator = "🟡"
            level = "ELEVATED"
        else:
            indicator = "🟢"
            level = "NORMAL"

        print(f"{ticker:<8} {indicator} {level:<10} {sparkline}  {current_vol:.2%} ({ratio:.1f}x avg)")

    print("")

    # 4. Progress bars and ranges
    print("\n4. PROGRESS BARS & RANGE INDICATORS")
    print("-" * 80)

    # Portfolio allocation
    allocations = {
        "Equities": 0.70,
        "Bonds": 0.20,
        "Cash": 0.10,
    }

    print("Portfolio Allocation:")
    for asset_class, pct in allocations.items():
        bar = ProgressBar.bar_with_label(pct, 1.0, width=25, label_pct=True)
        print(f"  {asset_class:<15} {bar}")

    print("")

    # Valuation range
    print("Valuation vs Target Range:")
    valuations = {
        "MSFT": {"current": 375, "low": 300, "high": 450},
        "AAPL": {"current": 121, "low": 120, "high": 180},
        "JPM": {"current": 160, "low": 150, "high": 200},
    }

    for ticker, data in valuations.items():
        range_bar = MiniChart.range_bar(data["current"], data["low"], data["high"], width=20)
        print(f"  {ticker:<8} ${data['current']:>6.2f}  {range_bar}")

    print("")

    # 5. Price movement summary
    print("\n5. PRICE MOVEMENT WITH CONTEXT")
    print("-" * 80)

    movements = {
        "MSFT": {"current": 375, "previous": 370, "high": 378, "low": 368},
        "AAPL": {"current": 121, "previous": 122, "high": 125, "low": 120},
        "JPM": {"current": 160, "previous": 160, "high": 164, "low": 156},
    }

    for ticker, data in movements.items():
        movement = format_price_movement(
            data["current"], data["previous"], data["high"], data["low"], width=20
        )
        print(f"{ticker:<8} {movement}")

    print("")

    # 6. Volatility context
    print("\n6. VOLATILITY CONTEXT WITH HISTORICAL COMPARISON")
    print("-" * 80)

    for ticker, returns in return_series.items():
        current_vol = vol_data[ticker]
        context = format_volatility_context(returns, current_vol, historical_avg_vol)
        print(f"{ticker:<8} {context}")

    print("")

    # 7. Heatmap colors
    print("\n7. HEAT MAP COLOR INDICATORS")
    print("-" * 80)

    metrics = {
        "Return (YTD)": 0.15,
        "Sharpe Ratio": 0.72,
        "Volatility": 0.28,
        "Correlation": 0.45,
        "Drawdown": 0.05,
    }

    print("Metric Heatmap (red=low, yellow=medium, green=high):")
    for metric_name, value in metrics.items():
        indicator = HeatmapColor.indicator(value)
        ascii_ind = HeatmapColor.ascii_indicator(value)
        print(f"  {metric_name:<20} {indicator} {ascii_ind} {value:>6.2%}")

    print("")

    # 8. Trend comparison
    print("\n8. TREND INDICATORS")
    print("-" * 80)

    trends = {
        "Strong Uptrend": [100, 102, 105, 108, 112, 115, 118, 122],
        "Flat": [100, 100.5, 99.8, 100.2, 100.1, 99.9, 100.3, 100.2],
        "Strong Downtrend": [100, 98, 95, 92, 88, 85, 82, 78],
        "Volatile": [100, 105, 95, 108, 90, 112, 88, 115],
    }

    for trend_name, prices in trends.items():
        sparkline = Sparkline.line(prices, width=25)
        trend = Sparkline.trend(prices)
        print(f"{trend_name:<20} {sparkline} {trend}")

    print("")

    print("=" * 80)
    print("ANSI sparklines enable:")
    print("  ✓ Inline price movement visualization")
    print("  ✓ Volatility trending")
    print("  ✓ Range/target positioning")
    print("  ✓ Intraday OHLC in 1 character")
    print("  ✓ Progress and allocation tracking")
    print("  ✓ Trend direction (↑ ↓ →)")
    print("  ✓ Heatmap colors for metrics")
    print("  ✓ No external dependencies (Unicode only)")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
