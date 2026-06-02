"""Sentiment factor — analyst revisions, momentum, surprise persistence."""

from __future__ import annotations

import statistics

from iam.data.security import Security
from iam.factors.base import Factor, FactorContribution


class SentimentFactor(Factor):
    name = "sentiment"

    def compute(self, security: Security) -> FactorContribution:
        components: dict[str, float] = {}
        notes: list[str] = []
        confidence = 1.0
        m = security.market

        # Analyst revision breadth — already in [-1, 1] by convention
        if m.analyst_revisions_breadth_30d is not None:
            components["analyst_revisions"] = self.clamp(m.analyst_revisions_breadth_30d)
        else:
            confidence *= 0.8

        # 6m vol-adjusted momentum
        if len(m.price_history) >= 126:
            recent = m.price_history[0]
            six_m_ago = m.price_history[125]
            if six_m_ago > 0:
                ret = (recent / six_m_ago) - 1
                # daily returns -> annualized vol proxy
                daily_returns = [
                    (m.price_history[i] / m.price_history[i + 1]) - 1
                    for i in range(min(125, len(m.price_history) - 1))
                    if m.price_history[i + 1] > 0
                ]
                vol = statistics.pstdev(daily_returns) * (252**0.5) if daily_returns else 0.3
                vol_adj = ret / max(vol, 0.05)
                components["momentum_6m"] = self.clamp(vol_adj)
        else:
            confidence *= 0.85

        # Earnings surprise persistence
        if len(m.earnings_surprise_history) >= 4:
            avg_surprise = statistics.mean(m.earnings_surprise_history[:4])
            components["surprise_persistence"] = self.clamp(avg_surprise * 20)
        else:
            confidence *= 0.9

        if m.news_sentiment_delta is not None:
            components["news_sentiment"] = self.clamp(m.news_sentiment_delta)

        value = self.weighted_average(
            {
                "rev": (components.get("analyst_revisions"), 0.30),
                "mom": (components.get("momentum_6m"), 0.30),
                "surp": (components.get("surprise_persistence"), 0.20),
                "news": (components.get("news_sentiment"), 0.20),
            }
        )

        return FactorContribution(
            name=self.name,
            value=self.clamp(value),
            confidence=confidence,
            components=components,
            notes=notes,
        )
