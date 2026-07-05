import numpy as np

try:
    import plotly.graph_objects as go
except ImportError:
    go = None

def generate_ti89_3d_wireframe(intrinsic: float, relative: float, expectations: float, mode: str = "tui"):
    """
    Generate a 3D visualization of the three valuation pillars.
    If mode == "tui", returns an ASCII/ANSI wireframe projection.
    If mode == "gui", returns a Plotly Figure (monochrome wireframe like TI-89).
    """
    if mode == "tui":
        # ASCII art representation of a 3D surface
        art = [
            "      .      +       .      .   .   .",
            "  .       .      .      .       .    ",
            "    .  /---------------------\ .  .  ",
            " .    /  Valuation Surface    \      ",
            "     /    Intrinsic: {:+.1f}%    \    ".format(intrinsic * 100),
            "    /     Relative: {:+.1f}%     \   ".format(relative * 100),
            "   /      Expected: {:+.1f}%     \  ".format(expectations * 100),
            "  /_____________________________\ .  ",
            "  | \  .                     .  |    ",
            "  |  \      _/\_                | .  ",
            "  |   \   _/    \_     _/\      |    ",
            "  |    \_/        \___/   \_    |    ",
            "  |                         \   |    ",
            "  +-----------------------------+    "
        ]
        return "\n".join(art)
    
    elif mode == "gui":
        if go is None:
            return None
        # Create a mesh3d or scatter3d for Streamlit GUI
        # A simple saddle shape or terrain based on the three points
        u = np.linspace(-1, 1, 15)
        v = np.linspace(-1, 1, 15)
        u, v = np.meshgrid(u, v)
        
        # Simple polynomial surface using the three pillars as coefficients
        w = intrinsic * (u**2) + relative * (v**2) + expectations * u * v
        
        # TI-89 Monochrome green theme
        color = "#77FF77"
        
        fig = go.Figure(data=[go.Surface(z=w, x=u, y=v, 
                                       colorscale=[[0, color], [1, color]],
                                       showscale=False,
                                       opacity=0.7)])
        fig.update_traces(contours_z=dict(show=True, usecolormap=True, highlightcolor="limegreen", project_z=True))
        
        fig.update_layout(
            title="TI-89 Valuation Projection",
            scene=dict(
                xaxis=dict(showbackground=False, showgrid=True, gridcolor='rgba(0,255,0,0.2)'),
                yaxis=dict(showbackground=False, showgrid=True, gridcolor='rgba(0,255,0,0.2)'),
                zaxis=dict(showbackground=False, showgrid=True, gridcolor='rgba(0,255,0,0.2)')
            ),
            paper_bgcolor='#001100',
            plot_bgcolor='#001100',
            font=dict(color=color, family="Courier New, monospace"),
            margin=dict(l=0, r=0, b=0, t=30)
        )
        return fig
    else:
        raise ValueError(f"Unknown mode: {mode}")
