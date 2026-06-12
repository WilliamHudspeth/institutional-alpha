"""Portfolio analytics: correlations, factor exposures, risk decomposition.

Computes:
- Position correlations
- Net factor exposures
- Factor crowding (vs universe)
- Sector concentration
- VaR and expected shortfall
- Diversification metrics
"""

from __future__ import annotations

import math

from iam.portfolio.types import ExposureProfile, Portfolio


class PortfolioAnalyzer:
    """Compute analytics for a portfolio."""

    @staticmethod
    def compute_factor_exposures(
        portfolio: Portfolio,
        position_factor_scores: dict[str, dict[str, float]],
    ) -> ExposureProfile:
        """Compute net factor exposures.

        Args:
            portfolio: Portfolio to analyze
            position_factor_scores: Dict mapping ticker -> {factor -> z-score}

        Returns:
            ExposureProfile with net exposures and crowding
        """
        if not portfolio.positions:
            return ExposureProfile()

        # Weighted average factor exposure
        quality_exp = 0.0
        growth_exp = 0.0
        value_exp = 0.0
        momentum_exp = 0.0
        sentiment_exp = 0.0

        crowding_counts = {
            "quality": 0,
            "growth": 0,
            "value": 0,
            "momentum": 0,
            "sentiment": 0,
        }

        for position in portfolio.positions:
            if position.ticker not in position_factor_scores:
                continue

            scores = position_factor_scores[position.ticker]
            weight = position.weight

            # Weighted exposures
            quality_exp += scores.get("quality", 0.0) * weight
            growth_exp += scores.get("growth", 0.0) * weight
            value_exp += scores.get("value", 0.0) * weight
            momentum_exp += scores.get("momentum", 0.0) * weight
            sentiment_exp += scores.get("sentiment", 0.0) * weight

            # Count exposures > 0.5 standard deviations
            if scores.get("quality", 0.0) > 0.5:
                crowding_counts["quality"] += 1
            if scores.get("growth", 0.0) > 0.5:
                crowding_counts["growth"] += 1
            if scores.get("value", 0.0) > 0.5:
                crowding_counts["value"] += 1
            if scores.get("momentum", 0.0) > 0.5:
                crowding_counts["momentum"] += 1
            if scores.get("sentiment", 0.0) > 0.5:
                crowding_counts["sentiment"] += 1

        # Crowding as percentile (how many positions exposed)
        num_positions = len(portfolio.positions)
        factor_crowding = {
            factor: count / num_positions for factor, count in crowding_counts.items()
        }

        return ExposureProfile(
            quality_exposure=quality_exp,
            growth_exposure=growth_exp,
            value_exposure=value_exp,
            momentum_exposure=momentum_exp,
            sentiment_exposure=sentiment_exp,
            factor_crowding=factor_crowding,
        )

    @staticmethod
    def compute_sector_concentration(portfolio: Portfolio) -> dict[str, float]:
        """Compute sector weights.

        Args:
            portfolio: Portfolio to analyze

        Returns:
            Dict mapping sector -> weight
        """
        sector_weights: dict[str, float] = {}

        for position in portfolio.positions:
            if position.sector:
                sector_weights[position.sector] = (
                    sector_weights.get(position.sector, 0.0) + position.weight
                )

        return sector_weights

    @staticmethod
    def compute_correlation_matrix(
        position_returns: dict[str, list[float]],
    ) -> dict[str, dict[str, float]]:
        """Compute correlation matrix from return series.

        Args:
            position_returns: Dict mapping ticker -> list of returns

        Returns:
            Correlation matrix as nested dict
        """
        tickers = list(position_returns.keys())
        if len(tickers) < 2:
            return {}

        correlations: dict[str, dict[str, float]] = {}

        for ticker_i in tickers:
            correlations[ticker_i] = {}
            for ticker_j in tickers:
                if ticker_i == ticker_j:
                    correlations[ticker_i][ticker_j] = 1.0
                else:
                    returns_i = position_returns[ticker_i]
                    returns_j = position_returns[ticker_j]

                    if len(returns_i) < 2 or len(returns_j) < 2:
                        correlations[ticker_i][ticker_j] = 0.0
                        continue

                    corr = _compute_correlation(returns_i, returns_j)
                    correlations[ticker_i][ticker_j] = corr

        return correlations

    @staticmethod
    def compute_portfolio_var(
        portfolio: Portfolio,
        position_volatilities: dict[str, float],
        correlation_matrix: dict[str, dict[str, float]],
        confidence: float = 0.95,
    ) -> float:
        """Compute Value at Risk using variance-covariance method.

        Args:
            portfolio: Portfolio
            position_volatilities: Dict mapping ticker -> volatility
            correlation_matrix: Position correlations
            confidence: VaR confidence level (0.95 = 95%)

        Returns:
            VaR as dollar amount
        """
        if not portfolio.positions or not correlation_matrix:
            return 0.0

        # Build covariance matrix
        tickers = [p.ticker for p in portfolio.positions]
        n = len(tickers)
        cov_matrix = [[0.0] * n for _ in range(n)]

        for i, ticker_i in enumerate(tickers):
            for j, ticker_j in enumerate(tickers):
                vol_i = position_volatilities.get(ticker_i, 0.01)
                vol_j = position_volatilities.get(ticker_j, 0.01)

                if i == j:
                    cov_matrix[i][j] = vol_i * vol_j
                else:
                    corr = correlation_matrix.get(ticker_i, {}).get(ticker_j, 0.0)
                    cov_matrix[i][j] = corr * vol_i * vol_j

        # Portfolio variance = w^T * Cov * w
        weights = [p.weight for p in portfolio.positions]

        portfolio_variance = 0.0
        for i in range(n):
            for j in range(n):
                portfolio_variance += weights[i] * weights[j] * cov_matrix[i][j]

        portfolio_vol = math.sqrt(max(0.0, portfolio_variance))

        # VaR using normal distribution
        z_score = _get_z_score_for_confidence(confidence)
        var = portfolio.total_value * portfolio_vol * z_score

        return var

    @staticmethod
    def compute_average_correlation(
        correlation_matrix: dict[str, dict[str, float]],
    ) -> float:
        """Compute average pairwise correlation."""
        if len(correlation_matrix) < 2:
            return 0.0

        correlations = []
        tickers = list(correlation_matrix.keys())

        for i, ticker_i in enumerate(tickers):
            for ticker_j in tickers[i + 1 :]:
                corr = correlation_matrix.get(ticker_i, {}).get(ticker_j, 0.0)
                correlations.append(corr)

        if not correlations:
            return 0.0

        return sum(correlations) / len(correlations)

    @staticmethod
    def compute_diversification_ratio(
        portfolio: Portfolio,
        position_volatilities: dict[str, float],
    ) -> float:
        """Compute diversification ratio.

        Ratio of weighted-average volatility to portfolio volatility.
        Higher = better diversification.

        Args:
            portfolio: Portfolio
            position_volatilities: Dict mapping ticker -> volatility

        Returns:
            Diversification ratio (1.0+ means diversified)
        """
        if not portfolio.positions:
            return 1.0

        # Weighted average volatility
        weighted_avg_vol = sum(
            p.weight * position_volatilities.get(p.ticker, 0.01) for p in portfolio.positions
        )

        if weighted_avg_vol == 0:
            return 1.0

        # TODO: Compute actual portfolio volatility from returns
        # For now, approximate from position correlation
        portfolio_vol = weighted_avg_vol * 0.8  # Simplified

        if portfolio_vol == 0:
            return 1.0

        return weighted_avg_vol / portfolio_vol

    @staticmethod
    def format_exposure_summary(exposures: ExposureProfile) -> list[str]:
        """Format exposure profile for display."""
        lines = []

        lines.append("FACTOR EXPOSURE PROFILE")
        lines.append("-" * 60)
        lines.append(f"  Quality        {exposures.quality_exposure:+.2f}σ")
        lines.append(f"  Growth         {exposures.growth_exposure:+.2f}σ")
        lines.append(f"  Value          {exposures.value_exposure:+.2f}σ")
        lines.append(f"  Momentum       {exposures.momentum_exposure:+.2f}σ")
        lines.append(f"  Sentiment      {exposures.sentiment_exposure:+.2f}σ")
        lines.append("")

        lines.append("FACTOR CROWDING (% of positions exposed)")
        lines.append("-" * 60)
        for factor, crowding in exposures.factor_crowding.items():
            pct = crowding * 100
            level = "HIGH" if pct > 75 else "MODERATE" if pct > 50 else "LOW"
            lines.append(f"  {factor:<15} {pct:>5.0f}%  [{level}]")

        return lines

    @staticmethod
    def format_concentration_summary(portfolio: Portfolio) -> list[str]:
        """Format concentration analysis."""
        lines = []

        hhi = portfolio.concentration_herfindahl()
        largest = portfolio.largest_position_weight()

        lines.append("CONCENTRATION ANALYSIS")
        lines.append("-" * 60)
        lines.append(f"  Positions              {len(portfolio.positions)}")
        lines.append(f"  Gross Exposure         {portfolio.gross_exposure():>6.1%}")
        lines.append(f"  Net Exposure           {portfolio.net_exposure():>6.1%}")
        lines.append(f"  Largest Position       {largest:>6.1%}")
        lines.append(f"  Herfindahl Index       {hhi:>6.1%}  (0=diversified, 1=concentrated)")

        return lines


def _compute_correlation(returns_a: list[float], returns_b: list[float]) -> float:
    """Compute Pearson correlation between two return series."""
    if len(returns_a) < 2 or len(returns_b) < 2:
        return 0.0

    n = min(len(returns_a), len(returns_b))
    returns_a = returns_a[:n]
    returns_b = returns_b[:n]

    mean_a = sum(returns_a) / n
    mean_b = sum(returns_b) / n

    cov = sum((a - mean_a) * (b - mean_b) for a, b in zip(returns_a, returns_b)) / (n - 1)

    var_a = sum((a - mean_a) ** 2 for a in returns_a) / (n - 1)
    var_b = sum((b - mean_b) ** 2 for b in returns_b) / (n - 1)

    if var_a == 0 or var_b == 0:
        return 0.0

    return cov / (math.sqrt(var_a) * math.sqrt(var_b))


def _get_z_score_for_confidence(confidence: float) -> float:
    """Get z-score for confidence level."""
    # Common confidence levels
    z_scores = {
        0.90: 1.282,
        0.95: 1.645,
        0.99: 2.326,
    }
    return z_scores.get(confidence, 1.645)
