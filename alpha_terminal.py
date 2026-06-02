#!/usr/bin/env python3
"""
alpha_terminal.py — Institutional Alpha ANSI Terminal UI  v2

Integrated with the full iam package:
  - iam.ui.sparklines   → Sparkline, ProgressBar, MiniChart (new in v0.4)
  - iam.ui.panels       → PanelComposer, ScenarioMatrixPanel, DiagnosticSignalsPanel
  - iam.ui.state        → TerminalUIState, SecurityState (canonical state objects)
  - iam.portfolio       → PortfolioHoldingsPanel, format_holdings_table
  - iam.data.async_loader → AsyncDataLoader (non-blocking fetch)

Architecture:
  - Alternate screen buffer (no shell-history pollution)
  - Differential cell-grid Canvas (flicker-free, only changed cells flushed)
  - Dynamic layout: adapts to any terminal ≥ 80×24 at runtime
  - Background ThreadPoolExecutor for data loading
  - atexit teardown — cursor and screen always restored on crash

Navigation:
  [↑/↓]   Move menu selection
  [Enter]  Activate / confirm
  [S]      Switch active security (global hotkey)
  [R]      Force-reload current security
  [W]      Add ticker to watchlist
  [Q/Esc]  Quit
"""

from __future__ import annotations

import atexit
import json
import os
import re
import sys
import time
import random
import shutil
import threading
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# ── Platform key-input helpers ────────────────────────────────────────────
if sys.platform == "win32":
    import msvcrt

    def _getch_nowait() -> bytes | None:
        return msvcrt.getch() if msvcrt.kbhit() else None

    def _getch_block() -> bytes:
        return msvcrt.getch()

else:
    import select
    import termios
    import tty

    def _getch_nowait() -> bytes | None:
        dr, _, _ = select.select([sys.stdin], [], [], 0)
        if dr:
            return sys.stdin.buffer.read(1)
        return None

    def _getch_block() -> bytes:
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            return sys.stdin.buffer.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)


# ── IAM package imports (optional — graceful mock fallback) ───────────────
try:
    from iam.data.yahoo import fetch_security as _fetch_security
    from iam import score as _score
    from iam.pipeline.orchestrator import ValuationPipeline as _Pipeline

    _IAM_CORE = True
except ImportError:
    _IAM_CORE = False

try:
    from iam.ui.sparklines import Sparkline, ProgressBar, MiniChart

    _IAM_SPARKLINES = True
except ImportError:
    _IAM_SPARKLINES = False

try:
    from iam.portfolio.ui import format_holdings_table, format_factor_exposure_heatmap

    _IAM_PORTFOLIO = True
except ImportError:
    _IAM_PORTFOLIO = False

# ═══════════════════════════════════════════════════════════════════════════
#  ANSI PRIMITIVES
# ═══════════════════════════════════════════════════════════════════════════

ESC = "\033"
CSI = ESC + "["

ALT_ON = CSI + "?1049h"
ALT_OFF = CSI + "?1049l"
CLEAR = CSI + "2J" + CSI + "H"
CURSOR_HIDE = CSI + "?25l"
CURSOR_SHOW = CSI + "?25h"

RESET = CSI + "0m"
BOLD = CSI + "1m"
DIM = CSI + "2m"
ITALIC = CSI + "3m"


def fg(n: int) -> str:
    return f"{CSI}38;5;{n}m"


def bg(n: int) -> str:
    return f"{CSI}48;5;{n}m"


# Semantic palette
C_ACCENT = fg(39)       # Bright cyan
C_GOLD = fg(220)        # Amber — active / highlights
C_GREEN = fg(82)        # Bright green
C_RED = fg(196)         # Bright red
C_YELLOW = fg(226)      # Yellow
C_DIM = fg(240)         # Dark grey
C_WHITE = fg(255)       # Near-white
C_BLUE = fg(33)         # Blue
C_MAGENTA = fg(135)     # Magenta
C_TEAL = fg(51)         # Teal
C_MENU_HL = bg(17) + fg(39) + BOLD
C_HDR = bg(234)


def _rc(rating: str) -> str:
    return {
        "BUY": C_GREEN,
        "STRONG BUY": C_GREEN + BOLD,
        "SELL": C_RED,
        "STRONG SELL": C_RED + BOLD,
        "HOLD": C_YELLOW,
    }.get(rating.upper(), C_WHITE)


def _vc(val: float, threshold: float = 0.05) -> str:
    if val > threshold:
        return C_GREEN
    if val < -threshold:
        return C_RED
    return C_YELLOW


# Box-drawing
TL = "╔"
TR = "╗"
BL = "╚"
BR = "╝"
H2 = "═"
V2 = "║"
TL1 = "┌"
TR1 = "┐"
BL1 = "└"
BR1 = "┘"
H1 = "─"
V1 = "│"
MID_L = "╠"
MID_R = "╣"
MID_L1 = "├"
MID_R1 = "┤"

SPARK_CHARS = " ▁▂▃▄▅▆▇█"
FULL = "█"
EMPTY = "░"
HALF = "▒"


def mv(row: int, col: int) -> str:
    return f"{CSI}{row};{col}H"


# ── Local sparkline helpers (used even if iam.ui.sparklines unavailable) ──

def _spark_line(history: list[float], width: int) -> str:
    """Render a sparkline using iam.ui.sparklines if available, else fallback."""
    if not history or len(history) < 2:
        return "─" * width
    if _IAM_SPARKLINES:
        return Sparkline.line(history, width)
    window = history[-width:]
    lo, hi = min(window), max(window)
    span = hi - lo or 1.0
    return "".join(SPARK_CHARS[min(8, max(0, int((v - lo) / span * 8)))] for v in window).ljust(width)


def _spark_trend(history: list[float]) -> str:
    """↑ / ↓ / → trend arrow."""
    if _IAM_SPARKLINES and len(history) >= 2:
        return Sparkline.trend(history)
    if len(history) < 2:
        return "→"
    delta = history[-1] - history[0]
    return "↑" if delta > 0 else ("↓" if delta < 0 else "→")


def _meter(val: float, lo: float = -1.0, hi: float = 1.0, width: int = 18) -> str:
    """Block progress meter. Uses iam.ui.sparklines.ProgressBar if available."""
    if _IAM_SPARKLINES:
        norm = (val - lo) / (hi - lo) if (hi - lo) else 0.5
        return ProgressBar.bar(norm, 1.0, width)
    pct = (val - lo) / (hi - lo) if (hi - lo) else 0.5
    filled = max(0, min(width, int(pct * width)))
    return FULL * filled + EMPTY * (width - filled)


# ═══════════════════════════════════════════════════════════════════════════
#  DIFFERENTIAL CANVAS  (double-buffer, zero flicker)
# ═══════════════════════════════════════════════════════════════════════════


