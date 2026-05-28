"""Portfolio optimization: position sizing, rebalancing, mean-variance.

Optimizes:
- Position sizing based on conviction and risk
- Rebalancing to target weights
- Factor exposure balancing
- Risk-adjusted returns
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class OptimizationConstraints:
    """Portfolio optimization constraints."""

    min_position_size: float = 0.01  # Minimum position weight
    max_position_size: float = 0.15  # Maximum position weight
    max_concentration: float = 0.40  # Max position + top 2 combined
    min_diversification: float = 0.05  # Min diversification ratio
    target_gross_exposure: float = 1.0  # 100% = fully invested
    target_net_exposure: float = 1.0  # Net long bias
    rebalance_threshold: float = 0.02  # Rebalance if drift > 2%

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict."""
        return {
            "min_position": f"{self.min_position_size:.1%}",
            "max_position": f"{self.max_position_size:.1%}",
            "max_concentration": f"{self.max_concentration:.1%}",
            "gross_exposure_target": f"{self.target_gross_exposure:.1%}",
            "net_exposure_target": f"{self.target_net_exposure:.1%}",
            "rebalance_threshold": f"{self.rebalance_threshold:.1%}",
        }


class PositionSizer:
    """Compute optimal position sizes based on conviction and risk."""

    @staticmethod
    def size_by_conviction(
        tickers: list[str],
        convictions: dict[str, str],  # ticker -> "HIGH", "MODERATE", "LOW"
        constraints: OptimizationConstraints | None = None,
    ) -> dict[str, float]:
        """Size positions based on investment conviction.

        Args:
            tickers: List of security tickers
            convictions: Conviction level per position
            constraints: Optimization constraints

        Returns:
            Dict mapping ticker -> target weight
        """
        if not constraints:
            constraints = OptimizationConstraints()

        # Map conviction to weight multiplier
        conviction_multipliers = {
            "HIGH": 1.5,
            "MODERATE": 1.0,
            "LOW": 0.5,
        }

        # Calculate raw weights
        raw_weights = {}
        total_weight = 0.0

        for ticker in tickers:
            conviction = convictions.get(ticker, "MODERATE")
            multiplier = conviction_multipliers.get(conviction, 1.0)
            raw_weights[ticker] = multiplier
            total_weight += multiplier

        # Normalize and apply constraints
        if total_weight == 0:
            return {ticker: 1.0 / len(tickers) for ticker in tickers}

        normalized = {ticker: w / total_weight for ticker, w in raw_weights.items()}

        # Apply min/max constraints
        constrained = {}
        for ticker, weight in normalized.items():
            weight = max(constraints.min_position_size, min(constraints.max_position_size, weight))
            constrained[ticker] = weight

        # Renormalize after constraints
        constrained_sum = sum(constrained.values())
        if constrained_sum > 0:
            constrained = {
                ticker: w / constrained_sum * constraints.target_gross_exposure
                for ticker, w in constrained.items()
            }

        return constrained

    @staticmethod
    def size_by_risk(
        tickers: list[str],
        volatilities: dict[str, float],  # ticker -> annual volatility
        target_volatility: float = 0.15,  # Target 15% portfolio volatility
        constraints: OptimizationConstraints | None = None,
    ) -> dict[str, float]:
        """Size positions by inverse volatility (risk parity concept).

        Higher volatility positions get smaller weights.

        Args:
            tickers: List of tickers
            volatilities: Volatility per position
            target_volatility: Target portfolio volatility
            constraints: Constraints

        Returns:
            Dict mapping ticker -> target weight
        """
        if not constraints:
            constraints = OptimizationConstraints()

        # Inverse volatility weighting
        inverse_vols = {}
        total_inverse_vol = 0.0

        for ticker in tickers:
            vol = volatilities.get(ticker, 0.20)
            if vol > 0:
                inv_vol = 1.0 / vol
                inverse_vols[ticker] = inv_vol
                total_inverse_vol += inv_vol

        if total_inverse_vol == 0:
            return {ticker: 1.0 / len(tickers) for ticker in tickers}

        # Normalize
        weights = {
            ticker: (inv_vol / total_inverse_vol) for ticker, inv_vol in inverse_vols.items()
        }

        # Apply constraints
        constrained = {}
        for ticker, weight in weights.items():
            weight = max(constraints.min_position_size, min(constraints.max_position_size, weight))
            constrained[ticker] = weight

        # Renormalize
        constrained_sum = sum(constrained.values())
        if constrained_sum > 0:
            constrained = {
                ticker: w / constrained_sum * constraints.target_gross_exposure
                for ticker, w in constrained.items()
            }

        return constrained

    @staticmethod
    def size_by_return(
        tickers: list[str],
        expected_returns: dict[str, float],  # ticker -> expected return %
        constraints: OptimizationConstraints | None = None,
    ) -> dict[str, float]:
        """Size positions by expected return.

        Allocate more to higher expected return positions.

        Args:
            tickers: List of tickers
            expected_returns: Expected return per position
            constraints: Constraints

        Returns:
            Dict mapping ticker -> target weight
        """
        if not constraints:
            constraints = OptimizationConstraints()

        # Return weighting
        returns = {}
        total_return = 0.0

        for ticker in tickers:
            ret = expected_returns.get(ticker, 0.10)
            # Avoid negative returns
            ret = max(0.01, ret)
            returns[ticker] = ret
            total_return += ret

        if total_return == 0:
            return {ticker: 1.0 / len(tickers) for ticker in tickers}

        # Normalize
        weights = {ticker: ret / total_return for ticker, ret in returns.items()}

        # Apply constraints
        constrained = {}
        for ticker, weight in weights.items():
            weight = max(constraints.min_position_size, min(constraints.max_position_size, weight))
            constrained[ticker] = weight

        # Renormalize
        constrained_sum = sum(constrained.values())
        if constrained_sum > 0:
            constrained = {
                ticker: w / constrained_sum * constraints.target_gross_exposure
                for ticker, w in constrained.items()
            }

        return constrained


