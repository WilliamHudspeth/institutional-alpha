import math
import sys

import numpy as np

from iam.engine.damodaran import DamodaranEngine
from iam.ui.term import clear_screen
from iam.valuation.expectations_surface import ExpectationSurface
from iam.valuation.sensitivity import DCFValuationSurface
from iam.valuation.sotp import SOTP
from iam.valuation.topology import compute_gradients

from .renderer import render_scene
from .scene import Scene
from .sotp_tower import render_sotp_tower


def _finite(v: object) -> float | None:
    """Finite float or None (NaN/inf/non-numeric all mean 'no data')."""
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _debt_to_equity(security) -> float | None:
    """Real D/E from the security, or None. Never assumes leverage."""
    balance_sheet = getattr(security, "balance_sheet", None)
    d_e = _finite(getattr(balance_sheet, "debt_to_equity", None))
    if d_e is not None:
        return d_e
    d_e = _finite((security.qualitative or {}).get("current_de_ratio"))
    if d_e is not None:
        return d_e
    debt = _finite(security.fundamentals.total_debt)
    equity = _finite(security.market.market_cap)
    if debt is None or equity is None or equity <= 0:
        return None
    return debt / equity


def sotp_tower_report(security) -> str:
    """Text for the SOTP tower (mode 6), or an explicit insufficient-data message.

    Uses only segments supplied in ``security.qualitative["segments"]`` and a
    real debt/equity ratio; nothing is substituted when either is missing.
    """
    rule = "=" * 100
    header = [rule, " SUM OF THE PARTS (SOTP) TOWER ", rule]

    segments = (security.qualitative or {}).get("segments", [])
    if not segments:
        return "\n".join(
            header
            + [f"SOTP tower: n/a (insufficient data: no segment data for {security.ticker})", rule]
        )
    d_e = _debt_to_equity(security)
    if d_e is None:
        return "\n".join(
            header
            + [f"SOTP tower: n/a (insufficient data: no debt/equity for {security.ticker})", rule]
        )

    q = security.qualitative or {}
    if q.get("tax_rate") is not None:
        tax_rate, tax_source = float(q["tax_rate"]), "supplied"
    else:
        from iam.valuation.country_tax import company_marginal_tax

        tax_rate, tax_source = company_marginal_tax(security)
    ke = DamodaranEngine().compute_cost_of_equity(segments, d_e, tax_rate)
    result = SOTP.compute(segments, ke)
    return "\n".join(
        header
        + [
            render_sotp_tower(result.segments),
            rule,
            f"\nWeighted Unlevered Beta: {result.weighted_unlevered_beta:.2f}",
            f"Cost of Equity: {ke:.2%}",
            f"Marginal tax rate: {tax_rate:.2%} ({tax_source})",
            rule,
        ]
    )


def _getch():
    """Cross-platform single-character input."""
    try:
        import msvcrt

        ch = msvcrt.getch()
        if ch in (b"\x00", b"\xe0"):  # Arrow keys prefix
            ch = msvcrt.getch()
            if ch == b"H":
                return "UP"
            elif ch == b"P":
                return "DOWN"
            elif ch == b"M":
                return "RIGHT"
            elif ch == b"K":
                return "LEFT"
            return ""
        return ch.decode("utf-8", errors="ignore")
    except ImportError:
        import termios
        import tty

        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                ch = sys.stdin.read(2)
                if ch == "[A":
                    return "UP"
                elif ch == "[B":
                    return "DOWN"
                elif ch == "[C":
                    return "RIGHT"
                elif ch == "[D":
                    return "LEFT"
                return chr(27)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
        return ch


def run_visualization_lab(security):
    """Blocking interactive loop. Press Esc to exit."""
    dcf_surface = DCFValuationSurface(security)
    expectation_surface = ExpectationSurface(security)

    scene = Scene()
    cam = scene.camera

    modes = {
        "1": ("DCF Valuation Terrain", [dcf_surface]),
        "2": ("Market Expectations Plane", [expectation_surface]),
        "3": ("Expectations vs Intrinsic Surface", [dcf_surface, expectation_surface]),
    }
    current_mode = "1"

    # Compute topology once
    z_grid = dcf_surface.generate_z_grid()
    g_steps = np.linspace(dcf_surface.x_min, dcf_surface.x_max, dcf_surface.grid_size).tolist()
    m_steps = np.linspace(dcf_surface.y_min, dcf_surface.y_max, dcf_surface.grid_size).tolist()
    topo = compute_gradients(z_grid, g_steps, m_steps)

    dcf_surface.x_min + (dcf_surface.x_max - dcf_surface.x_min) / 2
    dcf_surface.y_min + (dcf_surface.y_max - dcf_surface.y_min) / 2

    while True:
        clear_screen()

        mode_name, surfaces = modes.get(current_mode, modes["1"])
        scene.surfaces = surfaces

        scene.planes.clear()
        scene.markers.clear()

        if current_mode in ("1", "3"):
            scene.planes.extend(dcf_surface.get_planes())
            scene.markers.extend(dcf_surface.get_markers())

        output = render_scene(scene, width=100, height=35)
        print(output)

        print("\n" + "=" * 100)
        print(
            f" [F9] VISUALIZATION LAB | Mode: {current_mode} - {mode_name} | Yaw:{cam.yaw:.0f} Pitch:{cam.pitch:.0f} Zoom:{cam.zoom:.1f}"
        )
        print(
            " Controls: [Arrows] Rotate | [+/-] Zoom | [R] Reset | [1-3] Change Mode | [6] SOTP Tower | [Esc] Exit"
        )

        if current_mode == "1":
            print(
                f" Topology: Dominant Driver = {topo['dominant_driver']} | Fragility Score = {topo['fragility_score']:.2f} | Stability = {topo['stability_score']:.2f}"
            )
        print("=" * 100)

        ch = _getch()
        if ch == chr(27):  # Esc
            break
        elif ch in ("1", "2", "3"):
            current_mode = ch
        elif ch == "6":
            clear_screen()
            print(sotp_tower_report(security))
            input("Press Enter to continue...")  # pause until keypress
        elif ch == "UP":
            cam.pitch = min(90, cam.pitch + 10)
        elif ch == "DOWN":
            cam.pitch = max(0, cam.pitch - 10)
        elif ch == "RIGHT":
            cam.yaw += 15
        elif ch == "LEFT":
            cam.yaw -= 15
        elif ch == "+":
            cam.zoom *= 1.2
        elif ch == "-":
            cam.zoom /= 1.2
        elif ch.lower() == "r":
            cam.reset()


def render_dcf_surface(security, width: int = 80, height: int = 25, report=None) -> str:
    """Non-interactive render for the static report."""
    dcf_surface = DCFValuationSurface(security, report=report)
    scene = Scene()
    scene.surfaces = [dcf_surface]
    scene.planes.extend(dcf_surface.get_planes())
    scene.markers.extend(dcf_surface.get_markers())
    scene.camera.zoom = 3.0
    scene.camera.yaw = 45.0
    scene.camera.pitch = 30.0

    output = render_scene(scene, width=width, height=height)

    # Overlay labels
    lines = output.split("\n")
    if len(lines) > 2:
        lines[0] = "  DCF VALUATION TERRAIN ".center(width, "=")
        lines[1] = (
            f"  Z: Fair Value | X: Growth ({dcf_surface.x_min:.0%} - {dcf_surface.x_max:.0%}) | Y: Margin ({dcf_surface.y_min:.0%} - {dcf_surface.y_max:.0%})".center(
                width
            )
        )

    return "\n".join(lines)