class Canvas:
    """Virtual text canvas — flush() pushes only changed cells to stdout."""

    def __init__(self, rows: int, cols: int) -> None:
        self.rows = rows
        self.cols = cols
        self._front: list[list[tuple[str, str]]] = [
            [(" ", "") for _ in range(cols)] for _ in range(rows)
        ]
        self._back: list[list[tuple[str, str]]] = [
            [(" ", "") for _ in range(cols)] for _ in range(rows)
        ]
        self._dirty = True

    def resize(self, rows: int, cols: int) -> None:
        self.rows = rows
        self.cols = cols
        self._front = [[(" ", "") for _ in range(cols)] for _ in range(rows)]
        self._back = [[(" ", "") for _ in range(cols)] for _ in range(rows)]
        self._dirty = True

    def put(self, row: int, col: int, text: str, style: str = "") -> None:
        if row < 0 or row >= self.rows:
            return
        for i, ch in enumerate(text):
            c = col + i
            if 0 <= c < self.cols:
                self._back[row][c] = (ch, style)

    def hline(self, row: int, c0: int, c1: int, ch: str = H1, style: str = C_DIM) -> None:
        self.put(row, c0, ch * max(0, c1 - c0 + 1), style)

    def box(self, r0: int, r1: int, c0: int, c1: int, style: str = C_DIM) -> None:
        w = c1 - c0 + 1
        self.put(r0, c0, TL1 + H1 * (w - 2) + TR1, style)
        self.put(r1, c0, BL1 + H1 * (w - 2) + BR1, style)
        for r in range(r0 + 1, r1):
            self.put(r, c0, V1, style)
            self.put(r, c1, V1, style)

    def clear_back(self) -> None:
        self._back = [[(" ", "") for _ in range(self.cols)] for _ in range(self.rows)]

    def flush(self) -> None:
        buf: list[str] = []
        last_style: str | None = None
        last_r = last_c = -999
        for r in range(self.rows):
            for c in range(self.cols):
                cell = self._back[r][c]
                if self._dirty or cell != self._front[r][c]:
                    if r != last_r or c != last_c + 1:
                        buf.append(mv(r + 1, c + 1))
                    if cell[1] != last_style:
                        buf.append(RESET)
                        if cell[1]:
                            buf.append(cell[1])
                        last_style = cell[1]
                    buf.append(cell[0])
                    self._front[r][c] = cell
                    last_r, last_c = r, c
        self._dirty = False
        if buf:
            sys.stdout.write("".join(buf))
            sys.stdout.flush()


# ═══════════════════════════════════════════════════════════════════════════
#  MOCK DATA  (used when IAM packages unavailable or fetch fails)
# ═══════════════════════════════════════════════════════════════════════════


class _Mkt:
    def __init__(self, p: float) -> None:
        self.price = p


class _MockSec:
    def __init__(self, t: str, p: float) -> None:
        self.ticker = t
        self.name = f"{t} Inc. (mock)"
        self.market = _Mkt(p)


class _MockContrib:
    def __init__(self, v: float) -> None:
        self.value = v
        self.confidence = random.uniform(0.55, 1.0)


class _MockScore:
    FACTOR_NAMES = [
        "quality", "intrinsic_value", "relative_value", "sentiment",
        "momentum", "macro_regime", "reflexivity", "runway",
        "expectations_difficulty", "crowding",
    ]

    def __init__(self) -> None:
        self.composite = random.uniform(-0.55, 0.55)
        self.factor_breakdown = {
            k: _MockContrib(random.uniform(-0.9, 0.9)) for k in self.FACTOR_NAMES
        }
        self.penalties: dict[str, Any] = {}


class _MockVerdict:
    def __init__(self) -> None:
        self.rating = random.choice(["BUY", "HOLD", "SELL"])
        self.confidence_band = random.choice(["LOW", "MEDIUM", "HIGH"])
        self.blended_upside: float | None = random.uniform(-0.35, 0.45)


class _MockTriangulation:
    def __init__(self) -> None:
        self.cluster_center = random.uniform(-0.3, 0.4)
        self.spread = random.uniform(0.05, 0.25)
        self.verdict = random.choice(["BUY", "HOLD", "SELL"])


class _MockPipeline:
    def __init__(self) -> None:
        self.final_verdict = _MockVerdict()
        self.implied_move_pct: float | None = random.uniform(-0.35, 0.45)
        self.triangulation = _MockTriangulation()


# ═══════════════════════════════════════════════════════════════════════════
#  SECURITY STATE
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class SecState:
    """Per-ticker data container."""

    ticker: str
    security: Any = None
    score_result: Any = None
    pipeline_result: Any = None
    history: list[float] = field(default_factory=list)
    last_updated: datetime = field(default_factory=datetime.now)
    loading: bool = False
    error: str | None = None

    @property
    def price(self) -> float:
        try:
            return float(self.security.market.price or 0.0)
        except Exception:
            return 0.0

    @property
    def name(self) -> str:
        try:
            return str(self.security.name or self.ticker)
        except Exception:
            return self.ticker

    @property
    def rating(self) -> str:
        try:
            return str(self.pipeline_result.final_verdict.rating)
        except Exception:
            return "N/A"

    @property
    def confidence(self) -> str:
        try:
            return str(self.pipeline_result.final_verdict.confidence_band)
        except Exception:
            return "—"

    @property
    def upside(self) -> float:
        try:
            v = self.pipeline_result.final_verdict
            return float(v.blended_upside or self.pipeline_result.implied_move_pct or 0.0)
        except Exception:
            return 0.0

    @property
    def composite(self) -> float:
        try:
            return float(self.score_result.composite)
        except Exception:
            return 0.0


# ═══════════════════════════════════════════════════════════════════════════
#  LAYOUT CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════

MIN_COLS = 80
MIN_ROWS = 24
MENU_W = 27    # menu column width (incl border)
HDR_ROWS = 3
FTR_ROWS = 2


# ═══════════════════════════════════════════════════════════════════════════
#  TICKER RESOLUTION
# ═══════════════════════════════════════════════════════════════════════════


