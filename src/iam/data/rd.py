"""Capitalise research and development as an asset (Damodaran, *Investment Valuation* ch. 9).

Accounting expenses R&D, which understates both operating income and invested capital for
research-heavy firms and inflates their book ROIC. Treating each year's R&D as an asset
amortised straight-line over ``life`` years:

    research asset_t = sum_{k=0..life-1} R&D_{t-k} x (life - k) / life
    amortisation_t   = sum_{k=1..life}   R&D_{t-k} / life

operating income and reinvestment both rise by R&D_t - amortisation_t (R&D is already fully
deducted for tax, so no tax adjustment), and invested capital rises by the research asset.
"""

from __future__ import annotations

from collections.abc import Sequence

RD_LIFE_YEARS = 3


def capitalise_rd(
    rd_most_recent_first: Sequence[float], life: int = RD_LIFE_YEARS
) -> list[tuple[float, float]]:
    """(R&D - amortisation, research asset) for each fiscal year in the series.

    ``rd_most_recent_first`` is consecutive fiscal years (0 where none was reported). Years
    before the series start count as zero, which understates the asset of the earliest years.
    """
    rd = [float(v) for v in rd_most_recent_first]

    def at(i: int) -> float:
        return rd[i] if i < len(rd) else 0.0

    out: list[tuple[float, float]] = []
    for i in range(len(rd)):
        amortisation = sum(at(i + k) for k in range(1, life + 1)) / life
        asset = sum(at(i + k) * (life - k) / life for k in range(life))
        out.append((rd[i] - amortisation, asset))
    return out
