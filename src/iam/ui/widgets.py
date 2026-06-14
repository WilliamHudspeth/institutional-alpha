"""Reusable terminal widget primitives for the Alpha Terminal TUI.

Self-contained: depends only on the stdlib so it can be imported from any
panel module without circular-import risk against ``alpha_terminal``.

Provides:
    * A small ANSI color palette with **theme** support (amber / green / cyan)
      and a monochrome fallback, driven by the settings ``color_mode`` / ``theme``.
    * String builders that return *plain* glyph strings (no embedded color) so
      the caller applies a single ``cv.put(..., style=...)`` color, matching the
      existing Canvas API.  Where two-tone output is needed the panel draws the
      segments itself.

All builders are pure and side-effect free.
"""

from __future__ import annotations

from dataclasses import dataclass

# ── Raw ANSI ───────────────────────────────────────────────────────────────
CSI = "\x1b["
RESET = CSI + "0m"
BOLD = CSI + "1m"
DIM = CSI + "2m"


def fg(n: int) -> str:
    """256-color foreground escape."""
    return f"{CSI}38;5;{n}m"


def bg(n: int) -> str:
    """256-color background escape."""
    return f"{CSI}48;5;{n}m"


# ── Theme system ─────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Theme:
    """A phosphor color theme.  ``accent`` is the primary highlight hue."""

    name: str
    accent: int  # primary chrome / borders
    highlight: int  # active row / selected (the "gold" slot)
    green: int
    red: int
    yellow: int
    dim: int
    white: int
    blue: int
    magenta: int
    teal: int


# Cyan is the historical default (matches the current C_ACCENT = 39 chrome).
THEME_CYAN = Theme("cyan", 39, 220, 82, 196, 226, 240, 255, 33, 135, 51)
# Amber: classic Bloomberg/old-CRT look — amber chrome, warmer accents.
THEME_AMBER = Theme("amber", 214, 220, 82, 196, 226, 240, 230, 208, 209, 222)
# Green: P1 phosphor / 80s terminal.
THEME_GREEN = Theme("green", 35, 47, 46, 196, 226, 238, 253, 35, 78, 49)

THEMES: dict[str, Theme] = {
    "cyan": THEME_CYAN,
    "amber": THEME_AMBER,
    "green": THEME_GREEN,
}

# Module-global active theme + mono flag.  Set once from settings at startup.
_THEME: Theme = THEME_CYAN
_MONO: bool = False
_UNICODE: bool = True
# Monospace cell pixel size — used to correct the ~2:1 character aspect so 3D
# surfaces are not vertically squashed.  Tune to your font; 8x16 is a common
# default (a square 800x800 px window is then ~100 cols x 50 rows).
_CELL_W: int = 8
_CELL_H: int = 16


def configure(
    theme: str = "cyan",
    color_mode: str = "auto",
    unicode_enabled: bool = True,
    cell_px: tuple[int, int] | None = None,
) -> None:
    """Apply display settings (call once from the terminal at startup)."""
    global _THEME, _MONO, _UNICODE, _CELL_W, _CELL_H
    _THEME = THEMES.get((theme or "cyan").lower(), THEME_CYAN)
    _MONO = color_mode == "mono"
    _UNICODE = bool(unicode_enabled)
    if cell_px:
        _CELL_W, _CELL_H = int(cell_px[0]) or 8, int(cell_px[1]) or 16


def cell_size() -> tuple[int, int]:
    """Current monospace cell size in pixels (width, height)."""
    return (_CELL_W, _CELL_H)


