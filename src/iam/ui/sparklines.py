"""ANSI sparklines and inline data visualization.

Creates Unicode charts without external dependencies:
- Line sparklines: ▁▂▃▄▅▆▇█
- Trend indicators: ↑ ↓ →
- Progress bars: █░
- Mini bars: ▌▐
- Heatmaps: 🟢🟡🔴
"""

from __future__ import annotations


class Sparkline:
    """Simple sparkline renderer using Unicode characters."""

    # Sparkline levels (low to high)
    LEVELS = ("▁", "▂", "▃", "▄", "▅", "▆", "▇", "█")

    @staticmethod
    def line(values: list[float], width: int = 20) -> str:
        """Create a line sparkline from values.

        Args:
            values: List of numeric values
            width: Maximum width in characters

        Returns:
            Sparkline string
        """
        if not values or len(values) == 0:
            return "—"

        # Normalize values to 0-1
        min_val = min(values)
        max_val = max(values)

        if min_val == max_val:
            # All same value
            return "▄" * min(width, len(values))

        normalized = [(v - min_val) / (max_val - min_val) for v in values]

        # Sample to width if needed
        if len(normalized) > width:
            step = len(normalized) / width
            sampled = [normalized[int(i * step)] for i in range(width)]
        else:
            sampled = normalized

        # Map to levels
        sparkline = ""
        for val in sampled:
            level_idx = min(int(val * (len(Sparkline.LEVELS) - 1)), len(Sparkline.LEVELS) - 1)
            sparkline += Sparkline.LEVELS[level_idx]

        return sparkline

    @staticmethod
    def trend(values: list[float], window: int = 5) -> str:
        """Determine trend direction.

        Args:
            values: List of numeric values
            window: Number of recent values to analyze

        Returns:
            Trend arrow: ↑ (up), ↓ (down), → (flat)
        """
        if len(values) < 2:
            return "→"

        recent = values[-window:]
        first = recent[0]
        last = recent[-1]

        change_pct = (last - first) / abs(first) if first != 0 else 0

        if change_pct > 0.05:  # >5% increase
            return "↑"
        elif change_pct < -0.05:  # >5% decrease
            return "↓"
        else:
            return "→"

    @staticmethod
    def volatility_bars(values: list[float], width: int = 10) -> str:
        """Show volatility as bars (higher bars = more volatility).

        Args:
            values: Returns series
            width: Number of bars

        Returns:
            Volatility bar chart
        """
        if len(values) < 2:
            return "—"

        # Calculate rolling volatility
        window = max(5, len(values) // 10)
        volatilities = []

        for i in range(len(values) - window):
            window_values = values[i : i + window]
            mean = sum(window_values) / len(window_values)
            variance = sum((v - mean) ** 2 for v in window_values) / len(window_values)
            volatility = variance**0.5
            volatilities.append(volatility)

        # Render
        if not volatilities:
            return "—"

        max_vol = max(volatilities)
        if max_vol == 0:
            return "▁" * width

        # Sample to width
        step = len(volatilities) / width
        bars = ""
        for i in range(width):
            idx = min(int(i * step), len(volatilities) - 1)
            normalized = volatilities[idx] / max_vol
            level_idx = min(
                int(normalized * (len(Sparkline.LEVELS) - 1)), len(Sparkline.LEVELS) - 1
            )
            bars += Sparkline.LEVELS[level_idx]

        return bars


class ProgressBar:
    """Simple ASCII progress bars."""

    @staticmethod
    def bar(value: float, max_value: float = 1.0, width: int = 20) -> str:
        """Create a progress bar.

        Args:
            value: Current value
            max_value: Maximum value
            width: Bar width in characters

        Returns:
            Progress bar string
        """
        if max_value <= 0:
            return "█" * width

        ratio = min(value / max_value, 1.0)
        filled = int(ratio * width)
        empty = width - filled

        return "█" * filled + "░" * empty

    @staticmethod
    def bar_with_label(
        value: float, max_value: float = 1.0, width: int = 20, label_pct: bool = True
    ) -> str:
        """Create a progress bar with optional percentage.

        Args:
            value: Current value
            max_value: Maximum value
            width: Bar width
            label_pct: Show percentage

        Returns:
            Bar with optional percentage
        """
        bar = ProgressBar.bar(value, max_value, width)
        if label_pct:
            pct = (value / max_value * 100) if max_value > 0 else 0
            return f"{bar} {pct:>5.1f}%"
        return bar


class HeatmapColor:
    """Heatmap color indicators."""

    # Emoji indicators (zero dep alternative)
    @staticmethod
    def indicator(value: float, threshold_low: float = 0.33, threshold_mid: float = 0.67) -> str:
        """Get color indicator for value.

        Args:
            value: Value 0-1
            threshold_low: Lower threshold
            threshold_mid: Middle threshold

        Returns:
            Color emoji or ASCII
        """
        if value < threshold_low:
            return "🔴"  # Red (low)
        elif value < threshold_mid:
            return "🟡"  # Yellow (medium)
        else:
            return "🟢"  # Green (high)

    @staticmethod
    def ascii_indicator(
        value: float, threshold_low: float = 0.33, threshold_mid: float = 0.67
    ) -> str:
        """Get ASCII indicator (no emoji).

        Args:
            value: Value 0-1
            threshold_low: Lower threshold
            threshold_mid: Middle threshold

        Returns:
            ASCII indicator
        """
        if value < threshold_low:
            return "▓"  # Dark (low)
        elif value < threshold_mid:
            return "▒"  # Medium (medium)
        else:
            return "░"  # Light (high)


class MiniChart:
    """Compact inline charts."""

    @staticmethod
    def intraday(open_price: float, high: float, low: float, close: float) -> str:
        """Show intraday movement in 1 character.

        Range: ▁▂▃▄▅▆▇█

        Args:
            open_price: Opening price
            high: High price
            low: Low price
            close: Closing price

        Returns:
            Single character showing close position within range
        """
        if high <= low:
            return "—"

        range_width = high - low
        if range_width == 0:
            return "▄"

        # Position of close within range
        position = (close - low) / range_width
        position = max(0, min(1, position))

        level_idx = min(int(position * (len(Sparkline.LEVELS) - 1)), len(Sparkline.LEVELS) - 1)
        return Sparkline.LEVELS[level_idx]

    @staticmethod
    def range_bar(value: float, target_low: float, target_high: float, width: int = 15) -> str:
        """Show value relative to target range.

        Args:
            value: Current value
            target_low: Target range low
            target_high: Target range high
            width: Bar width

        Returns:
            Bar showing position relative to range
        """
        range_width = target_high - target_low
        if range_width <= 0:
            return "—"

        position = (value - target_low) / range_width
        position = max(0, min(1, position))

        filled = int(position * width)
        bar = "█" * filled + "░" * (width - filled)

        # Add indicator for outside range
        if value < target_low:
            return "← " + bar
        elif value > target_high:
            return bar + " →"
        else:
            return "| " + bar + " |"


def format_price_movement(
    current: float,
    previous: float,
    high: float,
    low: float,
    width: int = 30,
) -> str:
    """Format price movement with sparkline and trend.

    Args:
        current: Current price
        previous: Previous price
        high: High price
        low: Low price
        width: Chart width

    Returns:
        Formatted price movement
    """
    change = current - previous
    change_pct = (change / previous * 100) if previous > 0 else 0

    # Trend arrow
    if change > 0:
        arrow = "↑"
        color = "▲"
    elif change < 0:
        arrow = "↓"
        color = "▼"
    else:
        arrow = "→"
        color = "→"

    # Range bar
    range_bar = MiniChart.range_bar(current, low, high, width=20)

    return f"{color} {arrow} {change:+.2f} ({change_pct:+.1f}%)  {range_bar}"


def format_volatility_context(
    returns: list[float],
    current_vol: float,
    historical_avg_vol: float,
) -> str:
    """Format volatility with context.

    Args:
        returns: Recent return series
        current_vol: Current volatility
        historical_avg_vol: Average volatility

    Returns:
        Formatted volatility context
    """
    # Sparkline of volatility
    sparkline = Sparkline.volatility_bars(returns, width=15)

    # Context
    if current_vol > historical_avg_vol * 1.5:
        context = "HIGH VOLATILITY"
        indicator = "🔴"
    elif current_vol > historical_avg_vol * 1.1:
        context = "ELEVATED"
        indicator = "🟡"
    else:
        context = "NORMAL"
        indicator = "🟢"

    vol_ratio = current_vol / historical_avg_vol if historical_avg_vol > 0 else 1.0

    return f"Volatility {indicator} {context:12} {sparkline}  {vol_ratio:.1f}x avg ({current_vol:.1f}%)"


if __name__ == "__main__":
    # Examples
    print("\nSPARKLINE EXAMPLES")
    print("=" * 60)

    # Line sparkline
    prices = [100, 102, 101, 105, 103, 108, 110, 107, 111, 115]
    print(f"\nPrice movement: {Sparkline.line(prices)}")

    # Trend
    returns = [0.01, 0.02, -0.01, 0.03, 0.02, 0.04, -0.01, 0.03]
    print(f"Trend: {Sparkline.trend(returns)}")

    # Volatility
    print(f"Volatility: {Sparkline.volatility_bars(returns)}")

    # Progress bar
    print(f"\nProgress bar (75%): {ProgressBar.bar_with_label(0.75, 1.0, width=20)}")

    # Intraday
    print(
        f"\nIntraday OHLC (open=100, high=105, low=98, close=103): {MiniChart.intraday(100, 105, 98, 103)}"
    )

    # Price movement
    print(
        f"\nPrice movement (+5 pts, +5%): {format_price_movement(current=105, previous=100, high=107, low=98)}"
    )

    print("\n" + "=" * 60)
