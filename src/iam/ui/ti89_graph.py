"""TI-89 style valuation map, drawn from a real value grid.

Both modes plot the same thing: value per share across growth (x) and
discount rate (y), from :func:`iam.valuation.value_grid.build_value_grid`,
with our base case and the market-implied point marked. If the grid could
not be built, callers show "n/a"; nothing here invents a surface.
"""

from __future__ import annotations

from iam.valuation.value_grid import ValueGrid, fair_value_frontier

try:
    import plotly.graph_objects as go
except ImportError:  # pragma: no cover - optional GUI dependency
    go = None

# Value relative to the reference (price, else our base value), cheapest first.
_BANDS: list[tuple[float, str]] = [
    (0.70, " "),
    (0.85, "."),
    (0.95, ":"),
    (1.05, "="),
    (1.15, "+"),
    (1.30, "*"),
    (float("inf"), "#"),
]

LEGEND = "value vs price:  ' '<70%  .<85%  :<95%  = ±5%  +<115%  *<130%  #>130%"


def _band(ratio: float) -> str:
    for upper, ch in _BANDS:
        if ratio < upper:
            return ch
    return "#"


def _nearest(axis: list[float], v: float) -> int:
    return min(range(len(axis)), key=lambda i: abs(axis[i] - v))


def render_ti89_map(grid: ValueGrid, cell_w: int = 6) -> list[str]:
    """ASCII heat-map rows. 'B' = our base case, 'M' = market-implied point."""
    ref = grid.price if grid.price else grid.base[2]
    bi, bj = _nearest(grid.rates, grid.base[1]), _nearest(grid.growths, grid.base[0])
    mi = mj = None
    if grid.market is not None:
        mi, mj = _nearest(grid.rates, grid.market[1]), _nearest(grid.growths, grid.market[0])

    frontier = fair_value_frontier(grid)
    frontier_cells = (
        {(_nearest(grid.rates, fr), _nearest(grid.growths, fg)) for fg, fr in frontier}
        if frontier is not None
        else set()
    )

    header = " r \\ g ".ljust(8) + "".join(f"{g * 100:>{cell_w}.1f}" for g in grid.growths)
    lines = [header]
    for i, r in enumerate(grid.rates):
        cells = []
        for j, v in enumerate(grid.values[i]):
            if (i, j) == (bi, bj):
                ch = "B"
            elif (i, j) == (mi, mj):
                ch = "M"
            elif (i, j) in frontier_cells:
                ch = "~"
            elif v is None:
                ch = "?"
            else:
                ch = _band(v / ref)
            cells.append(ch * (cell_w - 1) + " " if ch not in "BM" else f"[{ch}]".center(cell_w))
        lines.append(f"{r * 100:6.2f}% " + "".join(cells))
    if frontier is not None:
        lines.append("~ = V = price (fair-value frontier)")
    return lines


def ti89_figure(grid: ValueGrid):
    """Plotly 3D surface of the same grid, TI-89 monochrome styling."""
    if go is None:
        return None
    color = "#00008B"
    z = [[v if v is not None else None for v in row] for row in grid.values]
    x = [g * 100 for g in grid.growths]
    y = [r * 100 for r in grid.rates]
    fig = go.Figure(
        data=[
            go.Surface(
                z=z,
                x=x,
                y=y,
                colorscale=[[0, color], [1, color]],
                showscale=False,
                opacity=0.65,
                contours_z=dict(show=True, color=color, project_z=True),
                name="Value / share",
            ),
            go.Scatter3d(
                x=[grid.base[0] * 100],
                y=[grid.base[1] * 100],
                z=[grid.base[2]],
                mode="markers+text",
                text=["Our base"],
                marker=dict(size=6, color="#006400"),
                name="Our base case",
            ),
        ]
    )
    if grid.market is not None and grid.price:
        fig.add_trace(
            go.Scatter3d(
                x=[grid.market[0] * 100],
                y=[grid.market[1] * 100],
                z=[grid.price],
                mode="markers+text",
                text=["Market"],
                marker=dict(size=6, color="#8B0000"),
                name="Market-implied",
            )
        )
    frontier = fair_value_frontier(grid)
    if frontier is not None and grid.price:
        fig.add_trace(
            go.Scatter3d(
                x=[p[0] * 100 for p in frontier],
                y=[p[1] * 100 for p in frontier],
                z=[grid.price] * len(frontier),
                mode="lines+markers",
                line=dict(color="#FFD700", width=4),
                marker=dict(size=4, color="#FFD700"),
                name="V = price (fair-value frontier)",
            )
        )
    fig.update_layout(
        title="TI-89 Valuation Map: value per share by growth and discount rate",
        scene=dict(
            xaxis=dict(title="Growth %", showbackground=False, gridcolor="rgba(0,0,139,0.2)"),
            yaxis=dict(
                title="Discount rate %", showbackground=False, gridcolor="rgba(0,0,139,0.2)"
            ),
            zaxis=dict(title="Value / share", showbackground=False, gridcolor="rgba(0,0,139,0.2)"),
        ),
        paper_bgcolor="#8F9F8F",
        font=dict(color=color, family="Courier New, monospace"),
        margin=dict(l=0, r=0, b=0, t=30),
    )
    return fig
