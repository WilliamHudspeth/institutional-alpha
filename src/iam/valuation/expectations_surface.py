from iam.data.security import Security
from iam.ui.surface import SurfaceModel


class ExpectationSurface(SurfaceModel):
    """Generates the data structure for the Market Expectation Surface."""

    title = "Market Expectation Surface"
    x_axis_name = "Growth"
    y_axis_name = "Margin"
    z_axis_name = "Price"

    def __init__(self, security: Security):
        self.security = security
        self.market_price = security.market.price if security.market.price else 100.0

        q = security.qualitative or {}
        base_g = q.get("forecast_growth", 0.08)

        self.x_min = max(-0.20, base_g - 0.20)
        self.x_max = base_g + 0.30
        self.y_min = 0.01
        self.y_max = 0.50
        self.grid_size = 15

    def generate_z_grid(self) -> list[list[float]]:
        """Returns a flat grid at the market price representing the expectation plane."""
        grid = []
        for _ in range(self.grid_size):
            row = [self.market_price for _ in range(self.grid_size)]
            grid.append(row)
        return grid
