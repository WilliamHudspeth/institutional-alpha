"""TI-89 style 3D valuation-surface engine for the Alpha Terminal.

Renders a rotatable ASCII surface — wireframe or shaded — over a value grid
defined on two axes (revenue growth × discount rate).  It is a *valuation
landscape*, not a math toy: the modes map directly to the platform's strongest
ideas.

Modes
-----
    DCF        Z = intrinsic value over (growth, discount rate)
    PLANE      DCF terrain with the current market price drawn as a flat plane,
               so the intersection is the "fair-value frontier"
    FRAGILITY  Z = local gradient magnitude  (steep = knife-edge, flat = robust)

Controls (the panel exposes these; the terminal routes keys to them)
    ← →   yaw      ↑ ↓   pitch      + -   zoom      [ ]   cycle mode
    W     toggle wireframe / shaded

Shaded rendering uses a half-space (edge-function) triangle rasterizer with a
per-pixel z-buffer and Lambert shading from the face normal — the technique
ported from ecumene/rust-sloth's CLI software rasterizer
(https://github.com/ecumene/rust-sloth), adapted to a character grid and to a
value-height colour ramp.  No numpy required.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field

from iam.ui import widgets as w

# Shade ramp (rust-sloth's default_shader ramp); leading space = empty cell.
_SHADE_U = " .:-=+*#%@"
_SHADE_A = " .:-=+*#"


# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class SurfaceModel:
    """A height field z[i][j] over normalized axes, with view state."""

    z: list[list[float]]
    x_label: str = "Growth"
    y_label: str = "Discount"
    z_label: str = "Value"
    yaw: float = 0.6
    pitch: float = 0.5
    zoom: float = 1.0
    plane_z: float | None = None  # market-price plane (normalized), optional

    _zmin: float = field(default=0.0, init=False)
    _zmax: float = field(default=1.0, init=False)

    def __post_init__(self) -> None:
        flat = [v for row in self.z for v in row]
        self._zmin = min(flat) if flat else 0.0
        self._zmax = max(flat) if flat else 1.0

    @property
    def rows(self) -> int:
        return len(self.z)

    @property
    def cols(self) -> int:
        return len(self.z[0]) if self.z else 0

    def nz(self, i: int, j: int) -> float:
        """Normalized height in [-1, 1]."""
        rng = (self._zmax - self._zmin) or 1.0
        return ((self.z[i][j] - self._zmin) / rng) * 2.0 - 1.0

    # ── view controls ─────────────────────────────────────────────────────
    def rotate(self, dyaw: float = 0.0, dpitch: float = 0.0) -> None:
        self.yaw += dyaw
        self.pitch = max(-1.4, min(1.4, self.pitch + dpitch))

    def scale(self, factor: float) -> None:
        self.zoom = max(0.4, min(3.0, self.zoom * factor))

    # ── projection ────────────────────────────────────────────────────────
    def project(self, nx: float, ny: float, nz: float) -> tuple[float, float, float]:
        """Map a normalized 3D point to rotated coords (x, y, depth).

        Orthographic: screen uses (x, y); ``depth`` is the view-axis coordinate
        used for the z-buffer and for the face-normal shade.  The returned triple
        is a valid rotated 3D point (zoom is applied later as a fit multiplier).
        """
        ca, sa = math.cos(self.yaw), math.sin(self.yaw)
        cb, sb = math.cos(self.pitch), math.sin(self.pitch)
        # yaw about the vertical (height) axis -> mixes the two ground axes
        x1 = nx * ca - ny * sa
        y1 = nx * sa + ny * ca
        z1 = nz
        # pitch about the screen-horizontal axis -> tilts height into view
        y2 = y1 * cb - z1 * sb
        z2 = y1 * sb + z1 * cb
        return (x1, y2, z2)


# ─────────────────────────────────────────────────────────────────────────────
def _shade_ramp() -> str:
    return _SHADE_U if w._UNICODE else _SHADE_A


def _default_shader(shade: float) -> str:
    """Map a Lambert shade in [0,1] to an ASCII density glyph (rust-sloth ramp)."""
    ramp = _shade_ramp()
    s = max(0.0, min(1.0, shade))
    idx = int(round(s * (len(ramp) - 1)))
    return ramp[max(1, idx)]  # never the leading space => solid fill


def _height_color(t: float) -> str:
    """Colour ramp by normalized height t in [0,1]: blue→teal→green→gold→red."""
    if t < 0.2:
        return w.C_BLUE()
    if t < 0.4:
        return w.C_TEAL()
    if t < 0.6:
        return w.C_GREEN()
    if t < 0.8:
        return w.C_GOLD()
    return w.C_RED()


def _orient(ax, ay, bx, by, cx, cy) -> float:
    """Edge function / 2x signed area of triangle (a,b,c)."""
    return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)


def render_surface(
    cv, model: SurfaceModel, r0: int, r1: int, c0: int, c1: int, wireframe: bool = False
) -> None:
    """Rasterize ``model`` into the panel rect.

    The surface is **auto-fitted** to the panel and **aspect-corrected**: points
    are scaled uniformly in pixels (using the configured monospace cell size) and
    only then converted to character cells, so the surface never looks squashed
    regardless of resolution.  ``model.zoom`` multiplies the fitted scale.

    Shaded mode triangulates the height field and fills each triangle with a
    half-space rasterizer + z-buffer (ported from rust-sloth).  Wireframe mode
    draws the projected grid edges.
    """
    height = r1 - r0
    width = c1 - c0
    if height < 4 or width < 8 or model.rows < 2:
        return

    rows, cols = model.rows, model.cols
    cw, chh = w.cell_size()  # pixels per character cell (e.g. 8 x 16)

    # 1) Project every vertex to rotated scene coords (sx, sy, depth) + keep 3D.
    raw = [[(0.0, 0.0, 0.0) for _ in range(cols)] for _ in range(rows)]
    minx = miny = 1e9
    maxx = maxy = -1e9
    for i in range(rows):
        for j in range(cols):
            nx = (j / (cols - 1)) * 2 - 1
            ny = (i / (rows - 1)) * 2 - 1
            nz = model.nz(i, j) * 0.8
            sx, sy, depth = model.project(nx, ny, nz)
            raw[i][j] = (sx, sy, depth)
            minx, maxx = min(minx, sx), max(maxx, sx)
            miny, maxy = min(miny, sy), max(maxy, sy)

    # 2) Auto-fit: scale uniformly in PIXELS, then divide by cell size -> cells.
    span_x = max(maxx - minx, 1e-6)
    span_y = max(maxy - miny, 1e-6)
    avail_w_px = (width - 1) * cw
    avail_h_px = (height - 1) * chh
    margin = 0.88
    scale_px = min(avail_w_px / span_x, avail_h_px / span_y) * margin * model.zoom
    mid_x = (minx + maxx) / 2.0
    mid_y = (miny + maxy) / 2.0
    ctr_col = (width - 1) / 2.0
    ctr_row = (height - 1) / 2.0

    def to_cell(sx: float, sy: float) -> tuple[float, float]:
        col = ctr_col + (sx - mid_x) * scale_px / cw
        row = ctr_row - (sy - mid_y) * scale_px / chh
        return (col, row)

    # 3) Screen-space vertices (fx, fy in cells, depth, rotated-3D for normals).
    proj = [[(0.0, 0.0, 0.0, (0.0, 0.0, 0.0)) for _ in range(cols)] for _ in range(rows)]
    for i in range(rows):
        for j in range(cols):
            sx, sy, depth = raw[i][j]
            fx, fy = to_cell(sx, sy)
            proj[i][j] = (fx, fy, depth, (sx, sy, depth))

    # Screen buffers.
    NEG = -1e9
    zbuf = [[NEG] * width for _ in range(height)]
    cbuf: list[list[tuple[str, str]]] = [[(" ", "")] * width for _ in range(height)]

    def put_buf(px: int, py: int, depth: float, ch: str, col: str) -> None:
        if 0 <= py < height and 0 <= px < width and depth > zbuf[py][px]:
            zbuf[py][px] = depth
            cbuf[py][px] = (ch, col)

    if wireframe:
        glyph = "·" if w._UNICODE else "+"

        def line(p, q, col):
            (x0, y0, d0, _), (x1_, y1_, d1, _) = p, q
            steps = max(2, int(max(abs(x1_ - x0), abs(y1_ - y0))))
            for s in range(steps + 1):
                t = s / steps
                put_buf(
                    int(round(x0 + (x1_ - x0) * t)),
                    int(round(y0 + (y1_ - y0) * t)),
                    d0 + (d1 - d0) * t,
                    glyph,
                    col,
                )

        for i in range(rows):
            for j in range(cols):
                col = _height_color((model.nz(i, j) + 1) / 2)
                if j + 1 < cols:
                    line(proj[i][j], proj[i][j + 1], col)
                if i + 1 < rows:
                    line(proj[i][j], proj[i + 1][j], col)
    else:
        # Shaded: two triangles per grid quad, edge-function rasterized.
        def rasterize(a, b, c, na, nb, nc):
            ax, ay, ad, a3 = a
            bx, by, bd, b3 = b
            cx, cy, cd, c3 = c
            area = _orient(ax, ay, bx, by, cx, cy)
            if abs(area) < 1e-6:
                return
            inv = 1.0 / area
            # Face normal from the rotated 3D triangle -> Lambert toward viewer.
            e1 = (b3[0] - a3[0], b3[1] - a3[1], b3[2] - a3[2])
            e2 = (c3[0] - a3[0], c3[1] - a3[1], c3[2] - a3[2])
            nzc = e1[0] * e2[1] - e1[1] * e2[0]
            nx_ = e1[1] * e2[2] - e1[2] * e2[1]
            ny_ = e1[2] * e2[0] - e1[0] * e2[2]
            norm = math.sqrt(nx_ * nx_ + ny_ * ny_ + nzc * nzc) or 1.0
            shade = abs(nzc / norm) * 0.8 + 0.2  # ambient floor
            ch = _default_shader(shade)
            # Colour by mean height of the tri's vertices.
            col = _height_color(max(0.0, min(1.0, (na + nb + nc) / 6 + 0.5)))
            minx_ = max(0, int(math.floor(min(ax, bx, cx))))
            maxx_ = min(width - 1, int(math.ceil(max(ax, bx, cx))))
            miny_ = max(0, int(math.floor(min(ay, by, cy))))
            maxy_ = min(height - 1, int(math.ceil(max(ay, by, cy))))
            for py in range(miny_, maxy_ + 1):
                for px in range(minx_, maxx_ + 1):
                    w0 = _orient(bx, by, cx, cy, px + 0.5, py + 0.5)
                    w1 = _orient(cx, cy, ax, ay, px + 0.5, py + 0.5)
                    w2 = _orient(ax, ay, bx, by, px + 0.5, py + 0.5)
                    inside = (w0 >= 0 and w1 >= 0 and w2 >= 0) or (w0 <= 0 and w1 <= 0 and w2 <= 0)
                    if not inside:
                        continue
                    l0, l1, l2 = w0 * inv, w1 * inv, w2 * inv
                    depth = l0 * ad + l1 * bd + l2 * cd
                    put_buf(px, py, depth, ch, col)

        for i in range(rows - 1):
            for j in range(cols - 1):
                p00, p01 = proj[i][j], proj[i][j + 1]
                p10, p11 = proj[i + 1][j], proj[i + 1][j + 1]
                n00, n01 = model.nz(i, j), model.nz(i, j + 1)
                n10, n11 = model.nz(i + 1, j), model.nz(i + 1, j + 1)
                rasterize(p00, p01, p10, n00, n01, n10)
                rasterize(p01, p11, p10, n01, n11, n10)

    # market-price plane overlay (drawn into the same z-buffer)
    if model.plane_z is not None:
        pz = max(-1.0, min(1.0, model.plane_z)) * 0.8
        glyph = "─" if w._UNICODE else "-"
        n = max(rows, cols)
        for a in range(n):
            for b in range(n):
                nx = (a / (n - 1)) * 2 - 1
                ny = (b / (n - 1)) * 2 - 1
                sx, sy, depth = model.project(nx, ny, pz)
                px, py = to_cell(sx, sy)
                put_buf(int(round(px)), int(round(py)), depth + 0.01, glyph, w.C_WHITE())

    # blit
    for ry in range(height):
        for cx in range(width):
            ch, col = cbuf[ry][cx]
            if ch != " ":
                cv.put(r0 + ry, c0 + cx, ch, col)


# ─────────────────────────────────────────────────────────────────────────────
# Grid builders
def saddle_demo_grid(n: int = 16) -> list[list[float]]:
    g = []
    for i in range(n):
        row = []
        for j in range(n):
            x = (j / (n - 1)) * 2 - 1
            y = (i / (n - 1)) * 2 - 1
            row.append(x * x - y * y)  # classic saddle
        g.append(row)
    return g


def dcf_terrain_grid(
    base_value: float, growth: float, discount: float, n: int = 16
) -> list[list[float]]:
    """Synthetic-but-plausible DCF value surface over growth × discount.

    Value rises with growth, falls steeply as discount approaches growth
    (Gordon-style sensitivity).  Anchored on the security's own numbers when
    available; replace with the engine's ``DCFValuationSurface`` grid for the
    real thing (see INTEGRATION_GUIDE Phase 5/6).
    """
    g = []
    g_lo, g_hi = max(-0.02, growth - 0.08), growth + 0.08
    d_lo, d_hi = max(0.04, discount - 0.05), discount + 0.05
    for i in range(n):
        d = d_lo + (d_hi - d_lo) * i / (n - 1)
        row = []
        for j in range(n):
            gr = g_lo + (g_hi - g_lo) * j / (n - 1)
            spread = max(0.005, d - gr)  # Gordon growth denominator
            val = base_value * (1.0 + gr) / spread
            row.append(val)
        g.append(row)
    return g


def fragility_grid(dcf_grid: list[list[float]]) -> list[list[float]]:
    """Gradient-magnitude surface from a value grid: steep = fragile."""
    n = len(dcf_grid)
    m = len(dcf_grid[0]) if n else 0
    out = [[0.0] * m for _ in range(n)]
    for i in range(n):
        for j in range(m):
            dx = abs(dcf_grid[i][min(j + 1, m - 1)] - dcf_grid[i][max(j - 1, 0)])
            dy = abs(dcf_grid[min(i + 1, n - 1)][j] - dcf_grid[max(i - 1, 0)][j])
            out[i][j] = math.hypot(dx, dy)
    return out


# ─────────────────────────────────────────────────────────────────────────────
class TerrainPanel:
    title = "VALUATION TERRAIN"

    MODES = ["DCF", "PLANE", "FRAGILITY"]

    def __init__(self, grid_provider: Callable | None = None) -> None:
        self._mode_idx = 0
        self._wire = False
        self._model: SurfaceModel | None = None
        self._grid_provider = grid_provider
        self._last_ticker: str | None = None

    # ── controls (terminal routes keys here) ──────────────────────────────
    def rotate(self, dyaw=0.0, dpitch=0.0):
        if self._model:
            self._model.rotate(dyaw, dpitch)

    def zoom(self, factor):
        if self._model:
            self._model.scale(factor)

    def cycle_mode(self, d=1):
        self._mode_idx = (self._mode_idx + d) % len(self.MODES)
        self._model = None  # force rebuild

    def toggle_wireframe(self):
        self._wire = not self._wire

    def reset_view(self):
        if self._model:
            self._model.yaw, self._model.pitch, self._model.zoom = 0.6, 0.5, 1.0

    # ── build the surface for the current security + mode ──────────────────
    def _build(self, sec):
        mode = self.MODES[self._mode_idx]
        if self._grid_provider:
            spec = self._grid_provider(sec, mode)
            if spec:
                z, xl, yl, zl, plane = spec
                self._model = SurfaceModel(z, xl, yl, zl, plane_z=plane)
                return
        # fallback: build from sec anchors or demo
        price = getattr(sec, "price", None) if sec else None
        bf = getattr(getattr(sec, "pipeline_result", None), "battlefield", None) if sec else None
        growth = getattr(bf, "intrinsic_growth", 0.10) if bf else 0.10
        if price:
            dcf = dcf_terrain_grid(price, growth, 0.09)
        else:
            dcf = saddle_demo_grid()
        plane = None
        if mode == "DCF":
            z, zl = dcf, "Intrinsic Value"
        elif mode == "PLANE":
            z, zl = dcf, "Value vs Price"
            if price:
                flat = [v for row in dcf for v in row]
                lo, hi = min(flat), max(flat)
                plane = ((price - lo) / ((hi - lo) or 1.0)) * 2 - 1
        else:  # FRAGILITY
            z, zl = fragility_grid(dcf), "Gradient Magnitude"
        self._model = SurfaceModel(z, "Growth", "Discount", zl, plane_z=plane)

    def render(self, cv, r0, r1, c0, c1, sec=None, system_state=None, ticks=0) -> None:
        ticker = getattr(sec, "ticker", None) if sec else None
        if self._model is None or ticker != self._last_ticker:
            self._build(sec)
            self._last_ticker = ticker

        mode = self.MODES[self._mode_idx]
        style = "WIRE" if self._wire else "SHADED"
        cv.put(r0, c0 + 1, f"MODE: {mode}", w.C_ACCENT() + w.BOLD)
        cv.put(r0, c0 + 20, f"[{style}]", w.C_GOLD())
        if self._model:
            cv.put(r0, c0 + 30, f"Z = {self._model.z_label}", w.C_DIM())
        cv.hline(r0 + 1, c0, c1, style=w.C_DIM())

        if self._model is None:
            cv.put(r0 + 2, c0 + 2, "No surface — open a security first.", w.C_DIM())
            return

        render_surface(cv, self._model, r0 + 2, r1 - 2, c0 + 1, c1 - 1, wireframe=self._wire)

        # axes legend + controls
        cv.hline(r1 - 2, c0, c1, style=w.C_DIM())
        cv.put(
            r1 - 1,
            c0 + 1,
            f"X:{self._model.x_label}  Y:{self._model.y_label}  "
            "[<>]yaw [^v]pitch [+/-]zoom []]mode [W]wire [R]reset",
            w.C_DIM(),
        )
        if mode == "PLANE" and self._model.plane_z is not None:
            cv.put(r1 - 1, c1 - 22, "-- market price plane", w.C_WHITE())


if __name__ == "__main__":  # ASCII smoke render

    class _C:
        def __init__(s):
            s.grid = {}

        def put(s, r, c, t, style=""):
            s.grid[(r, c)] = t

        def hline(s, *a, **k):
            pass

    cv = _C()
    w.configure("green", "mono", True)
    m = SurfaceModel(dcf_terrain_grid(180.0, 0.12, 0.09))
    m.yaw, m.pitch = 0.7, 0.6
    render_surface(cv, m, 0, 24, 0, 72, wireframe=False)
    for r in range(24):
        line = "".join(cv.grid.get((r, c), " ") for c in range(72))
        if line.strip():
            print(line)