def force_window_size(
    width_px: int = 800,
    height_px: int = 800,
    cell_w: int | None = None,
    cell_h: int | None = None,
    *,
    emit: bool = True,
) -> tuple[int, int]:
    """Request a fixed ``width_px`` x ``height_px`` terminal window.

    Emits the xterm window-manipulation escapes (pixel resize ``CSI 4;h;w t`` and
    character-grid resize ``CSI 8;rows;cols t``) and returns the resulting
    ``(cols, rows)`` character grid for the given cell size.  Most modern
    emulators (xterm, iTerm2, kitty, Windows Terminal, GNOME/Konsole) honour at
    least one of these; those that don't simply ignore the sequence, so call it
    best-effort and fall back to the returned grid for canvas sizing.

    ``cell_w`` / ``cell_h`` default to the live module globals (set by
    :func:`configure`) when omitted — they are resolved in the body rather than
    captured as default-argument values at import time.
    """
    import sys

    global _CELL_W, _CELL_H
    _CELL_W = int(cell_w) if cell_w else _CELL_W
    _CELL_H = int(cell_h) if cell_h else _CELL_H
    cols = max(40, width_px // _CELL_W)
    rows = max(20, height_px // _CELL_H)
    if emit and sys.stdout.isatty():
        # pixel resize, then lock the text grid
        sys.stdout.write(f"{CSI}4;{height_px};{width_px}t")
        sys.stdout.write(f"{CSI}8;{rows};{cols}t")
        sys.stdout.flush()
    return (cols, rows)


def theme() -> Theme:
    return _THEME


def _c(n: int) -> str:
    """Color escape honoring the mono toggle."""
    return "" if _MONO else fg(n)


# Convenience accessors (re-evaluated each call so a live theme switch applies).
def C_ACCENT() -> str:
    return _c(_THEME.accent)


def C_GOLD() -> str:
    return _c(_THEME.highlight)


def C_GREEN() -> str:
    return _c(_THEME.green)


def C_RED() -> str:
    return _c(_THEME.red)


def C_YELLOW() -> str:
    return _c(_THEME.yellow)


def C_DIM() -> str:
    return _c(_THEME.dim)


def C_WHITE() -> str:
    return _c(_THEME.white)


def C_BLUE() -> str:
    return _c(_THEME.blue)


def C_MAGENTA() -> str:
    return _c(_THEME.magenta)


def C_TEAL() -> str:
    return _c(_THEME.teal)


# ── Glyph sets (Unicode with ASCII fallback) ────────────────────────────────
_BLOCKS_U = "▁▂▃▄▅▆▇█"
_BLOCKS_A = ".:-=+*#@"
_SHADE_U = " ░▒▓█"
_SHADE_A = " .:#@"


def _blocks() -> str:
    return _BLOCKS_U if _UNICODE else _BLOCKS_A


def up_arrow() -> str:
    return "▲" if _UNICODE else "^"


def down_arrow() -> str:
    return "▼" if _UNICODE else "v"


def flat_arrow() -> str:
    return "►" if _UNICODE else ">"


# ── Color selectors ──────────────────────────────────────────────────────────
def value_color(val: float | None, threshold: float = 0.0) -> str:
    """Green if above threshold, red if below, dim if ~equal/None."""
    if val is None:
        return C_DIM()
    if val > threshold:
        return C_GREEN()
    if val < -threshold if threshold else val < 0:
        return C_RED()
    return C_YELLOW()


def rating_color(rating: str | None) -> str:
    r = (rating or "").upper()
    if "STRONG BUY" in r or r == "BUY":
        return C_GREEN()
    if "STRONG SELL" in r or r == "SELL":
        return C_RED()
    if "HOLD" in r or "NEUTRAL" in r:
        return C_YELLOW()
    return C_DIM()


def delta_color(delta: float | None) -> str:
    if delta is None:
        return C_DIM()
    return C_GREEN() if delta >= 0 else C_RED()


# ── Sparklines & trends ──────────────────────────────────────────────────────
def spark_line(history: list[float], width: int) -> str:
    """Render a list of values as a block-glyph sparkline of length ``width``."""
    blocks = _blocks()
    if not history or width <= 0:
        return " " * max(0, width)
    # Resample to width by simple bucketing.
    n = len(history)
    if n > width:
        step = n / width
        sampled = [history[int(i * step)] for i in range(width)]
    else:
        sampled = list(history)
    lo, hi = min(sampled), max(sampled)
    rng = (hi - lo) or 1.0
    out = []
    for v in sampled:
        idx = int((v - lo) / rng * (len(blocks) - 1))
        out.append(blocks[max(0, min(len(blocks) - 1, idx))])
    s = "".join(out)
    return s.ljust(width)[:width]


def spark_trend(history: list[float]) -> str:
    """Single arrow summarizing the net direction of a series."""
    if not history or len(history) < 2:
        return "─" if _UNICODE else "-"
    delta = history[-1] - history[0]
    base = abs(history[0]) or 1.0
    pct = delta / base
    if pct > 0.02:
        return up_arrow()
    if pct < -0.02:
        return down_arrow()
    return "─" if _UNICODE else "="


# ── Bars / meters ────────────────────────────────────────────────────────────
def hbar(frac: float, width: int, *, fill: str | None = None, empty: str = "·") -> str:
    """Horizontal bar.  ``frac`` in [0, 1].  Returns a ``width``-char string."""
    fill = fill or ("█" if _UNICODE else "#")
    empty = empty if _UNICODE else "."
    frac = max(0.0, min(1.0, frac))
    n = int(round(frac * width))
    return fill * n + empty * (width - n)


def meter(val: float | None, lo: float = -1.0, hi: float = 1.0, width: int = 18) -> str:
    """Centered meter for a signed score.  Marks the position of ``val``."""
    cells = ["·" if _UNICODE else "."] * width
    if val is None:
        return "".join(cells)
    frac = (val - lo) / ((hi - lo) or 1.0)
    pos = int(round(frac * (width - 1)))
    pos = max(0, min(width - 1, pos))
    mid = width // 2
    cells[mid] = "│" if _UNICODE else "|"
    cells[pos] = "█" if _UNICODE else "#"
    return "".join(cells)


def gauge(score: float, width: int = 20) -> str:
    """0..100 gauge as a filled bar."""
    return hbar(max(0.0, min(100.0, score)) / 100.0, width)


# ── Distribution (vertical histogram rows) ───────────────────────────────────
def distribution_row(weight: float, max_weight: float, width: int, glyph: str = "█") -> str:
    """One row of a horizontal distribution histogram."""
    if max_weight <= 0:
        return ""
    if not _UNICODE and glyph not in (".", "#", ":"):
        glyph = "#"
    n = int(round((weight / max_weight) * width))
    return glyph * max(0, min(width, n))


def yield_curve(points: list[tuple[str, float]], width: int = 28) -> str:
    """Compact yield-curve sparkline from (tenor, yield_pct) pairs."""
    if not points:
        return ""
    vals = [y for _, y in points]
    return spark_line(vals, width)


# ── Misc formatting ──────────────────────────────────────────────────────────
def fmt_pct(x: float | None, places: int = 1, signed: bool = True) -> str:
    if x is None:
        return "—" if _UNICODE else "-"
    sign = "+" if signed else ""
    return f"{x * 100:{sign}.{places}f}%"


def fmt_bps(x: float | None) -> str:
    """Format a fractional change as basis points (e.g. 0.0003 -> +3bp)."""
    if x is None:
        return "—" if _UNICODE else "-"
    return f"{x * 10000:+.0f}bp"


def fmt_num(x: float | None, places: int = 2) -> str:
    if x is None:
        return "—" if _UNICODE else "-"
    if abs(x) >= 1000:
        return f"{x:,.0f}"
    return f"{x:.{places}f}"


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))
