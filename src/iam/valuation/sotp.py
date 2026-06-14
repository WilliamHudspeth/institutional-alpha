from dataclasses import dataclass


@dataclass
class Segment:
    name: str
    revenue: float  # for weighting unlevered beta
    ebit: float
    unlevered_beta: float
    tax_rate: float
    growth_rate: float
    fcfe: float  # free cash flow to equity (current year)


@dataclass
class SOTPResult:
    segments: list[dict]  # each segment: name, ev, beta_contribution
    total_ev: float
    weighted_unlevered_beta: float


class SOTP:
    @staticmethod
    def compute(segments: list[Segment], cost_of_equity: float) -> SOTPResult:
        total_revenue = sum(s.revenue for s in segments)
        weighted_beta_u = (
            sum(s.revenue * s.unlevered_beta for s in segments) / total_revenue
            if total_revenue
            else 0.0
        )

        segment_evs = []
        for s in segments:
            if cost_of_equity <= s.growth_rate:
                ev = float("inf")  # or handle gracefully
            else:
                ev = s.fcfe * (1 + s.growth_rate) / (cost_of_equity - s.growth_rate)
            segment_evs.append(
                {
                    "name": s.name,
                    "ev": ev,
                    "beta_contribution": (s.revenue * s.unlevered_beta / total_revenue)
                    if total_revenue
                    else 0.0,
                }
            )

        total_ev = sum(item["ev"] for item in segment_evs)
        return SOTPResult(
            segments=segment_evs, total_ev=total_ev, weighted_unlevered_beta=weighted_beta_u
        )
