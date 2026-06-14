"""
expectations_battlefield.py

Replaces a simplistic "normal distribution" alignment engine with a
scenario‑based expectations battlefield. Integrates directly into the
VerdictGenerator to produce nuanced recommendations like "Speculative Buy"
when intrinsic value is high but market expectations are far richer.
"""

from dataclasses import dataclass

import numpy as np

# ---------------------------------------------------------------------------
# 1. Core data structures – scenario‑based views, not normal distributions
# ---------------------------------------------------------------------------


@dataclass
class Scenario:
    """A single scenario with its probability."""

    probability: float  # 0.0 – 1.0
    growth: float  # e.g. 0.10 for 10 %
    margin: float  # operating margin
    roic: float  # return on invested capital


@dataclass
class ScenarioDistribution:
    """A discrete probability distribution over a set of scenarios."""

    scenarios: list[Scenario]

    def mean_growth(self) -> float:
        return sum(s.probability * s.growth for s in self.scenarios)

    def mean_margin(self) -> float:
        return sum(s.probability * s.margin for s in self.scenarios)

    def mean_roic(self) -> float:
        return sum(s.probability * s.roic for s in self.scenarios)

    def median_growth(self) -> float:
        return self._weighted_percentile("growth", 0.5)

    def median_margin(self) -> float:
        return self._weighted_percentile("margin", 0.5)

    def median_roic(self) -> float:
        return self._weighted_percentile("roic", 0.5)

    def _weighted_percentile(self, attr: str, q: float) -> float:
        """Weighted median/percentile for a given attribute."""
        vals = np.array([getattr(s, attr) for s in self.scenarios])
        probs = np.array([s.probability for s in self.scenarios])
        order = np.argsort(vals)
        vals = vals[order]
        probs = probs[order]
        cum = np.cumsum(probs)
        idx = np.searchsorted(cum, q * cum[-1])
        return vals[min(idx, len(vals) - 1)]

    def variance_growth(self) -> float:
        m = self.mean_growth()
        return sum(s.probability * (s.growth - m) ** 2 for s in self.scenarios)

    def variance_margin(self) -> float:
        m = self.mean_margin()
        return sum(s.probability * (s.margin - m) ** 2 for s in self.scenarios)

    def variance_roic(self) -> float:
        m = self.mean_roic()
        return sum(s.probability * (s.roic - m) ** 2 for s in self.scenarios)


# ---------------------------------------------------------------------------
# 2. Overlap and alignment metrics
# ---------------------------------------------------------------------------


def distribution_overlap(
    dist_a: ScenarioDistribution,
    dist_b: ScenarioDistribution,
    metric: str = "growth",
    bins: int = 50,
) -> float:
    """
    Approximate overlap between two scenario distributions by binning.
    Returns a value in [0, 1] (higher = more overlap).
    """
    vals_a = np.array([getattr(s, metric) for s in dist_a.scenarios])
    probs_a = np.array([s.probability for s in dist_a.scenarios])
    vals_b = np.array([getattr(s, metric) for s in dist_b.scenarios])
    probs_b = np.array([s.probability for s in dist_b.scenarios])

    all_vals = np.concatenate([vals_a, vals_b])
    if all_vals.size == 0:
        return 1.0
    if all_vals.min() == all_vals.max():
        return 1.0

    bin_edges = np.linspace(all_vals.min(), all_vals.max(), bins + 1)
    hist_a, _ = np.histogram(vals_a, bins=bin_edges, weights=probs_a, density=True)
    hist_b, _ = np.histogram(vals_b, bins=bin_edges, weights=probs_b, density=True)

    bin_width = bin_edges[1] - bin_edges[0]
    overlap = np.sum(np.minimum(hist_a, hist_b)) * bin_width
    return min(overlap, 1.0)


