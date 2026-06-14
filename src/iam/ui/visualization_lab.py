import sys
import os
from .scene import Scene, Camera
from .renderer import render_scene
from iam.valuation.sensitivity import DCFValuationSurface
from iam.valuation.expectations_surface import ExpectationSurface
from iam.valuation.topology import compute_gradients
from iam.engine.damodaran import DamodaranEngine
from iam.valuation.sotp import SOTP, Segment
from .sotp_tower import render_sotp_tower
import numpy as np

def mock_blk_segments():
    return [
        Segment("iShares",      revenue=5000, ebit=2000, unlevered_beta=0.60, tax_rate=0.21, growth_rate=0.04, fcfe=1500),
        Segment("Aladdin",      revenue=3000, ebit=1500, unlevered_beta=1.14, tax_rate=0.21, growth_rate=0.05, fcfe=1100),
        Segment("GIP",          revenue=2000, ebit=900,  unlevered_beta=0.95, tax_rate=0.21, growth_rate=0.03, fcfe=700),
        Segment("HPS",          revenue=1000, ebit=400,  unlevered_beta=1.05, tax_rate=0.21, growth_rate=0.04, fcfe=300),
    ]


def _getch():
    """Cross-platform single-character input."""
    try:
        import msvcrt
        ch = msvcrt.getch()
        if ch in (b'\x00', b'\xe0'):  # Arrow keys prefix
            ch = msvcrt.getch()
            if ch == b'H': return 'UP'
            elif ch == b'P': return 'DOWN'
            elif ch == b'M': return 'RIGHT'
            elif ch == b'K': return 'LEFT'
            return ''
        return ch.decode('utf-8', errors='ignore')
    except ImportError:
        import termios, tty
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == '\x1b':
                ch = sys.stdin.read(2)
                if ch == '[A': return 'UP'
                elif ch == '[B': return 'DOWN'
                elif ch == '[C': return 'RIGHT'
                elif ch == '[D': return 'LEFT'
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
        '1': ('DCF Valuation Terrain', [dcf_surface]),
        '2': ('Market Expectations Plane', [expectation_surface]),
        '3': ('Expectations vs Intrinsic Surface', [dcf_surface, expectation_surface]),
    }
    current_mode = '1'

    # Compute topology once
    z_grid = dcf_surface.generate_z_grid()
    g_steps = np.linspace(dcf_surface.x_min, dcf_surface.x_max, dcf_surface.grid_size).tolist()
    m_steps = np.linspace(dcf_surface.y_min, dcf_surface.y_max, dcf_surface.grid_size).tolist()
    topo = compute_gradients(z_grid, g_steps, m_steps)

    cursor_enabled = False
    cursor_x = dcf_surface.x_min + (dcf_surface.x_max - dcf_surface.x_min)/2
    cursor_y = dcf_surface.y_min + (dcf_surface.y_max - dcf_surface.y_min)/2

    while True:
        os.system('cls' if os.name == 'nt' else 'clear')
        
        mode_name, surfaces = modes.get(current_mode, modes['1'])
        scene.surfaces = surfaces
        
        scene.planes.clear()
        scene.markers.clear()
        
        if current_mode in ('1', '3'):
            scene.planes.extend(dcf_surface.get_planes())
            scene.markers.extend(dcf_surface.get_markers())
        
        output = render_scene(scene, width=100, height=35)
        print(output)
        
        print("\n" + "="*100)
        print(f" [F9] VISUALIZATION LAB | Mode: {current_mode} - {mode_name} | Yaw:{cam.yaw:.0f} Pitch:{cam.pitch:.0f} Zoom:{cam.zoom:.1f}")
        print(" Controls: [Arrows] Rotate | [+/-] Zoom | [R] Reset | [1-3] Change Mode | [6] SOTP Tower | [Esc] Exit")
        
        if current_mode == '1':
            print(f" Topology: Dominant Driver = {topo['dominant_driver']} | Fragility Score = {topo['fragility_score']:.2f} | Stability = {topo['stability_score']:.2f}")
        print("="*100)

        ch = _getch()
        if ch == chr(27):  # Esc
            break
        elif ch in ('1', '2', '3'):
            current_mode = ch
        elif ch == '6':
            # Use mocked BLK segments (from security.qualitative['segments'])
            segments = security.qualitative.get('segments', [])
            if not segments:
                segments = mock_blk_segments()   # fallback for testing
            # Compute cost of equity via Damodaran engine
            damodaran = DamodaranEngine()
            
            # Get D/E ratio
            if hasattr(security, "balance_sheet") and hasattr(security.balance_sheet, "debt_to_equity"):
                d_e = security.balance_sheet.debt_to_equity
            elif "current_de_ratio" in security.qualitative:
                d_e = security.qualitative["current_de_ratio"]
            else:
                book_debt = float(security.fundamentals.total_debt or 0.0)
                equity = float(security.market.market_cap or 1.0)
                d_e = book_debt / equity if equity > 0 else 0.5
                
            ke = damodaran.compute_cost_of_equity(segments, d_e)
            # Compute SOTP
            result = SOTP.compute(segments, ke)
            # Render tower
            os.system('cls' if os.name == 'nt' else 'clear')
            tower = render_sotp_tower(result.segments)
            print("=" * 100)
            print(" SUM OF THE PARTS (SOTP) TOWER ")
            print("=" * 100)
            print(tower)
            print("=" * 100)
            print(f"\nWeighted Unlevered Beta: {result.weighted_unlevered_beta:.2f}")
            print(f"Cost of Equity: {ke:.2%}")
            print("=" * 100)
            input("Press Enter to continue...")  # pause until keypress
        elif ch == 'UP':
            cam.pitch = min(90, cam.pitch + 10)
        elif ch == 'DOWN':
            cam.pitch = max(0, cam.pitch - 10)
        elif ch == 'RIGHT':
            cam.yaw += 15
        elif ch == 'LEFT':
            cam.yaw -= 15
        elif ch == '+':
            cam.zoom *= 1.2
        elif ch == '-':
            cam.zoom /= 1.2
        elif ch.lower() == 'r':
            cam.reset()

def render_dcf_surface(security, width: int = 80, height: int = 25) -> str:
    """Non-interactive render for the static report."""
    dcf_surface = DCFValuationSurface(security)
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
        lines[1] = f"  Z: Fair Value | X: Growth ({dcf_surface.x_min:.0%} - {dcf_surface.x_max:.0%}) | Y: Margin ({dcf_surface.y_min:.0%} - {dcf_surface.y_max:.0%})".center(width)
        
    return "\n".join(lines)
