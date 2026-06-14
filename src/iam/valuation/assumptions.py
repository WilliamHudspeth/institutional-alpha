from dataclasses import dataclass

import numpy as np


@dataclass
class AssumptionDistribution:
    """Represents an aggregated assumption with multiple sourced beliefs."""

    name: str
    historical_cagr: float | None = None
    sustainable_growth: float | None = None
    market_implied: float | None = None
    sector_median: float | None = None
    bottom_up: float | None = None

    user_override: float | None = None

    def get_sources(self) -> list[tuple[str, float, float]]:
        """Returns a list of (source_name, value, weight) tuples for active sources."""
        sources = []
        # Basic heuristic weighting for now
        if self.historical_cagr is not None:
            sources.append(("Historical CAGR", self.historical_cagr, 0.40))
        if self.sustainable_growth is not None:
            sources.append(("Sustainable Growth", self.sustainable_growth, 0.25))
        if self.bottom_up is not None:
            sources.append(("Bottom-Up TAM", self.bottom_up, 0.20))
        if self.sector_median is not None:
            sources.append(("Sector Median", self.sector_median, 0.10))
        if self.market_implied is not None:
            sources.append(("Market Implied", self.market_implied, 0.05))

        # Normalize weights if some sources are missing
        total_weight = sum(w for _, _, w in sources)
        if total_weight > 0:
            sources = [(n, v, w / total_weight) for n, v, w in sources]

        return sources

    @property
    def recommended_value(self) -> float:
        if self.user_override is not None:
            return self.user_override

        sources = self.get_sources()
        if not sources:
            return 0.0

        return sum(v * w for _, v, w in sources)

    @property
    def confidence_score(self) -> float:
        """Confidence score based on the number of overlapping sources and their variance."""
        sources = self.get_sources()
        if not sources:
            return 0.0
        if len(sources) == 1:
            return 0.30

        vals = [v for _, v, _ in sources]
        variance = np.var(vals)
        # Lower variance -> higher confidence
        # Heuristic: max confidence of 0.95
        base_confidence = min(0.95, 0.40 + (len(sources) * 0.10))
        penalty = min(0.40, variance * 10)  # arbitrary penalty scaling
        return max(0.10, base_confidence - penalty)  # type: ignore
