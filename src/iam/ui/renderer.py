import math

from .scene import Scene

LAYER_CHARS = ["-", "+", "=", ":", "."]  # chars to distinguish layers


def _rotate(x: float, y: float, z: float, camera) -> tuple:
    """Apply yaw (Z rotation) and pitch (X rotation) to a 3D point."""
    # Yaw around Z
    rad_yaw = math.radians(camera.yaw)
    x1 = x * math.cos(rad_yaw) - y * math.sin(rad_yaw)
    y1 = x * math.sin(rad_yaw) + y * math.cos(rad_yaw)
    z1 = z

    # Pitch around X
    rad_pitch = math.radians(camera.pitch)
    y2 = y1 * math.cos(rad_pitch) - z1 * math.sin(rad_pitch)
    z2 = y1 * math.sin(rad_pitch) + z1 * math.cos(rad_pitch)

    return x1, y2, z2


def _project(point_3d, width, height, zoom):
    """Simple orthographic projection to screen coordinates."""
    x, y, z = point_3d
    # terminal characters are about 2x as tall as they are wide, stretch X
    x *= zoom * 2.0
    y *= zoom
    screen_x = int(width / 2 + x)
    screen_y = int(height / 2 - y)  # flip Y for terminal
    return screen_x, screen_y, z


def _draw_line(
    buffer: list[list[str]],
    z_buffer: list[list[float]],
    width: int,
    height: int,
    x0: int,
    y0: int,
    z0: float,
    x1: int,
    y1: int,
    z1: float,
    char: str,
):
    """Bresenham line drawing on the buffer with Z-buffer interpolation."""
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy

    dist = math.hypot(x1 - x0, y1 - y0)
    if dist == 0:
        if 0 <= x0 < width and 0 <= y0 < height:
            if z0 > z_buffer[y0][x0]:
                z_buffer[y0][x0] = z0
                buffer[y0][x0] = char
        return

    x, y = x0, y0
    while True:
        curr_dist = math.hypot(x - x0, y - y0)
        t = curr_dist / dist if dist > 0 else 0
        z = z0 + t * (z1 - z0)

        if 0 <= x < width and 0 <= y < height:
            if z > z_buffer[y][x]:
                z_buffer[y][x] = z
                buffer[y][x] = char

        if x == x1 and y == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x += sx
        if e2 < dx:
            err += dx
            y += sy


def render_scene(scene: Scene, width: int = 80, height: int = 30) -> str:
    buffer = [[" " for _ in range(width)] for _ in range(height)]
    z_buffer = [[-float("inf") for _ in range(width)] for _ in range(height)]
    cam = scene.camera

    # 1. Draw planes
    for plane in scene.planes:
        if plane.x_range and plane.y_range:
            xmin, xmax = plane.x_range
            ymin, ymax = plane.y_range
        elif scene.surfaces:
            xmin = min(s.x_min for s in scene.surfaces)
            xmax = max(s.x_max for s in scene.surfaces)
            ymin = min(s.y_min for s in scene.surfaces)
            ymax = max(s.y_max for s in scene.surfaces)
        else:
            xmin, xmax = -1.0, 1.0
            ymin, ymax = -1.0, 1.0

        p_char = plane.symbol
        # Draw a grid for the plane
        grid_size = 10
        for i in range(grid_size):
            y_curr = ymin + (ymax - ymin) * i / (grid_size - 1)
            p0 = _project(_rotate(xmin, y_curr, plane.z, cam), width, height, cam.zoom)
            p1 = _project(_rotate(xmax, y_curr, plane.z, cam), width, height, cam.zoom)
            _draw_line(
                buffer, z_buffer, width, height, p0[0], p0[1], p0[2], p1[0], p1[1], p1[2], p_char
            )

            x_curr = xmin + (xmax - xmin) * i / (grid_size - 1)
            p0 = _project(_rotate(x_curr, ymin, plane.z, cam), width, height, cam.zoom)
            p1 = _project(_rotate(x_curr, ymax, plane.z, cam), width, height, cam.zoom)
            _draw_line(
                buffer, z_buffer, width, height, p0[0], p0[1], p0[2], p1[0], p1[1], p1[2], p_char
            )

    # 2. Draw surfaces
    for idx, surface in enumerate(scene.surfaces):
        z_grid = surface.generate_z_grid()
        y_count = len(z_grid)
        if y_count == 0:
            continue
        x_count = len(z_grid[0])

        char_x = LAYER_CHARS[idx % len(LAYER_CHARS)]
        char_y = "|" if idx == 0 else char_x

        for yi in range(y_count):
            for xi in range(x_count):
                fx0 = surface.x_min + (surface.x_max - surface.x_min) * xi / (x_count - 1)
                fy0 = surface.y_min + (surface.y_max - surface.y_min) * yi / (y_count - 1)
                fz0 = z_grid[yi][xi]
                p0 = _project(_rotate(fx0, fy0, fz0, cam), width, height, cam.zoom)

                # Draw to right neighbor
                if xi < x_count - 1:
                    fx1 = surface.x_min + (surface.x_max - surface.x_min) * (xi + 1) / (x_count - 1)
                    fz1 = z_grid[yi][xi + 1]
                    p1 = _project(_rotate(fx1, fy0, fz1, cam), width, height, cam.zoom)
                    _draw_line(
                        buffer,
                        z_buffer,
                        width,
                        height,
                        p0[0],
                        p0[1],
                        p0[2],
                        p1[0],
                        p1[1],
                        p1[2],
                        char_x,
                    )

                # Draw to bottom neighbor
                if yi < y_count - 1:
                    fy1 = surface.y_min + (surface.y_max - surface.y_min) * (yi + 1) / (y_count - 1)
                    fz1 = z_grid[yi + 1][xi]
                    p1 = _project(_rotate(fx0, fy1, fz1, cam), width, height, cam.zoom)
                    _draw_line(
                        buffer,
                        z_buffer,
                        width,
                        height,
                        p0[0],
                        p0[1],
                        p0[2],
                        p1[0],
                        p1[1],
                        p1[2],
                        char_y,
                    )

                # Draw point marker
                if 0 <= p0[0] < width and 0 <= p0[1] < height and p0[2] >= z_buffer[p0[1]][p0[0]]:
                    # slightly pop points to ensure visibility of intersections
                    z_buffer[p0[1]][p0[0]] = p0[2] + 0.001
                    buffer[p0[1]][p0[0]] = "+" if idx == 0 else "*"

    # 3. Draw markers
    for marker in scene.markers:
        sx, sy, sz = _project(_rotate(marker.x, marker.y, marker.z, cam), width, height, cam.zoom)
        # Always draw markers on top, or pop them in Z
        if 0 <= sx < width and 0 <= sy < height:
            if sz + 1.0 > z_buffer[sy][sx]:
                buffer[sy][sx] = marker.symbol
                if marker.label:
                    len(marker.label)
                    for i, c in enumerate(marker.label):
                        lx = sx + 2 + i
                        if 0 <= lx < width:
                            buffer[sy][lx] = c
                            z_buffer[sy][lx] = sz + 1.0

    return "\n".join("".join(row) for row in buffer)
