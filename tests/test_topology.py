import pytest

from iam.valuation.topology import compute_gradients


def test_dominant_driver_linear():
    # Surface where value = 2*growth + 3*margin
    xs = [0.0, 0.1, 0.2]
    ys = [0.0, 0.1, 0.2]
    z_grid = [[0.0, 0.2, 0.4], [0.3, 0.5, 0.7], [0.6, 0.8, 1.0]]
    result = compute_gradients(z_grid, xs, ys)
    assert result["dominant_driver"] == "Margin"  # gradient_y = 3, gradient_x = 2
    assert result["gradient_x_mean"] == pytest.approx(2.0)
    assert result["gradient_y_mean"] == pytest.approx(3.0)
    assert result["fragility_score"] == pytest.approx(0.0)  # linear => zero curvature
