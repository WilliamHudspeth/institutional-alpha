"""Stage 4: Triangulation.

Takes the outputs of the three valuation stages and decides whether they
agree, two-of-three agree, or all three disagree.

Decision rule: equal-weighted, closest cluster wins.

Concretely:
  - Compute pairwise distances between the three fair_value_to_price ratios.
  - If all three are within a tight band (default 10%), call it AGREE.
  - Else find the pair with the smallest distance. If that pair is tighter
    than a wider band (default 20%) and the third method is clearly further,
    call it TWO_OF_THREE and flag the third as an outlier.
  - Else call it DISAGREE — the three methods are saying genuinely different
    things, and we shouldn't pretend to have a verdict.

Confidence is highest when methods agree and is reduced by both the spread
and by any individual method having low intrinsic confidence.
"""

from __future__ import annotations

from itertools import combinations
from typing import Optional

from iam.valuation.types import Method, ValuationResult, TriangulationResult


# Reverse DCF doesn't produce a fair_value_to_price directly — it produces
# an implied expectations set. To put it on the same axis as the other two
# stages, we convert it: how does implied growth compare to historical max?
# If the market is implying ~peak growth, that's ~0% upside on a fundamentals
# basis. If implying below peak, that's upside; well above peak, downside.
#
# This is an approximation but a defensible one: it lets reverse DCF
# participate in cluster math without inventing a fake fair value.
def reverse_dcf_to_ratio(result: ValuationResult) -> Optional[float]:
    """Convert a reverse-DCF result into a fair_value_to_price-comparable
    ratio for triangulation. Returns None if the result lacks the inputs."""
    if result.implied is None:
        return None
    vs_max = result.implied.growth_vs_history_max
    if vs_max is None:
        return None
    # vs_max < 1.0  => market is implying *less* than peak growth => upside
    # vs_max > 1.0  => market needs above-peak growth => downside
    # Map: vs_max 0.5 -> +0.50, 1.0 -> 0.0, 1.5 -> -0.33, 2.0 -> -0.50.
    # Functional form: ratio = (1/vs_max) - 1, clipped.
    if vs_max <= 0:
        return None
    raw = (1.0 / vs_max) - 1.0
    return max(-0.9, min(2.0, raw))


class Triangulator:
    """Stage 4 of the pipeline.

    Parameters control the tolerance bands. Defaults are reasonable for
    generalist equity work; tighten for high-conviction screens, loosen for
    early-stage / volatile names where method spread is naturally wider.
    """

    def __init__(
        self,
        agree_band: float = 0.10,        # all three within ±10% => AGREE
        pair_band: float = 0.20,         # two within ±20% with third outside => TWO_OF_THREE
    ):
        self.agree_band = agree_band
        self.pair_band = pair_band

    def triangulate(
        self,
        reverse_dcf: ValuationResult,
        relative: ValuationResult,
        intrinsic: ValuationResult,
    ) -> TriangulationResult:
        # Extract comparable ratios. Reverse DCF gets the special conversion.
        ratios: dict[Method, Optional[float]] = {
            Method.REVERSE_DCF: reverse_dcf_to_ratio(reverse_dcf),
            Method.RELATIVE: relative.fair_value_to_price,
            Method.INTRINSIC: intrinsic.fair_value_to_price,
        }
        confidences: dict[Method, float] = {
            Method.REVERSE_DCF: reverse_dcf.confidence,
            Method.RELATIVE: relative.confidence,
            Method.INTRINSIC: intrinsic.confidence,
        }

        # Drop methods that couldn't produce a comparable number.
        available = {m: r for m, r in ratios.items() if r is not None}

        if len(available) == 0:
            return TriangulationResult(
                verdict="no_data",
                notes=["None of the three methods produced a comparable result."],
            )

        if len(available) == 1:
            method, ratio = next(iter(available.items()))
            return TriangulationResult(
                cluster_center=ratio,
                cluster_members=[method],
                outliers=[m for m in Method if m not in available],
                spread=0.0,
                confidence=confidences[method] * 0.5,  # only one method — halve confidence
                verdict="single_method",
                notes=[f"Only {method.value} produced a result; confidence reduced."],
            )

        if len(available) == 2:
            methods = list(available.keys())
            ratios_list = list(available.values())
            distance = abs(ratios_list[0] - ratios_list[1])
            center = sum(ratios_list) / 2
            min_conf = min(confidences[m] for m in methods)
            if distance < self.pair_band:
                verdict = "two_of_three"
                conf = min_conf * 0.85
            else:
                verdict = "disagree"
                conf = min_conf * 0.4
            return TriangulationResult(
                cluster_center=center,
                cluster_members=methods,
                outliers=[m for m in Method if m not in available],
                spread=distance,
                confidence=conf,
                verdict=verdict,
                notes=[f"Only 2 of 3 methods available; spread {distance:.0%}."],
            )

        # All three available — the interesting case.
        all_ratios = list(available.values())
        spread = max(all_ratios) - min(all_ratios)

        # Case A: all three agree
        if spread < self.agree_band:
            center = sum(all_ratios) / 3
            avg_conf = sum(confidences.values()) / 3
            return TriangulationResult(
                cluster_center=center,
                cluster_members=list(Method),
                outliers=[],
                spread=spread,
                confidence=min(1.0, avg_conf),  # full confidence when methods agree
                verdict="agree",
                notes=[f"All three methods agree within ±{self.agree_band:.0%}."],
            )

        # Case B: find the tightest pair; check if third is the outlier
        best_pair: Optional[tuple[Method, Method]] = None
        best_dist = float("inf")
        for (m1, m2) in combinations(available.keys(), 2):
            d = abs(available[m1] - available[m2])
            if d < best_dist:
                best_dist = d
                best_pair = (m1, m2)

        assert best_pair is not None  # for the type checker
        third = next(m for m in available if m not in best_pair)
        pair_center = (available[best_pair[0]] + available[best_pair[1]]) / 2
        third_distance_from_pair = abs(available[third] - pair_center)

        if best_dist < self.pair_band and third_distance_from_pair > best_dist * 1.5:
            # Two-of-three pattern: pair forms the cluster, third is outlier
            avg_conf = (confidences[best_pair[0]] + confidences[best_pair[1]]) / 2
            return TriangulationResult(
                cluster_center=pair_center,
                cluster_members=list(best_pair),
                outliers=[third],
                spread=spread,
                confidence=avg_conf * 0.75,
                verdict="two_of_three",
                notes=[
                    f"{best_pair[0].value} and {best_pair[1].value} cluster within "
                    f"{best_dist:.0%}; {third.value} is the outlier."
                ],
            )

        # Case C: real disagreement
        return TriangulationResult(
            cluster_center=sum(all_ratios) / 3,    # median would also be defensible
            cluster_members=[],
            outliers=list(available.keys()),
            spread=spread,
            confidence=min(confidences.values()) * 0.3,
            verdict="disagree",
            notes=[
                f"All three methods disagree (spread {spread:.0%}). "
                "No clear cluster; verdict suppressed."
            ],
        )