def alignment_score(intrinsic: ScenarioDistribution, market: ScenarioDistribution) -> float:
    """
    Alignment score (0‑100) combining:
      - Overlap of growth distributions
      - Distance between means (growth)
      - Distance between medians (growth)
      - Relative variance ratio
    """
    overlap_g = distribution_overlap(intrinsic, market, "growth")

    std_int = np.sqrt(intrinsic.variance_growth())
    std_mkt = np.sqrt(market.variance_growth())
    scale = max(std_int, std_mkt, 1e-6)
    mean_dist = abs(intrinsic.mean_growth() - market.mean_growth()) / scale

    median_dist = abs(intrinsic.median_growth() - market.median_growth()) / scale

    var_int = intrinsic.variance_growth()
    var_mkt = market.variance_growth()
    if max(var_int, var_mkt) < 1e-12:
        var_ratio = 1.0
    else:
        var_ratio = min(var_int, var_mkt) / max(var_int, var_mkt)

    raw = (
        0.5 * overlap_g
        + 0.2 * max(0, (1 - mean_dist))
        + 0.15 * max(0, (1 - median_dist))
        + 0.15 * var_ratio
    )
    return max(0.0, min(100.0, raw * 100))


# ---------------------------------------------------------------------------
# 3. The Battlefield Engine
# ---------------------------------------------------------------------------


@dataclass
class ExpectationBattlefieldExplicit:
    market_growth: float
    intrinsic_growth: float
    market_margin: float
    intrinsic_margin: float
    market_roic: float
    intrinsic_roic: float
    growth_overlap: float
    alignment_score: float
    primary_disagreement: str
    expectation_mismatch_score: float

    # Expanded battlefield fields
    market_terminal_growth: float = 0.025
    intrinsic_terminal_growth: float = 0.025
    market_beta: float = 1.0
    intrinsic_beta: float = 1.0
    market_erp: float = 0.05
    intrinsic_erp: float = 0.05
    market_tax_rate: float = 0.21
    intrinsic_tax_rate: float = 0.21
    market_share_count: float = 0.0
    intrinsic_share_count: float = 0.0
    market_net_debt: float = 0.0
    intrinsic_net_debt: float = 0.0

    @property
    def growth_gap(self) -> float:
        return self.market_growth - self.intrinsic_growth

    @property
    def margin_gap(self) -> float:
        return self.market_margin - self.intrinsic_margin

    @property
    def roic_gap(self) -> float:
        return self.market_roic - self.intrinsic_roic

    @property
    def terminal_growth_gap(self) -> float:
        return self.market_terminal_growth - self.intrinsic_terminal_growth

    @property
    def beta_gap(self) -> float:
        return self.market_beta - self.intrinsic_beta

    @property
    def erp_gap(self) -> float:
        return self.market_erp - self.intrinsic_erp

    @property
    def disagreement_ranking(self) -> list[tuple[str, float]]:
        """Ranks the factors by the absolute magnitude of their percentage gap."""
        gaps = [
            ("Growth", abs(self.growth_gap)),
            ("Margin", abs(self.margin_gap)),
            ("ROIC", abs(self.roic_gap)),
            ("Terminal Growth", abs(self.terminal_growth_gap)),
            ("Beta", abs(self.beta_gap)),
            ("ERP", abs(self.erp_gap)),
        ]
        return sorted(gaps, key=lambda x: x[1], reverse=True)

    def summary(self) -> str:
        def pct(x):
            return f"{x * 100:+.1f}%"

        return (
            "====================\n"
            "EXPECTATIONS BATTLEFIELD\n"
            "====================\n\n"
            f"Growth\n"
            f"  Market:    {pct(self.market_growth)}\n"
            f"  Intrinsic: {pct(self.intrinsic_growth)}\n"
            f"  Gap:       {pct(self.growth_gap)}\n\n"
            f"Margin\n"
            f"  Market:    {pct(self.market_margin)}\n"
            f"  Intrinsic: {pct(self.intrinsic_margin)}\n"
            f"  Gap:       {pct(self.margin_gap)}\n\n"
            f"ROIC\n"
            f"  Market:    {pct(self.market_roic)}\n"
            f"  Intrinsic: {pct(self.intrinsic_roic)}\n"
            f"  Gap:       {pct(self.roic_gap)}\n\n"
            f"Growth Overlap:    {self.growth_overlap:.2f}\n"
            f"Alignment Score:   {self.alignment_score:.0f}/100\n"
            f"Primary Disagreement: {self.primary_disagreement}\n"
            f"Mismatch Score:    {self.expectation_mismatch_score:.0f}/100\n\n"
            f"Interpretation:\n"
            f"{self._interpretation()}\n"
        )

    def _interpretation(self) -> str:
        if self.expectation_mismatch_score > 70:
            return "Market is materially more optimistic than our base-case assumptions."
        elif self.expectation_mismatch_score > 40:
            return "Moderate disagreement – market pricing some upside we don't fully see."
        else:
            return "Views are broadly aligned."