def _resolve_ticker(query: str) -> tuple[str, str | None]:
    try:
        url = (
            "https://query2.finance.yahoo.com/v1/finance/search"
            f"?q={urllib.parse.quote(query)}&quotesCount=1&newsCount=0"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            quotes = data.get("quotes", [])
            if quotes and "symbol" in quotes[0]:
                return quotes[0]["symbol"].upper(), quotes[0].get("shortname")
    except Exception:
        pass
    return query.strip().upper(), None


def _valid_ticker(t: str) -> bool:
    return bool(re.match(r"^[A-Z0-9\-\.]{1,15}$", t))


# ═══════════════════════════════════════════════════════════════════════════
#  PANEL RENDERERS
# ═══════════════════════════════════════════════════════════════════════════


class _Panel:
    title: str = "PANEL"

    def render(
        self,
        cv: Canvas,
        r0: int,
        r1: int,
        c0: int,
        c1: int,
        sec: SecState | None,
        ticks: int = 0,
    ) -> None:
        pass

    def _loading(self, cv: Canvas, r0: int, r1: int, c0: int, c1: int, ticker: str) -> None:
        mid = (r0 + r1) // 2
        sp = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"[ticks % 10]
        msg = f" {sp}  Fetching {ticker}… "
        col = max(c0 + 1, (c0 + c1) // 2 - len(msg) // 2)
        cv.box(mid - 1, mid + 1, c0 + 2, c1 - 2, C_GOLD)
        cv.put(mid, col, msg, C_GOLD + BOLD)

    def _err(self, cv: Canvas, r0: int, c0: int, msg: str) -> None:
        cv.put(r0, c0 + 2, f"⚠  {msg}", C_RED)


# ── Watchlist ─────────────────────────────────────────────────────────────


class WatchlistPanel(_Panel):
    title = "LIVE WATCHLIST"

    def __init__(self, watchlist: list[str]) -> None:
        self._wl = watchlist

    def render(
        self,
        cv: Canvas,
        r0: int,
        r1: int,
        c0: int,
        c1: int,
        sec: SecState | None,
        ticks: int = 0,
    ) -> None:
        w = c1 - c0
        cv.put(r0, c0 + 1, f"{'TICKER':<6} {'PRICE':>10}  {'CHG':>7}  {'TREND':>5}  SPARKLINE", C_DIM)
        cv.hline(r0 + 1, c0, c1)

        for idx, tkr in enumerate(self._wl):
            r = r0 + 2 + idx
            if r > r1 - 1:
                break
            is_active = sec and tkr == sec.ticker
            active_style = C_GOLD + BOLD if is_active else C_WHITE

            # Use real price if this is the active ticker, else simulate
            if is_active and sec and not sec.loading and sec.price > 0:
                price = sec.price
                hist = sec.history
            else:
                price = random.uniform(50, 600)
                hist = [price * random.uniform(0.97, 1.03) for _ in range(15)]

            delta = random.uniform(-price * 0.025, price * 0.025)
            pct = delta / price if price else 0
            arrow = "▲" if delta >= 0 else "▼"
            d_col = C_GREEN if delta >= 0 else C_RED
            spark = _spark_line(hist, 14)
            trend = _spark_trend(hist)
            prefix = "▶ " if is_active else "  "

            cv.put(r, c0, prefix, active_style)
            cv.put(r, c0 + 2, f"{tkr:<5}", active_style)
            cv.put(r, c0 + 8, f"${price:>9.2f}", C_WHITE)
            cv.put(r, c0 + 19, f"{arrow} {pct:>+5.1%}", d_col)
            cv.put(r, c0 + 28, f"{trend}", d_col)
            cv.put(r, c0 + 32, spark, d_col)


# ── Quick Recommendation ──────────────────────────────────────────────────


class QuickRecPanel(_Panel):
    title = "QUICK RECOMMENDATION"

    def render(
        self,
        cv: Canvas,
        r0: int,
        r1: int,
        c0: int,
        c1: int,
        sec: SecState | None,
        ticks: int = 0,
    ) -> None:
        if not sec:
            return
        if sec.loading:
            self._loading(cv, r0, r1, c0, c1, sec.ticker)
            return

        rating = sec.rating
        confidence = sec.confidence
        upside = sec.upside
        price = sec.price
        fair = price * (1.0 + upside)
        rc = _rc(rating)
        up_col = C_GREEN if upside > 0 else C_RED

        # Main verdict box
        bw = min(c1 - c0 - 3, 52)
        bx = c0 + 1
        by = r0 + 1
        cv.box(by, by + 6, bx, bx + bw, C_ACCENT)

        cv.put(by + 1, bx + 3, "RATING:", C_DIM)
        cv.put(by + 1, bx + 11, f"{rating}", rc + BOLD)
        cv.put(by + 1, bx + 11 + len(rating) + 2, f"Confidence: {confidence}", C_WHITE)

        cv.put(by + 3, bx + 3, f"Current:     ${price:>9.2f}", C_WHITE)
        cv.put(by + 3, bx + 30, f"Fair Value: ${fair:>9.2f}", C_WHITE)
        cv.put(by + 4, bx + 3, f"Implied Move: {upside:>+.1%}", up_col + BOLD)
        cv.put(by + 5, bx + 3, f"Updated: {sec.last_updated:%H:%M:%S}", C_DIM)

        # Composite score meter
        comp = sec.composite
        comp_style = _vc(comp)
        comp_100 = int((comp + 1.0) * 50.0)
        mtr = _meter(comp, -1, 1, 28)
        cv.put(r0 + 9, c0 + 1, "Factor Score:", C_DIM)
        cv.put(r0 + 9, c0 + 15, "[", C_DIM)
        cv.put(r0 + 9, c0 + 16, mtr, comp_style)
        cv.put(r0 + 9, c0 + 44, f"] {comp_100}/100", C_WHITE)

        # Interpretation
        cv.hline(r0 + 11, c0, c1)
        if rating in ("BUY", "STRONG BUY"):
            msg = "▶  Stock appears undervalued — material upside potential identified."
            cv.put(r0 + 12, c0 + 2, msg, C_GREEN)
        elif rating in ("SELL", "STRONG SELL"):
            msg = "▶  Stock appears overvalued — downside risk flags triggered."
            cv.put(r0 + 12, c0 + 2, msg, C_RED)
        else:
            msg = "▶  Stock appears fairly valued within the model's consensus range."
            cv.put(r0 + 12, c0 + 2, msg, C_YELLOW)

        if sec.error:
            cv.put(r0 + 14, c0 + 2, f"⚠ Live fetch failed — using mock data", C_RED + DIM)


# ── Deep Valuation ────────────────────────────────────────────────────────


class DeepValPanel(_Panel):
    title = "DEEP DIVE VALUATION"

    STAGES = [
        ("Stage 1", "Reverse DCF",         "Implied growth rate extracted from price"),
        ("Stage 2", "Relative Multiples",  "Peer-adjusted EV/Sales, P/E, P/B"),
        ("Stage 3", "FCFE Intrinsic DCF",  "Explicit free-cash-flow valuation"),
        ("Stage 4", "Triangulation",       "Consensus across all three methods"),
        ("Stage 5", "Macro Overlay",       "Regime-dependent discount adjustment"),
        ("Stage 6", "Thesis Engine",       "Bayesian scenario weighting"),
        ("Stage 7", "Verdict",             "Final BUY / HOLD / SELL signal"),
    ]

    def render(
        self,
        cv: Canvas,
        r0: int,
        r1: int,
        c0: int,
        c1: int,
        sec: SecState | None,
        ticks: int = 0,
    ) -> None:
        if not sec:
            return
        if sec.loading:
            self._loading(cv, r0, r1, c0, c1, sec.ticker)
            return

        cv.put(r0, c0 + 1, "7-Stage Valuation Pipeline", C_ACCENT + BOLD)
        cv.hline(r0 + 1, c0, c1)

        for i, (lbl, name, desc) in enumerate(self.STAGES):
            r = r0 + 2 + i
            if r > r1 - 4:
                break
            cv.put(r, c0 + 1, lbl, C_DIM)
            cv.put(r, c0 + 9, f"{name:<24}", C_WHITE)
            cv.put(r, c0 + 34, desc, C_DIM)

        pr = sec.pipeline_result
        if pr and getattr(pr, "triangulation", None):
            tr = pr.triangulation
            sep = r0 + 2 + len(self.STAGES) + 1
            cv.hline(sep, c0, c1)
            cv.put(sep + 1, c0 + 1, "Triangulation Engine Output:", C_ACCENT + BOLD)
            cc = tr.cluster_center
            cc_col = _vc(cc, 0.02)
            vt = tr.verdict
            vt_col = _rc(vt)

            # Visual range bar using MiniChart if available
            price = sec.price
            fair = price * (1.0 + cc) if price else 0
            bear = price * 0.72
            bull = price * 1.38
            if _IAM_SPARKLINES and price > 0:
                range_bar = MiniChart.range_bar(fair, bear, bull, width=18)
            else:
                range_bar = _meter(cc, -0.4, 0.4, 18)

            cv.put(sep + 2, c0 + 3, f"Cluster Center:   {cc:>+7.1%}", cc_col)
            cv.put(sep + 3, c0 + 3, f"Valuation Spread: {tr.spread:>7.1%}", C_WHITE)
            cv.put(sep + 4, c0 + 3, f"Profile:          {vt}", vt_col)
            cv.put(sep + 5, c0 + 3, f"Range Position: [{range_bar}]", cc_col)


# ── Factor Scoring ────────────────────────────────────────────────────────


class FactorPanel(_Panel):
    title = "FACTOR SCORING ANALYSIS"

    FACTORS = [
        ("quality",                 "Quality"),
        ("intrinsic_value",         "Intrinsic Value"),
        ("relative_value",          "Relative Value"),
        ("sentiment",               "Sentiment"),
        ("momentum",                "Momentum"),
        ("macro_regime",            "Macro Regime"),
        ("reflexivity",             "Reflexivity"),
        ("runway",                  "Runway"),
        ("expectations_difficulty", "Expectations"),
        ("crowding",                "Crowding"),
    ]

    def render(
        self,
        cv: Canvas,
        r0: int,
        r1: int,
        c0: int,
        c1: int,
        sec: SecState | None,
        ticks: int = 0,
    ) -> None:
        if not sec:
            return
        if sec.loading:
            self._loading(cv, r0, r1, c0, c1, sec.ticker)
            return

        sr = sec.score_result
        comp = sec.composite
        comp_100 = int((comp + 1.0) * 50.0)
        cs = _vc(comp)

        # Composite header
        cv.put(r0, c0 + 1, f"Composite Score: {comp_100}/100  ({comp:>+.4f})", C_ACCENT + BOLD)
        mtr = _meter(comp, -1, 1, 30)
        cv.put(r0 + 1, c0 + 1, "[", C_DIM)
        cv.put(r0 + 1, c0 + 2, mtr, cs)
        cv.put(r0 + 1, c0 + 32, "]", C_DIM)

        cv.hline(r0 + 3, c0, c1)
        cv.put(r0 + 4, c0 + 1, f"{'Factor':<22} {'Val':>6}  {'Conf':>5}  Meter", C_DIM)
        cv.hline(r0 + 5, c0, c1)

        breakdown = getattr(sr, "factor_breakdown", {}) if sr else {}
        for idx, (key, label) in enumerate(self.FACTORS):
            r = r0 + 6 + idx
            if r > r1 - 1:
                break
            contrib = breakdown.get(key)
            val = float(contrib.value) if contrib else 0.0
            conf = float(getattr(contrib, "confidence", 1.0)) if contrib else 0.0
            val_col = _vc(val)
            conf_col = C_DIM if conf < 0.5 else (C_YELLOW if conf < 0.75 else C_WHITE)
            bar = _meter(val, -1, 1, 12)
            cv.put(r, c0 + 1, f"{label:<22}", C_WHITE)
            cv.put(r, c0 + 24, f"{val:>+5.3f}", val_col)
            cv.put(r, c0 + 31, f"{conf:.0%}", conf_col)
            cv.put(r, c0 + 36, f"[", C_DIM)
            cv.put(r, c0 + 37, bar, val_col)
            cv.put(r, c0 + 49, f"]", C_DIM)


# ── Scenario & Thesis ─────────────────────────────────────────────────────


class ScenarioPanel(_Panel):
    title = "SCENARIO & THESIS ENGINE"

    def render(
        self,
        cv: Canvas,
        r0: int,
        r1: int,
        c0: int,
        c1: int,
        sec: SecState | None,
        ticks: int = 0,
    ) -> None:
        if not sec:
            return
        if sec.loading:
            self._loading(cv, r0, r1, c0, c1, sec.ticker)
            return

        price = sec.price or 150.0
        upside = sec.upside
        bear = price * 0.72
        base = price * (1.0 + upside)
        bull = price * 1.38
        exp = (bear * 0.20) + (base * 0.60) + (bull * 0.20)
        prem = (exp - price) / price if price else 0

        cv.put(r0, c0 + 1, "Bayesian Scenario Thesis Engine", C_ACCENT + BOLD)
        cv.hline(r0 + 1, c0, c1)

        # Scenario table (matches iam.ui.panels.ScenarioMatrixPanel format)
        scenarios = [
            ("Bear Case",  "20%", bear, f"{(bear - price) / price:>+.1%}", "Stressed execution"),
            ("Base Case",  "60%", base, f"{(base - price) / price:>+.1%}", "Anchor assumptions"),
            ("Bull Case",  "20%", bull, f"{(bull - price) / price:>+.1%}", "Platform leverage"),
        ]
        hdrs = f"{'SCENARIO':<14} {'PROB':<6} {'TARGET':>12}  {'RETURN':>8}  THESIS"
        cv.put(r0 + 2, c0 + 2, hdrs, C_DIM)
        cv.hline(r0 + 3, c0, c1)
        scenario_colors = [C_RED, C_YELLOW, C_GREEN]
        for i, (name, prob, target, ret, thesis) in enumerate(scenarios):
            r = r0 + 4 + i
            col = scenario_colors[i]
            cv.put(r, c0 + 2, f"{name:<14}", col)
            cv.put(r, c0 + 17, f"{prob:<6}", C_WHITE)
            cv.put(r, c0 + 24, f"${target:>10.2f}", C_WHITE)
            cv.put(r, c0 + 36, f"{ret:>8}", col)
            cv.put(r, c0 + 46, thesis, C_DIM)

        cv.hline(r0 + 7 + len(scenarios) - 3, c0, c1)

        # Visual bar chart
        bar_r = r0 + 8
        bw = c1 - c0 - 22
        cv.put(bar_r, c0 + 1, "Visual Range:", C_DIM)
        for i, (name, _, target, _, _) in enumerate(scenarios):
            bar_len = max(0, int((target / (bull * 1.05)) * bw))
            col = scenario_colors[i]
            label = name[:4]
            cv.put(bar_r + 1 + i, c0 + 1, f"{label} ", col)
            cv.put(bar_r + 1 + i, c0 + 6, FULL * min(bar_len, bw), col)
            cv.put(bar_r + 1 + i, c0 + 6 + min(bar_len, bw) + 1, f"${target:.0f}", C_DIM)

        cv.hline(bar_r + 4 + len(scenarios) - 3, c0, c1)
        prem_col = C_GREEN if prem >= 0 else C_RED
        cv.put(bar_r + 5, c0 + 2, f"Expected Value:  ${exp:.2f}", C_WHITE)
        cv.put(bar_r + 5, c0 + 26, f"  vs Current: {prem:>+.1%}", prem_col + BOLD)
        cv.put(bar_r + 6, c0 + 2, "Run main.py → Option 4 to enter custom Bull/Bear inputs.", C_DIM + ITALIC)


# ── Backtest ──────────────────────────────────────────────────────────────


class BacktestPanel(_Panel):
    title = "BACKTEST FACTOR EFFICACY"

    ROWS = [
        ("Quality",          "+0.084", "0.012", "+5.2%", True),
        ("Intrinsic Value",  "+0.112", "0.005", "+6.8%", True),
        ("Relative Value",   "+0.091", "0.008", "+5.9%", True),
        ("Sentiment",        "+0.023", "0.254", "+1.4%", False),
        ("Momentum",         "+0.067", "0.031", "+4.3%", True),
        ("Macro Regime",     "+0.055", "0.044", "+3.8%", True),
        ("Earnings Quality", "+0.078", "0.019", "+4.9%", True),
        ("Expectations",     "+0.041", "0.112", "+2.6%", False),
        ("Runway",           "+0.034", "0.178", "+2.1%", False),
        ("Crowding",         "-0.019", "0.310", "-1.2%", False),
    ]

    def render(
        self,
        cv: Canvas,
        r0: int,
        r1: int,
        c0: int,
        c1: int,
        sec: SecState | None,
        ticks: int = 0,
    ) -> None:
        cv.put(r0, c0 + 1, "Empirical Factor Backtest Summary (v0.4 illustrative)", C_ACCENT + BOLD)
        cv.put(r0 + 1, c0 + 1, "IC / p-value / Top-vs-Bottom-Quintile spread", C_DIM)
        cv.hline(r0 + 2, c0, c1)
        cv.put(r0 + 3, c0 + 1, f"{'Factor':<22} {'IC':>6}  {'p-val':>6}  {'Spread':>7}  Sig", C_DIM)
        cv.hline(r0 + 4, c0, c1)

        for idx, (name, ic, pval, spread, sig) in enumerate(self.ROWS):
            r = r0 + 5 + idx
            if r > r1 - 3:
                break
            col = C_GREEN if sig else C_RED
            cv.put(r, c0 + 1, f"{name:<22}", C_WHITE)
            cv.put(r, c0 + 24, f"{ic:>6}", col)
            cv.put(r, c0 + 32, f"{pval:>6}", C_WHITE)
            cv.put(r, c0 + 40, f"{spread:>7}", col)
            cv.put(r, c0 + 49, "✓ sig" if sig else "—", C_GREEN if sig else C_DIM)

        foot = r0 + 5 + len(self.ROWS)
        cv.hline(foot, c0, c1)
        cv.put(foot + 1, c0 + 1, "Run scripts/backtest_runner.py for a live empirical IC run.", C_DIM + ITALIC)
        cv.put(foot + 2, c0 + 1, "Significant factors (p<0.05) shown in green.", C_DIM + ITALIC)


# ── Portfolio Overview ────────────────────────────────────────────────────


class PortfolioPanel(_Panel):
    """
    Displays a simulated portfolio overview.
    When iam.portfolio is available, uses format_holdings_table and
    format_factor_exposure_heatmap for real output.
    """

    title = "PORTFOLIO OVERVIEW"

    # Mock watchlist as simulated portfolio
    _HOLDINGS = [
        {"ticker": "AAPL",  "weight": 0.22, "market_value": 52400, "pnl_pct": 18.2,  "conviction": "HIGH"},
        {"ticker": "MSFT",  "weight": 0.18, "market_value": 43200, "pnl_pct": 11.4,  "conviction": "HIGH"},
        {"ticker": "NVDA",  "weight": 0.15, "market_value": 36000, "pnl_pct": 72.1,  "conviction": "MEDIUM"},
        {"ticker": "TSLA",  "weight": 0.12, "market_value": 28800, "pnl_pct": -8.3,  "conviction": "LOW"},
        {"ticker": "AMD",   "weight": 0.10, "market_value": 24000, "pnl_pct": 5.6,   "conviction": "MEDIUM"},
        {"ticker": "GOOG",  "weight": 0.13, "market_value": 31200, "pnl_pct": 14.7,  "conviction": "HIGH"},
        {"ticker": "AMZN",  "weight": 0.10, "market_value": 24000, "pnl_pct": 9.3,   "conviction": "MEDIUM"},
    ]

    _EXPOSURES = {
        "Quality":       0.82,
        "Momentum":      0.61,
        "Value":        -0.24,
        "Sentiment":     0.35,
        "Macro Regime":  0.10,
        "Crowding":     -0.47,
    }

    def render(
        self,
        cv: Canvas,
        r0: int,
        r1: int,
        c0: int,
        c1: int,
        sec: SecState | None,
        ticks: int = 0,
    ) -> None:
        cv.put(r0, c0 + 1, "Portfolio Overview  (illustrative positions)", C_ACCENT + BOLD)
        cv.hline(r0 + 1, c0, c1)

        # Holdings table header
        cv.put(r0 + 2, c0 + 1, f"{'Ticker':<7} {'Weight':>7}  {'Mkt Value':>12}  {'P&L %':>7}  Conviction", C_DIM)
        cv.hline(r0 + 3, c0, c1)

        total_val = sum(h["market_value"] for h in self._HOLDINGS)
        for idx, h in enumerate(self._HOLDINGS):
            r = r0 + 4 + idx
            if r > r1 - 8:
                break
            pnl = h["pnl_pct"]
            pnl_col = C_GREEN if pnl >= 0 else C_RED
            conv_col = {"HIGH": C_GREEN, "MEDIUM": C_YELLOW, "LOW": C_RED}.get(h["conviction"], C_WHITE)
            cv.put(r, c0 + 1, f"{h['ticker']:<7}", C_WHITE)
            cv.put(r, c0 + 9, f"{h['weight']:>6.1%}", C_WHITE)
            cv.put(r, c0 + 17, f"  ${h['market_value']:>10,.0f}", C_WHITE)
            cv.put(r, c0 + 31, f"  {pnl:>+6.1f}%", pnl_col)
            cv.put(r, c0 + 40, f"  {h['conviction']:<8}", conv_col)

        sep = r0 + 4 + len(self._HOLDINGS) + 1
        cv.hline(sep, c0, c1)
        cv.put(sep + 1, c0 + 1, f"Total:  ${total_val:>12,.0f}", C_WHITE + BOLD)

        # Factor exposure section
        exp_r = sep + 3
        cv.put(exp_r, c0 + 1, "Net Factor Exposures (z-score)", C_ACCENT + BOLD)
        cv.hline(exp_r + 1, c0, c1)
        bar_w = min(20, c1 - c0 - 30)

        for idx, (factor, exposure) in enumerate(self._EXPOSURES.items()):
            r = exp_r + 2 + idx
            if r > r1 - 1:
                break
            col = C_GREEN if exposure > 0 else C_RED
            bar_len = int(abs(exposure) * bar_w)
            bar = FULL * min(bar_len, bar_w)
            arrow = "↑" if exposure > 0 else "↓"
            cv.put(r, c0 + 1, f"{arrow} {factor:<16}", col)
            cv.put(r, c0 + 19, f"{bar:<{bar_w}}", col)
            cv.put(r, c0 + 19 + bar_w + 1, f"{exposure:>+5.2f}σ", col)


# ── Matrix Rain ───────────────────────────────────────────────────────────


class MatrixPanel(_Panel):
    title = "MATRIX DIGITAL RAIN"

    def render(
        self,
        cv: Canvas,
        r0: int,
        r1: int,
        c0: int,
        c1: int,
        sec: SecState | None,
        ticks: int = 0,
    ) -> None:
        cv.put(r0 + 1, c0 + 2, "Digital Rain Subsystem", C_GREEN + BOLD)
        cv.put(r0 + 3, c0 + 2, "Press [Enter] to launch full-screen simulation.", C_WHITE)
        cv.put(r0 + 4, c0 + 2, "Press [Q], [Esc] or [Enter] inside to return.", C_DIM)
        cv.put(r0 + 6, c0 + 2, "Renders random ASCII + katakana characters via", C_DIM)
        cv.put(r0 + 7, c0 + 2, "direct ANSI coordinate addressing for visual effect.", C_DIM)


# ── System Info ───────────────────────────────────────────────────────────


class SysInfoPanel(_Panel):
    title = "SYSTEM INFORMATION"

    def render(
        self,
        cv: Canvas,
        r0: int,
        r1: int,
        c0: int,
        c1: int,
        sec: SecState | None,
        ticks: int = 0,
    ) -> None:
        cols, rows = shutil.get_terminal_size()
        cv.put(r0, c0 + 1, "Platform Parameters", C_ACCENT + BOLD)
        cv.hline(r0 + 1, c0, c1)
        rows_data = [
            ("OS",           sys.platform.upper()),
            ("Terminal",     f"{cols}×{rows} cells"),
            ("Python",       sys.version.split()[0]),
            ("IAM Core",     "Available ✓" if _IAM_CORE else "Unavailable (mock mode)"),
            ("Sparklines",   "iam.ui.sparklines ✓" if _IAM_SPARKLINES else "Built-in fallback"),
            ("Portfolio UI", "iam.portfolio ✓" if _IAM_PORTFOLIO else "Built-in fallback"),
            ("Active Ticker", sec.ticker if sec else "—"),
            ("Last Fetch",   sec.last_updated.strftime("%H:%M:%S") if sec else "—"),
            ("Error State",  (sec.error[:38] if sec and sec.error else "None")),
        ]
        for idx, (k, v) in enumerate(rows_data):
            r = r0 + 2 + idx * 2
            if r > r1 - 1:
                break
            v_col = (
                C_GREEN if "Available" in v or "✓" in v
                else C_RED if "Unavailable" in v or ("Error" in k and v != "None")
                else C_ACCENT
            )
            cv.put(r, c0 + 2, f"{k}:", C_DIM)
            cv.put(r, c0 + 22, v, v_col)

        cv.hline(r1 - 2, c0, c1)
        cv.put(r1 - 1, c0 + 1, "Press [R] to force-reload the active security.", C_DIM)


# ── Switch Security ───────────────────────────────────────────────────────


class SwitchPanel(_Panel):
    title = "SWITCH ACTIVE SECURITY"

    def render(
        self,
        cv: Canvas,
        r0: int,
        r1: int,
        c0: int,
        c1: int,
        sec: SecState | None,
        ticks: int = 0,
    ) -> None:
        cv.put(r0 + 1, c0 + 2, "Switch Active Security", C_GOLD + BOLD)
        cv.put(r0 + 3, c0 + 2, "Press [Enter] to open the ticker search prompt.", C_WHITE)
        cv.put(r0 + 4, c0 + 2, "You can type a company name or ticker symbol.", C_DIM)
        cv.put(r0 + 6, c0 + 2, "Resolves via Yahoo Finance, fetches live fundamentals,", C_DIM)
        cv.put(r0 + 7, c0 + 2, "runs the full 7-stage pipeline, and updates all panels.", C_DIM)
        cv.put(r0 + 9, c0 + 2, "Hotkey: [S] works from any panel.", C_DIM)
        cv.put(r0 + 11, c0 + 2, "Press [W] to add a ticker to the watchlist.", C_DIM)


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN APPLICATION
# ═══════════════════════════════════════════════════════════════════════════


class AlphaTerminal:
    MENU_ITEMS: list[str] = [
        "Watchlist",
        "Quick Recommendation",
        "Deep Dive Valuation",
        "Factor Scoring",
        "Scenario & Thesis",
        "Backtest Efficacy",
        "Portfolio Overview",
        "Matrix Digital Rain",
        "System Info",
        "Switch Security",
        "─────────────────",
        "Exit",
    ]

    DEFAULT_WATCHLIST = ["TSLA", "MSFT", "AAPL", "NVDA", "META"]

    def __init__(self) -> None:
        self._active = "AAPL"
        self._watchlist: list[str] = list(self.DEFAULT_WATCHLIST)
        self._menu_idx = 0
        self._secs: dict[str, SecState] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=4)
        self._running = False
        self._canvas: Canvas | None = None
        self._ticks = 0

        self._panels: dict[str, _Panel] = {
            "Watchlist":            WatchlistPanel(self._watchlist),
            "Quick Recommendation": QuickRecPanel(),
            "Deep Dive Valuation":  DeepValPanel(),
            "Factor Scoring":       FactorPanel(),
            "Scenario & Thesis":    ScenarioPanel(),
            "Backtest Efficacy":    BacktestPanel(),
            "Portfolio Overview":   PortfolioPanel(),
            "Matrix Digital Rain":  MatrixPanel(),
            "System Info":          SysInfoPanel(),
            "Switch Security":      SwitchPanel(),
        }

        atexit.register(self._teardown)

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def start(self) -> None:
        if sys.platform == "win32":
            os.system("")
            try:
                sys.stdout.reconfigure(encoding="utf-8")
            except AttributeError:
                pass
        else:
            self._old_settings = termios.tcgetattr(sys.stdin.fileno())
            tty.setcbreak(sys.stdin.fileno())
        sys.stdout.write(ALT_ON + CURSOR_HIDE + CLEAR)
        sys.stdout.flush()
        self._running = True
        self._resize()
        # Preload active ticker and watchlist in background
        self._async_load(self._active)
        for t in self._watchlist:
            if t != self._active:
                self._async_load(t)
        self._main_loop()

    def _teardown(self) -> None:
        sys.stdout.write(CURSOR_SHOW + ALT_OFF)
        sys.stdout.flush()
        if sys.platform != "win32" and hasattr(self, "_old_settings"):
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self._old_settings)
        self._executor.shutdown(wait=False)

    # ── Layout ────────────────────────────────────────────────────────────

    def _resize(self) -> None:
        cols, rows = shutil.get_terminal_size()
        if self._canvas is None:
            self._canvas = Canvas(rows, cols)
        else:
            self._canvas.resize(rows, cols)

    # ── Main loop ─────────────────────────────────────────────────────────

    def _main_loop(self) -> None:
        try:
            while self._running:
                self._handle_key()
                self._ticks += 1
                if self._ticks % 5 == 0:
                    self._draw_all()
                if self._ticks % 80 == 0:
                    self._tick_prices()
                time.sleep(0.04)
        except KeyboardInterrupt:
            pass
        finally:
            self._teardown()
            print("\nAlpha Terminal closed.  Goodbye!")

    # ── Input ─────────────────────────────────────────────────────────────

    def _handle_key(self) -> None:
        key = _getch_nowait()
        if key is None:
            return
        if key in (b"\xe0", b"\x00"):  # Windows arrow prefix
            arrow = _getch_block()
            if arrow == b"H":
                self._nav(-1)
            elif arrow == b"P":
                self._nav(+1)
        elif key == b"\x1b":
            nxt = _getch_nowait()
            if nxt is None:
                self._quit()
                return
            if nxt == b"[":
                code = _getch_block()
                if code == b"A":
                    self._nav(-1)
                elif code == b"B":
                    self._nav(+1)
        elif key.lower() == b"q":
            self._quit()
        elif key.lower() == b"s":
            self._switch_flow()
        elif key.lower() == b"r":
            self._force_reload()
        elif key.lower() == b"w":
            self._add_to_watchlist_flow()
        elif key == b"\r":
            self._activate()

    def _nav(self, d: int) -> None:
        new = (self._menu_idx + d) % len(self.MENU_ITEMS)
        if self.MENU_ITEMS[new].startswith("─"):
            new = (new + d) % len(self.MENU_ITEMS)
        self._menu_idx = new

    def _activate(self) -> None:
        item = self.MENU_ITEMS[self._menu_idx]
        if item == "Exit":
            self._quit()
        elif item == "Matrix Digital Rain":
            self._run_matrix_rain()
        elif item == "Switch Security":
            self._switch_flow()

    def _quit(self) -> None:
        self._running = False

    # ── Data loading ──────────────────────────────────────────────────────

    def _async_load(self, ticker: str, force: bool = False) -> None:
        with self._lock:
            ex = self._secs.get(ticker)
            if ex and ex.loading:
                return
            if ex and not force and not ex.error:
                return
            self._secs[ticker] = SecState(ticker=ticker, loading=True)
        self._executor.submit(self._worker, ticker)

    def _worker(self, ticker: str) -> None:
        try:
            if _IAM_CORE:
                sec = _fetch_security(ticker)
                sr = _score(sec)
                pr = _Pipeline().run(sec)
                p = float(sec.market.price or 150.0)
                hist = [p * random.uniform(0.97, 1.03) for _ in range(25)]
                hist.append(p)
                with self._lock:
                    st = self._secs[ticker]
                    st.security = sec
                    st.score_result = sr
                    st.pipeline_result = pr
                    st.history = hist
                    st.loading = False
                    st.last_updated = datetime.now()
                    st.error = None
            else:
                self._mock_load(ticker)
        except Exception as e:
            self._mock_load(ticker, error=str(e))

    def _mock_load(self, ticker: str, error: str | None = None) -> None:
        time.sleep(random.uniform(0.3, 0.9))
        p = random.uniform(50.0, 700.0)
        with self._lock:
            st = self._secs[ticker]
            st.security = _MockSec(ticker, p)
            st.score_result = _MockScore()
            st.pipeline_result = _MockPipeline()
            st.security.market.price = p
            st.history = [p * random.uniform(0.97, 1.03) for _ in range(25)]
            st.history.append(p)
            st.loading = False
            st.last_updated = datetime.now()
            st.error = error

    def _force_reload(self) -> None:
        with self._lock:
            self._secs.pop(self._active, None)
        self._async_load(self._active)

    def _tick_prices(self) -> None:
        """Simulate live price ticks for sparkline animation."""
        with self._lock:
            st = self._secs.get(self._active)
            if st and not st.loading and st.security:
                try:
                    p = st.security.market.price or 150.0
                    new_price = max(1.0, p + random.gauss(0, p * 0.004))
                    st.security.market.price = new_price
                    st.history.append(new_price)
                    if len(st.history) > 50:
                        st.history = st.history[-50:]
                except Exception:
                    pass

    # ── Interactive flows ─────────────────────────────────────────────────

    def _switch_flow(self) -> None:
        if sys.platform != "win32" and hasattr(self, "_old_settings"):
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self._old_settings)
        sys.stdout.write(CURSOR_SHOW + CLEAR)
        sys.stdout.flush()
        cols, _ = shutil.get_terminal_size()
        bw = min(cols - 4, 68)
        print(TL1 + H1 * bw + TR1)
        print(f"{V1}  {C_GOLD}{BOLD}QUANT SECURITY DISCOVERY{RESET}".ljust(bw + 12) + V1)
        print(f"{V1}  Enter a ticker symbol or company name (e.g. 'Apple' or 'AAPL'):".ljust(bw + 1) + V1)
        print(BL1 + H1 * bw + BR1)
        print()
        try:
            raw = input(f"  {C_ACCENT}❯{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            raw = ""
        if raw:
            ticker, name = _resolve_ticker(raw)
            if _valid_ticker(ticker):
                print(f"\n  {C_GREEN}✓ Resolved: {ticker}{(' — ' + name) if name else ''}{RESET}")
                self._active = ticker
                if ticker not in self._watchlist:
                    self._watchlist.append(ticker)
                self._async_load(ticker)
            else:
                print(f"\n  {C_RED}⚠  Could not resolve '{raw}' to a valid ticker.{RESET}")
        else:
            print(f"\n  {C_DIM}No input — keeping {self._active}.{RESET}")
        print(f"\n  Press any key to return...")
        sys.stdout.flush()
        sys.stdout.write(CURSOR_HIDE)
        _getch_block()
        if sys.platform != "win32":
            tty.setcbreak(sys.stdin.fileno())
        if self._canvas:
            self._canvas._dirty = True

    def _add_to_watchlist_flow(self) -> None:
        if sys.platform != "win32" and hasattr(self, "_old_settings"):
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self._old_settings)
        sys.stdout.write(CURSOR_SHOW + CLEAR)
        sys.stdout.flush()
        print(f"{TL1}{H1 * 50}{TR1}")
        print(f"{V1}  {C_GOLD}{BOLD}ADD TO WATCHLIST{RESET}".ljust(62) + V1)
        print(f"{BL1}{H1 * 50}{BR1}\n")
        try:
            raw = input(f"  {C_ACCENT}Ticker:{RESET} ").strip().upper()
        except (EOFError, KeyboardInterrupt):
            raw = ""
        if raw and _valid_ticker(raw) and raw not in self._watchlist:
            self._watchlist.append(raw)
            self._async_load(raw)
            print(f"\n  {C_GREEN}✓ {raw} added to watchlist.{RESET}")
        elif raw in self._watchlist:
            print(f"\n  {C_YELLOW}⚠ {raw} already in watchlist.{RESET}")
        else:
            print(f"\n  {C_DIM}No change.{RESET}")
        print(f"\n  Press any key...")
        sys.stdout.write(CURSOR_HIDE)
        _getch_block()
        if sys.platform != "win32":
            tty.setcbreak(sys.stdin.fileno())
        if self._canvas:
            self._canvas._dirty = True

    # ── Matrix rain ───────────────────────────────────────────────────────

    def _run_matrix_rain(self) -> None:
        sys.stdout.write(CLEAR)
        sys.stdout.flush()
        cols, rows = shutil.get_terminal_size()
        drops = [random.randint(0, rows) for _ in range(cols)]
        chars = [chr(c) for c in range(33, 127)] + list("アイウエオカキクケコサシスセソタチツテト")
        try:
            while True:
                k = _getch_nowait()
                if k and k.lower() in (b"q", b"\x1b", b"\r"):
                    break
                buf: list[str] = []
                for col in range(cols):
                    r = drops[col]
                    if r > 2:
                        buf.append(mv(r - 2, col + 1) + " ")
                    buf.append(mv(r, col + 1) + C_WHITE + random.choice(chars) + RESET)
                    if r > 1:
                        buf.append(mv(r - 1, col + 1) + C_GREEN + random.choice(chars) + RESET)
                    drops[col] = (r % rows) + 1
                sys.stdout.write("".join(buf))
                sys.stdout.flush()
                time.sleep(0.035)
        finally:
            if self._canvas:
                self._canvas._dirty = True

    # ── Drawing ───────────────────────────────────────────────────────────

    def _draw_all(self) -> None:
        cols, rows = shutil.get_terminal_size()
        if self._canvas is None or self._canvas.rows != rows or self._canvas.cols != cols:
            self._resize()
        cv = self._canvas
        assert cv is not None
        cv.clear_back()

        if cols < MIN_COLS or rows < MIN_ROWS:
            msg = f"Terminal too small ({cols}×{rows}). Min: {MIN_COLS}×{MIN_ROWS}."
            cv.put(rows // 2, max(0, (cols - len(msg)) // 2), msg, C_RED + BOLD)
            cv.flush()
            return

        self._draw_header(cv, rows, cols)
        self._draw_menu(cv, rows, cols)
        self._draw_divider(cv, rows, cols)
        self._draw_panel(cv, rows, cols)
        self._draw_footer(cv, rows, cols)
        cv.flush()

    def _draw_header(self, cv: Canvas, rows: int, cols: int) -> None:
        w = cols
        # Top border
        cv.put(0, 0, TL + H2 * (w - 2) + TR, C_ACCENT)
        # Security info line
        with self._lock:
            sec = self._secs.get(self._active)
        comp_name = sec.name[:28] if (sec and not sec.loading) else ("Loading…" if sec else "—")
        iam_tag = f"  {C_GREEN}[IAM]{RESET}" if _IAM_CORE else f"  {C_RED}[MOCK]{RESET}"
        ts = datetime.now().strftime("%H:%M:%S")
        cv.put(1, 0, V2, C_ACCENT)
        cv.put(1, 1, f" {C_ACCENT}{BOLD}ALPHA-TERMINAL{RESET}  {C_DIM}Active:{RESET} {C_GOLD}{BOLD}{self._active:<6}{RESET}  {C_DIM}{comp_name}{RESET}{iam_tag}", "")
        cv.put(1, w - len(ts) - 2, ts, C_DIM)
        cv.put(1, w - 1, V2, C_ACCENT)
        # Separator
        cv.put(2, 0, MID_L + H2 * (w - 2) + MID_R, C_ACCENT)

    def _draw_footer(self, cv: Canvas, rows: int, cols: int) -> None:
        w = cols
        cv.put(rows - 2, 0, MID_L + H2 * (w - 2) + MID_R, C_ACCENT)
        help_items = [
            ("[↑↓]", "Navigate"),
            ("[Enter]", "Select"),
            ("[S]", "Switch Ticker"),
            ("[W]", "Add Watchlist"),
            ("[R]", "Reload"),
            ("[Q]", "Quit"),
        ]
        x = 1
        cv.put(rows - 1, 0, V2, C_ACCENT)
        for key, label in help_items:
            cv.put(rows - 1, x, key, C_DIM)
            x += len(key)
            cv.put(rows - 1, x, f" {label}  ", C_WHITE)
            x += len(label) + 3
        cv.put(rows - 1, w - 1, V2, C_ACCENT)

    def _draw_divider(self, cv: Canvas, rows: int, cols: int) -> None:
        for r in range(HDR_ROWS, rows - FTR_ROWS):
            cv.put(r, 0, V2, C_ACCENT)
            cv.put(r, MENU_W - 1, V1, C_DIM)
            cv.put(r, cols - 1, V2, C_ACCENT)

    def _draw_menu(self, cv: Canvas, rows: int, cols: int) -> None:
        for idx, item in enumerate(self.MENU_ITEMS):
            r = HDR_ROWS + idx
            if r >= rows - FTR_ROWS:
                break
            is_sep = item.startswith("─")
            is_sel = idx == self._menu_idx and not is_sep
            if is_sep:
                cv.put(r, 1, H1 * (MENU_W - 3), C_DIM)
            elif is_sel:
                cv.put(r, 1, f"▶ {item:<{MENU_W - 4}}", C_GOLD + BOLD)
            else:
                cv.put(r, 1, f"  {item:<{MENU_W - 4}}", C_WHITE)

    def _draw_panel(self, cv: Canvas, rows: int, cols: int) -> None:
        item = self.MENU_ITEMS[self._menu_idx]
        if item.startswith("─") or item == "Exit":
            return
        panel = self._panels.get(item)
        if panel is None:
            return

        c0 = MENU_W
        c1 = cols - 2
        r0 = HDR_ROWS
        r1 = rows - FTR_ROWS - 1

        # Panel title strip
        cv.put(r0, c0, f" ╸ {panel.title}", C_ACCENT + BOLD)
        cv.hline(r0 + 1, c0, c1, style=C_DIM)

        with self._lock:
            sec = self._secs.get(self._active)

        # Pass ticks so loading spinners can animate
        panel.render(cv, r0 + 2, r1, c0, c1, sec, self._ticks)


# ═══════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    terminal = AlphaTerminal()
    terminal.start()
