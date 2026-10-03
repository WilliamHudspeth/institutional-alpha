from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from iam.data.security import Security
from iam.ui.scene import Marker, Plane
from iam.ui.surface import SurfaceModel
from iam.valuation.reverse_dcf import _present_value_two_stage


@dataclass
class ValuationSurfacePoint:
    growth: float
    margin: float
    fair_value: float


class DCFValuationSurface(SurfaceModel):
    """Generates the data structure for the 3D Valuation Terrain."""

    title = "DCF Valuation Terrain"
    x_axis_name = "Growth"
    y_axis_name = "Margin"
    z_axis_name = "Fair Value"

    def __init__(
        self,
        security: Security,
        base_discount_rate: float | None = None,
        base_roe: float | None = None,
        n_years: int | None = None,
        terminal_growth: float | None = None,
        report=None,
    ):
        """Inputs come from the pipeline's intrinsic build-up when ``report`` is
        given; otherwise from the FCFE engine's documented model defaults.
        The base margin is the company's actual net margin; it is never
        assumed. Without it (or a price) the marker (or plane) is omitted.
        """
        from iam.valuation.fcfe_dcf import FCFEAssumptions

        defaults = FCFEAssumptions(high_growth=0.08)
        a: dict = {}
        if report is not None and getattr(report, "intrinsic", None) is not None:
            a = getattr(report.intrinsic, "assumptions", None) or {}

        self.security = security
        self.r = base_discount_rate or a.get("discount_rate") or defaults.discount_rate
        self.roe = base_roe or a.get("roe") or defaults.roe
        self.n = int(n_years or a.get("high_growth_years") or defaults.high_growth_years)
        self.g_term = terminal_growth or a.get("terminal_growth") or defaults.terminal_growth

        f = security.fundamentals
        # revenue_history is most-recent-first.
        self.revenue_ttm = f.revenue_history[0] if f.revenue_history else 0.0
        self.shares = f.shares_outstanding or 1.0

        q = security.qualitative or {}
        self.base_g = a.get("high_growth") or q.get("forecast_growth", defaults.high_growth)
        if f.net_income_ttm is not None and self.revenue_ttm > 0:
            self.base_m: float | None = f.net_income_ttm / self.revenue_ttm
        else:
            self.base_m = f.operating_margin
        self.market_price: float | None = security.market.price or None

        # Define the domain
        self.x_min = max(-0.20, self.base_g - 0.20)
        self.x_max = self.base_g + 0.30
        self.y_min = 0.01
        self.y_max = 0.50

        # Grid parameters
        self.grid_size = 15
        self.max_z_generated = 1.0
        self.base_fair_value = 0.0

    def generate_z_grid(self) -> list[list[float]]:
        """Generates a grid of Z values by varying Growth and Margin."""
        grid = []
        g_steps = np.linspace(self.x_min, self.x_max, self.grid_size)
        m_steps = np.linspace(self.y_min, self.y_max, self.grid_size)

        max_z = 0.0
        for m in m_steps:
            row = []
            for g in g_steps:
                base_ni = self.revenue_ttm * m
                base_ni_per_share = base_ni / self.shares

                pv = _present_value_two_stage(
                    base_ni=base_ni_per_share,
                    g_high=g,
                    n=self.n,
                    g_terminal=self.g_term,
                    r=self.r,
                    roe=self.roe,
                )
                # cap PV for rendering sanity
                if pv == float("inf") or pv < 0:
                    pv = 0
                max_z = max(max_z, pv)
                row.append(pv)
            grid.append(row)

        self.max_z_generated = max_z if max_z > 0 else 1.0
        self.z_max = self.max_z_generated

        # Calculate base fair value for the marker (needs the real margin)
        if self.base_m is None:
            return grid
        base_ni_per_share = (self.revenue_ttm * self.base_m) / self.shares
        self.base_fair_value = _present_value_two_stage(
            base_ni=base_ni_per_share,
            g_high=self.base_g,
            n=self.n,
            g_terminal=self.g_term,
            r=self.r,
            roe=self.roe,
        )
        if self.base_fair_value == float("inf") or self.base_fair_value < 0:
            self.base_fair_value = 0

        # Scale the grid down for rendering terminal proportions (Z mapping 0..5)
        # We will do scaling in the renderer/camera usually, but let's normalize here
        # Actually, SurfaceModel should return raw values, renderer handles scaling.
        return grid

    def get_planes(self) -> list[Plane]:
        if self.market_price is None:
            return []
        return [
            Plane(
                z=self.market_price,
                symbol="~",
                x_range=(self.x_min, self.x_max),
                y_range=(self.y_min, self.y_max),
            )
        ]

    def get_markers(self) -> list[Marker]:
        if self.base_m is None:
            return []
        return [
            Marker(
                x=self.base_g, y=self.base_m, z=self.base_fair_value, symbol="X", label="IAM Base"
            )
        ]
