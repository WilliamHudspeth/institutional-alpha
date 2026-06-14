from typing import List

def compute_gradients(z_grid: List[List[float]], x_vals: List[float], y_vals: List[float]) -> dict:
    """Returns gradient_x, gradient_y, curvature, and derived metrics."""
    if len(z_grid) < 3 or len(z_grid[0]) < 3:
        return {
            'gradient_x_mean': 0.0,
            'gradient_y_mean': 0.0,
            'curvature_x_mean': 0.0,
            'curvature_y_mean': 0.0,
            'dominant_driver': 'None',
            'fragility_score': 0.0,
            'stability_score': 1.0,
            'cliff_locations': [],
            'ridge_locations': [],
        }

    dx = x_vals[1] - x_vals[0]
    dy = y_vals[1] - y_vals[0]

    grad_x = []
    grad_y = []
    curv_xx = []
    curv_yy = []
    
    for i in range(1, len(z_grid)-1):
        row_x = []
        row_y = []
        row_xx = []
        row_yy = []
        for j in range(1, len(z_grid[0])-1):
            dz_dx = (z_grid[i][j+1] - z_grid[i][j-1]) / (2*dx) if dx != 0 else 0
            dz_dy = (z_grid[i+1][j] - z_grid[i-1][j]) / (2*dy) if dy != 0 else 0
            d2z_dx2 = (z_grid[i][j+1] - 2*z_grid[i][j] + z_grid[i][j-1]) / (dx*dx) if dx != 0 else 0
            d2z_dy2 = (z_grid[i+1][j] - 2*z_grid[i][j] + z_grid[i-1][j]) / (dy*dy) if dy != 0 else 0
            
            row_x.append(dz_dx)
            row_y.append(dz_dy)
            row_xx.append(d2z_dx2)
            row_yy.append(d2z_dy2)
            
        grad_x.append(row_x)
        grad_y.append(row_y)
        curv_xx.append(row_xx)
        curv_yy.append(row_yy)

    avg_grad_x = sum(sum(row) for row in grad_x) / (len(grad_x)*len(grad_x[0]))
    avg_grad_y = sum(sum(row) for row in grad_y) / (len(grad_y)*len(grad_y[0]))
    avg_curv_x = sum(sum(row) for row in curv_xx) / (len(curv_xx)*len(curv_xx[0]))
    avg_curv_y = sum(sum(row) for row in curv_yy) / (len(curv_yy)*len(curv_yy[0]))

    dominant = 'Growth' if abs(avg_grad_x) > abs(avg_grad_y) else 'Margin'

    fragility = abs(avg_curv_x) + abs(avg_curv_y)
    stability = 1.0 / (1.0 + fragility)

    cliffs = []
    ridges = []
    for i in range(len(grad_x)):
        for j in range(len(grad_x[0])):
            mag = (grad_x[i][j]**2 + grad_y[i][j]**2)**0.5
            if mag > 2.0:
                if curv_xx[i][j] < -0.5:
                    cliffs.append((x_vals[j+1], y_vals[i+1]))
                elif curv_xx[i][j] > 0.5:
                    ridges.append((x_vals[j+1], y_vals[i+1]))

    return {
        'gradient_x_mean': avg_grad_x,
        'gradient_y_mean': avg_grad_y,
        'curvature_x_mean': avg_curv_x,
        'curvature_y_mean': avg_curv_y,
        'dominant_driver': dominant,
        'fragility_score': fragility,
        'stability_score': stability,
        'cliff_locations': cliffs,
        'ridge_locations': ridges,
    }