class ExpectationsBattlefieldEngine:
    """
    Computes the battlefield from intrinsic (model/research) and market
    (reverse‑DCF‑implied) scenario distributions.
    """

    def __init__(self, intrinsic: ScenarioDistribution, market: ScenarioDistribution):
        self.intrinsic = intrinsic
        self.market = market

    def compute(self) -> ExpectationBattlefieldExplicit:
        # Means
        int_g = self.intrinsic.mean_growth()
        int_m = self.intrinsic.mean_margin()
        int_r = self.intrinsic.mean_roic()
        mkt_g = self.market.mean_growth()
        mkt_m = self.market.mean_margin()
        mkt_r = self.market.mean_roic()

        # Gaps
        gaps = {
            "Growth": abs(mkt_g - int_g),
            "Margin": abs(mkt_m - int_m),
            "ROIC": abs(mkt_r - int_r),
        }
        primary = max(gaps, key=gaps.get)

        # Overlap and alignment
        growth_overlap = distribution_overlap(self.intrinsic, self.market, "growth")
        alignment = alignment_score(self.intrinsic, self.market)

        std_int_g = np.sqrt(self.intrinsic.variance_growth())
        std_mkt_g = np.sqrt(self.market.variance_growth())
        scale_g = (std_int_g + std_mkt_g) / 2 + 1e-6
        norm_gap_g = gaps["Growth"] / scale_g

        std_int_m = np.sqrt(self.intrinsic.variance_margin())
        std_mkt_m = np.sqrt(self.market.variance_margin())
        scale_m = (std_int_m + std_mkt_m) / 2 + 1e-6
        norm_gap_m = gaps["Margin"] / scale_m

        std_int_r = np.sqrt(self.intrinsic.variance_roic())
        std_mkt_r = np.sqrt(self.market.variance_roic())
        scale_r = (std_int_r + std_mkt_r) / 2 + 1e-6
        norm_gap_r = gaps["ROIC"] / scale_r

        avg_norm_gap = (norm_gap_g + norm_gap_m + norm_gap_r) / 3
        mismatch_score = min(100.0, max(0.0, avg_norm_gap * 50))

        return ExpectationBattlefieldExplicit(
            market_growth=mkt_g,
            intrinsic_growth=int_g,
            market_margin=mkt_m,
            intrinsic_margin=int_m,
            market_roic=mkt_r,
            intrinsic_roic=int_r,
            growth_overlap=growth_overlap,
            alignment_score=alignment,
            primary_disagreement=primary,
            expectation_mismatch_score=mismatch_score,
        )


def build_distributions(
    profile, triangulation
) -> tuple[ScenarioDistribution, ScenarioDistribution]:
    """Helper to generate intrinsic and market scenario distributions.

    Args:
        profile: CompanyProfile
        triangulation: TriangulatedGrowth

    Returns:
        (intrinsic_dist, market_dist)
    """
    mkt_g = profile.implied_growth
    mkt_m = profile.op_margin
    mkt_r = profile.roic

    market_dist = ScenarioDistribution(
        [
            Scenario(probability=0.20, growth=mkt_g - 0.05, margin=mkt_m - 0.02, roic=mkt_r - 0.02),
            Scenario(probability=0.60, growth=mkt_g, margin=mkt_m, roic=mkt_r),
            Scenario(probability=0.20, growth=mkt_g + 0.05, margin=mkt_m + 0.02, roic=mkt_r + 0.02),
        ]
    )

    int_g = triangulation.blended_growth
    int_m = profile.op_margin
    int_r = profile.roic
    spread = profile.hist_volatility

    intrinsic_dist = ScenarioDistribution(
        [
            Scenario(
                probability=0.20, growth=int_g - spread, margin=int_m - 0.02, roic=int_r - 0.02
            ),
            Scenario(probability=0.60, growth=int_g, margin=int_m, roic=int_r),
            Scenario(
                probability=0.20, growth=int_g + spread, margin=int_m + 0.02, roic=int_r + 0.02
            ),
        ]
    )

    return intrinsic_dist, market_dist
