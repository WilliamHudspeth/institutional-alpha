"""Demonstrates attaching bull/bear theses to a Security and calling show_spread()."""

from iam.data.security import Assumption, Security, Thesis, show_spread

sec = Security(
    ticker="EXCO",
    name="Example Co.",
    theses=[
        Thesis(
            label="Bull",
            fair_value_low=160.0,
            fair_value_high=200.0,
            narrative="Margin expansion drives re-rating; TAM assumption holds.",
            assumptions=[
                Assumption("revenue_growth_5y", 0.18, source="user"),
                Assumption("terminal_margin", 0.30, rationale="Peer ceiling", source="user"),
            ],
        ),
        Thesis(
            label="Bear",
            fair_value_low=80.0,
            fair_value_high=110.0,
            narrative="Competition compresses margins; growth decelerates faster than consensus.",
            assumptions=[
                Assumption("revenue_growth_5y", 0.08, source="user"),
                Assumption("terminal_margin", 0.15, rationale="Structural headwinds", source="user"),
            ],
        ),
    ],
)

print(show_spread(sec))
