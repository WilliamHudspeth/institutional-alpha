"""Portfolio optimization: position sizing, rebalancing, mean-variance.

Optimizes:
- Position sizing based on conviction and risk
- Rebalancing to target weights
- Factor exposure balancing
- Risk-adjusted returns
- Kelly criterion sizing
- Risk parity (equal risk contribution)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.optimize import minimize

from iam.backtest.weight_optimizer import ledoit_wolf_shrinkage

logger = logging.getLogger(__name__)

# ── Kelly Criterion constants ──────────────────────────────────────────────
# Fractional Kelly default: half-Kelly is industry-standard for practical
# portfolio management. Full Kelly (f* = μ/σ²) maximizes expected log wealth
# but produces extreme drawdowns (30-50% common in empirical studies).
# Half-Kelly reduces the betting fraction by 50%, cutting drawdown severity
# while retaining ~75% of the optimal growth rate. See MacLean, Thorp &
# Ziemba, "The Kelly Capital Growth Investment Criterion" (2011).
DEFAULT_KELLY_FRACTION: float = 0.5

# ── Risk Parity constants ─────────────────────────────────────────────────
# Minimum number of assets for meaningful risk parity optimization.
# With fewer assets the equal-contribution constraint is too tight or
# degenerate; fall back to inverse-vol weighting instead.
MIN_RISK_PARITY_ASSETS: int = 3

# Scipy optimizer tolerances for risk parity
RISK_PARITY_FTOL: float = 1e-9
RISK_PARITY_MAXITER: int = 1000


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

    @staticmethod
    def size_by_kelly(
        tickers: list[str],
        expected_returns: dict[str, float],  # ticker -> expected return (decimal)
        volatilities: dict[str, float],  # ticker -> annual volatility (decimal)
        kelly_fraction: float = DEFAULT_KELLY_FRACTION,
        constraints: OptimizationConstraints | None = None,
    ) -> dict[str, float]:
        """Size positions using continuous Kelly criterion.

        Implements the continuous-form Kelly formula for normally-distributed
        returns::

            f* = μ / σ²

        where μ = expected return and σ² = variance. This maximises the
        expected logarithm of wealth under i.i.d. normal returns (Thorp, "The
        Kelly Criterion in Blackjack Sports Betting, and the Stock Market",
        2008).

        Fractional Kelly (default *half*-Kelly) is applied uniformly to the
        raw Kelly fraction before normalisation.  This preserves the relative
        Kelly-optimal proportions across positive-expected-return positions
        while reducing overall aggressiveness — the industry-standard
        compromise between growth and drawdown control.

        Positions with non-positive expected return receive zero raw Kelly
        weight but may still appear at ``min_position_size`` after the
        clamping step, matching the degrade-don't-crash convention used
        across the codebase.

        Args:
            tickers: List of security tickers.
            expected_returns: Expected annual return per ticker (decimal).
            volatilities: Annual volatility per ticker (decimal).
            kelly_fraction: Fractional Kelly multiplier (0..1). Default 0.5.
            constraints: Optimization constraints.

        Returns:
            Dict mapping ticker -> target weight.
        """
        if not constraints:
            constraints = OptimizationConstraints()

        raw_kelly: dict[str, float] = {}
        total_kelly = 0.0

        for ticker in tickers:
            mu = expected_returns.get(ticker, 0.0)
            vol = volatilities.get(ticker, 0.20)
            if mu > 0 and vol > 0:
                variance = vol * vol
                kf = mu / variance
            else:
                kf = 0.0
            kf *= kelly_fraction
            raw_kelly[ticker] = kf
            total_kelly += kf

        if total_kelly == 0:
            return {ticker: 1.0 / len(tickers) for ticker in tickers}

        # Normalize relative Kelly proportions
        normalized = {ticker: w / total_kelly for ticker, w in raw_kelly.items()}

        # Apply min/max constraints
        constrained = {}
        for ticker, weight in normalized.items():
            weight = max(
                constraints.min_position_size,
                min(constraints.max_position_size, weight),
            )
            constrained[ticker] = weight

        # Renormalize to target gross exposure
        constrained_sum = sum(constrained.values())
        if constrained_sum > 0:
            constrained = {
                ticker: w / constrained_sum * constraints.target_gross_exposure
                for ticker, w in constrained.items()
            }

        return constrained

    @staticmethod
    def size_by_risk_parity(
        tickers: list[str],
        position_returns: dict[str, list[float]],  # ticker -> return series
        constraints: OptimizationConstraints | None = None,
    ) -> dict[str, float]:
        """Size positions by equal risk contribution (true risk parity).

        Unlike the simple inverse-volatility heuristic (:meth:`size_by_risk`),
        this method uses the **full covariance matrix** and solves for weights
        where every position contributes equally to total portfolio variance::

            RC_i = w_i · (Σ w)_i  /  √(wᵀ Σ w)

        The objective minimises the sum of squared deviations of each RC_i
        from the target RC = portfolio_vol / N.

        The covariance matrix is estimated via **Ledoit-Wolf shrinkage**
        (:func:`iam.backtest.weight_optimizer.ledoit_wolf_shrinkage`) to
        remain robust with short return histories.

        Args:
            tickers: List of security tickers.
            position_returns: Dict mapping ticker -> list of periodic returns.
            constraints: Optimization constraints.

        Returns:
            Dict mapping ticker -> target weight.
        """
        if not constraints:
            constraints = OptimizationConstraints()

        # Minimum-assets guard — risk parity is not meaningful / degenerate
        # for very small universes.
        if len(tickers) < MIN_RISK_PARITY_ASSETS:
            logger.warning(
                "Risk parity requires at least %d assets (%d provided); "
                "falling back to inverse-vol sizing.",
                MIN_RISK_PARITY_ASSETS,
                len(tickers),
            )
            # Compute volatilities from the return series for the fallback
            vols = {}
            for t in tickers:
                series = position_returns.get(t, [])
                if len(series) >= 2:
                    mu = sum(series) / len(series)
                    var = sum((r - mu) ** 2 for r in series) / (len(series) - 1)
                    vols[t] = float(np.sqrt(var)) if var > 0 else 0.20
                else:
                    vols[t] = 0.20
            return PositionSizer.size_by_risk(tickers, vols, constraints=constraints)

        # Build aligned return matrix (n_obs x n_assets)
        n = len(tickers)
        n_obs = min(len(position_returns.get(t, [])) for t in tickers)
        if n_obs < 2:
            logger.warning(
                "Fewer than 2 observations available; "
                "falling back to inverse-vol sizing."
            )
            vols = {t: 0.20 for t in tickers}
            return PositionSizer.size_by_risk(tickers, vols, constraints=constraints)

        X = np.column_stack(
            [position_returns[t][:n_obs] for t in tickers]
        )
        cov = ledoit_wolf_shrinkage(X)

        # Objective: minimise squared deviation of risk contributions
        def _objective(w: np.ndarray) -> float:
            port_var = float(w @ cov @ w)
            if port_var <= 0:
                return 1e6
            port_vol = np.sqrt(port_var)
            rc = w * (cov @ w) / port_vol
            target_rc = port_vol / n
            return float(np.sum((rc - target_rc) ** 2))

        bounds = [(0.0, 1.0)] * n
        constraints_list = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
        x0 = np.ones(n) / n

        result = minimize(
            _objective,
            x0,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints_list,
            options={"ftol": RISK_PARITY_FTOL, "maxiter": RISK_PARITY_MAXITER},
        )

        if not result.success:
            logger.warning(
                "Risk parity optimizer did not converge (%s); "
                "falling back to inverse-vol sizing.",
                result.message,
            )
            vols = {t: float(np.sqrt(np.var(position_returns[t]))) for t in tickers}
            return PositionSizer.size_by_risk(tickers, vols, constraints=constraints)

        weights = dict(zip(tickers, result.x))

        # Apply min/max constraints
        constrained = {}
        for ticker, weight in weights.items():
            weight = max(
                constraints.min_position_size,
                min(constraints.max_position_size, weight),
            )
            constrained[ticker] = weight

        # Renormalize to target gross exposure
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

    @staticmethod
    def suggest_sector_rotation_trades(
        sector_tilts: dict[str, float],  # sector -> overweight/underweight delta
        position_sectors: dict[str, str],  # ticker -> sector
        current_weights: dict[str, float],  # ticker -> current weight
    ) -> list[tuple[str, str]]:
        """Translate sector-rotation tilts into per-ticker BUY/SELL suggestions.

        This is the integration point between :class:`SectorRotationEngine`
        and the factor-balancing framework.  Sector tilts (deltas from current
        sector exposure) are mapped onto individual positions: tickers in
        overweight sectors get BUY suggestions, tickers in underweight sectors
        get SELL suggestions.

        Args:
            sector_tilts: Sector-level over/underweight deltas
                (e.g. ``{"Technology": +0.03, "Utilities": -0.02}``).
            position_sectors: Sector assignment per ticker.
            current_weights: Current weight per ticker (used only for
                non-zero-weight tickers — zero-weight / new candidates always
                receive BUY if their sector is tilted upward).

        Returns:
            List of (ticker, "BUY"/"SELL") suggestions.
        """
        suggestions: list[tuple[str, str]] = []

        for ticker, sector in position_sectors.items():
            tilt = sector_tilts.get(sector, 0.0)
            if tilt > 0.01:
                suggestions.append((ticker, "BUY"))
            elif tilt < -0.01:
                current = current_weights.get(ticker, 0.0)
                if current > 0:
                    suggestions.append((ticker, "SELL"))

        return suggestions
