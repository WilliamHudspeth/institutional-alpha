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
        base_discount_rate: float = 0.09,
        base_roe: float = 0.15,
        n_years: int = 10,
        terminal_growth: float = 0.025,
    ):
        self.security = security
        self.r = base_discount_rate
        self.roe = base_roe
        self.n = n_years
        self.g_term = terminal_growth

        f = security.fundamentals
        self.revenue_ttm = f.revenue_history[-1] if f.revenue_history else 0.0
        self.shares = f.shares_outstanding or 1.0

        # If no revenue history, fallback to a base NI approach
        if self.revenue_ttm <= 0:
            pass
        # Retrieve base expectations if possible
        q = security.qualitative or {}
        self.base_g = q.get("forecast_growth", 0.08)
        self.base_m = 0.20  # Base margin
        self.market_price = security.market.price if security.market.price else 100.0

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

        # Calculate base fair value for the marker
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
        return [
            Plane(
                z=self.market_price,
                symbol="~",
                x_range=(self.x_min, self.x_max),
                y_range=(self.y_min, self.y_max),
            )
        ]

    def get_markers(self) -> list[Marker]:
        return [
            Marker(
                x=self.base_g, y=self.base_m, z=self.base_fair_value, symbol="X", label="IAM Base"
            )
        ]