class Rebalancer:
    """Portfolio rebalancing logic."""

    @staticmethod
    def rebalancing_required(
        current_weights: dict[str, float],
        target_weights: dict[str, float],
        threshold: float = 0.02,
    ) -> bool:
        """Check if rebalancing is needed.

        Args:
            current_weights: Current position weights
            target_weights: Target position weights
            threshold: Drift threshold (e.g., 0.02 = 2%)

        Returns:
            True if any position drifted beyond threshold
        """
        for ticker, target in target_weights.items():
            current = current_weights.get(ticker, 0.0)
            drift = abs(current - target)
            if drift > threshold:
                return True

        return False

    @staticmethod
    def compute_trades(
        current_weights: dict[str, float],
        target_weights: dict[str, float],
        portfolio_value: float,
    ) -> dict[str, float]:
        """Compute trade amounts to rebalance.

        Args:
            current_weights: Current weights
            target_weights: Target weights
            portfolio_value: Total portfolio value

        Returns:
            Dict mapping ticker -> dollar amount to trade (positive = buy, negative = sell)
        """
        trades = {}

        all_tickers = set(current_weights.keys()) | set(target_weights.keys())

        for ticker in all_tickers:
            current_weight = current_weights.get(ticker, 0.0)
            target_weight = target_weights.get(ticker, 0.0)

            weight_diff = target_weight - current_weight
            trade_amount = weight_diff * portfolio_value

            if abs(trade_amount) > 100:  # Ignore trades < $100
                trades[ticker] = trade_amount

        return trades

    @staticmethod
    def format_rebalancing_summary(
        current_weights: dict[str, float],
        target_weights: dict[str, float],
        trades: dict[str, float],
        portfolio_value: float,
    ) -> list[str]:
        """Format rebalancing recommendation."""
        lines = []

        lines.append("PORTFOLIO REBALANCING RECOMMENDATION")
        lines.append("-" * 70)
        lines.append(f"{'Ticker':<10} {'Current':<12} {'Target':<12} {'Trade':<15} {'Impact':<10}")
        lines.append("-" * 70)

        for ticker in sorted(set(current_weights.keys()) | set(target_weights.keys())):
            current = current_weights.get(ticker, 0.0)
            target = target_weights.get(ticker, 0.0)
            trade = trades.get(ticker, 0.0)

            drift = (target - current) * 100
            direction = "↑ BUY" if trade > 0 else "↓ SELL" if trade < 0 else "= HOLD"

            lines.append(
                f"{ticker:<10} {current:>10.1%}  {target:>10.1%}  "
                f"{abs(trade):>12,.0f}$  {direction:>10}"
            )

        total_sell = sum(v for v in trades.values() if v < 0)
        total_buy = sum(v for v in trades.values() if v > 0)

        lines.append("-" * 70)
        lines.append(f"Total Sells: {abs(total_sell):,.0f}  |  Total Buys: {total_buy:,.0f}")

        return lines


class FactorBalancer:
    """Balance portfolio factor exposures."""

    @staticmethod
    def suggest_balancing_trades(
        current_exposures: dict[str, float],  # factor -> current exposure
        target_exposures: dict[str, float],  # factor -> target exposure (e.g., 0 for neutral)
        candidates: list[tuple[str, dict[str, float]]],  # (ticker, factor_scores)
    ) -> list[tuple[str, str]]:  # List of (ticker, action: BUY/SELL)
        """Suggest trades to balance factor exposures.

        Args:
            current_exposures: Current factor exposures
            target_exposures: Target factor exposures
            candidates: List of (ticker, factor_scores) to consider

        Returns:
            List of (ticker, "BUY"/"SELL") suggestions
        """
        suggestions = []

        for factor, current_exp in current_exposures.items():
            target_exp = target_exposures.get(factor, 0.0)

            if current_exp > target_exp:
                # Portfolio is over-exposed, find candidates to SELL
                # (high negative scores in this factor)
                best_sell = min(
                    candidates,
                    key=lambda x: x[1].get(factor, 0.0),
                    default=None,
                )
                if best_sell:
                    suggestions.append((best_sell[0], "SELL"))

            elif current_exp < target_exp:
                # Portfolio is under-exposed, find candidates to BUY
                # (high positive scores in this factor)
                best_buy = max(
                    candidates,
                    key=lambda x: x[1].get(factor, 0.0),
                    default=None,
                )
                if best_buy:
                    suggestions.append((best_buy[0], "BUY"))

        return suggestions
