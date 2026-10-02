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
import math
import os
import random
import shutil
import sys
import threading
import time
import urllib.parse
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from unittest.mock import MagicMock

from iam.config.settings import get_settings
from iam.data import markets as MKT
from iam.data.http import safe_urlopen
from iam.ui import widgets as W
from iam.ui.market_panels import GlobalMarketsPanel, RealWatchlistPanel, render_ribbon
from iam.ui.research_panels import (
    ArbitrationVisualizerPanel,
    ExpectationsBattlefieldPanel,
    FragilityMapPanel,
    ReverseDCFDistributionPanel,
    ThesisDriftPanel,
)
from iam.ui.settings_panel import SettingsPanel

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
    from iam import score as _score
    from iam.data.providers.yfinance_adapter import fetch_security as _fetch_security
    from iam.learning.learning_module import LearningModule as _LearningModule
    from iam.pipeline.orchestrator import ValuationPipeline as _Pipeline
    from iam.ui.visualization_lab import render_dcf_surface as _render_dcf_surface
    from iam.valuation.sensitivity import DCFValuationSurface
    from iam.valuation.topology import compute_gradients as _compute_gradients

    _IAM_CORE = True
except ImportError:
    _IAM_CORE = False

try:
    from iam.ui.sparklines import MiniChart, ProgressBar, Sparkline

    _IAM_SPARKLINES = True
except ImportError:
    _IAM_SPARKLINES = False

try:
    from iam.portfolio.ui import format_factor_exposure_heatmap, format_holdings_table  # noqa: F401

    _IAM_PORTFOLIO = True
except ImportError:
    _IAM_PORTFOLIO = False

try:
    from iam.ui.state import SystemState

    _IAM_STATE = True
except ImportError:
    _IAM_STATE = False


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
C_ACCENT = fg(39)  # Bright cyan
C_GOLD = fg(220)  # Amber — active / highlights
C_GREEN = fg(82)  # Bright green
C_RED = fg(196)  # Bright red
C_YELLOW = fg(226)  # Yellow
C_DIM = fg(240)  # Dark grey
C_WHITE = fg(255)  # Near-white
C_BLUE = fg(33)  # Blue
C_MAGENTA = fg(135)  # Magenta
C_TEAL = fg(51)  # Teal
C_MENU_HL = bg(17) + fg(39) + BOLD
C_HDR = bg(234)


def _rc(rating: str | None) -> str:
    if rating is None:
        return C_WHITE
    return {
        "BUY": C_GREEN,
        "STRONG BUY": C_GREEN + BOLD,
        "SELL": C_RED,
        "STRONG SELL": C_RED + BOLD,
        "HOLD": C_YELLOW,
    }.get(rating.upper(), C_WHITE)


def _vc(val: float | None, threshold: float = 0.05) -> str:
    if val is None:
        return C_WHITE
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
    return "".join(SPARK_CHARS[min(8, max(0, int((v - lo) / span * 8)))] for v in window).ljust(
        width
    )


def _spark_trend(history: list[float]) -> str:
    """↑ / ↓ / → trend arrow."""
    if _IAM_SPARKLINES and len(history) >= 2:
        return Sparkline.trend(history)
    if len(history) < 2:
        return "→"
    delta = history[-1] - history[0]
    return "↑" if delta > 0 else ("↓" if delta < 0 else "→")


def _meter(val: float | None, lo: float = -1.0, hi: float = 1.0, width: int = 18) -> str:
    """Block progress meter. Uses iam.ui.sparklines.ProgressBar if available."""
    if val is None:
        return EMPTY * width
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
#  MOCK DATA  (demo build only: used when IAM packages are unavailable)
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
        "quality",
        "intrinsic_value",
        "relative_value",
        "sentiment",
        "momentum",
        "macro_regime",
        "reflexivity",
        "runway",
        "expectations_difficulty",
        "crowding",
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
    terrain_render: str | None = None
    topology_metrics: dict[str, Any] | None = None
    last_updated: datetime = field(default_factory=datetime.now)
    loading: bool = False
    error: str | None = None

    @property
    def price(self) -> float | None:
        """Last real price, or None when unknown (never a placeholder)."""
        try:
            p = float(self.security.market.price)
        except Exception:
            return None
        return p if p > 0 else None

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
    def upside(self) -> float | None:
        """Model upside, or None when the pipeline produced none."""
        try:
            v = self.pipeline_result.final_verdict
            up = v.blended_upside
            if up is None:
                up = self.pipeline_result.implied_move_pct
            return None if up is None else float(up)
        except Exception:
            return None

    @property
    def composite(self) -> float | None:
        """Composite factor score, or None when unscored."""
        try:
            return float(self.score_result.composite)
        except Exception:
            return None

    @property
    def is_demo(self) -> bool:
        """True when this state holds the random demo-build mock data."""
        return isinstance(self.security, _MockSec)


# ═══════════════════════════════════════════════════════════════════════════
#  LAYOUT CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════

MIN_COLS = 80
MIN_ROWS = 24
MENU_W = 27  # menu column width (incl border)
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
        with safe_urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            quotes = data.get("quotes", [])
            if quotes and "symbol" in quotes[0]:
                return quotes[0]["symbol"].upper(), quotes[0].get("shortname")
    except Exception:
        pass
    return query.strip().upper(), None


def _valid_ticker(t: str) -> bool:
    from iam.validation import validate_ticker as strict_validate

    try:
        strict_validate(t)
        return True
    except ValueError:
        return False


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
        system_state: SystemState | None = None,
        ticks: int = 0,
    ) -> None:
        pass

    def _loading(
        self, cv: Canvas, r0: int, r1: int, c0: int, c1: int, ticker: str, ticks: int = 0
    ) -> None:
        mid = (r0 + r1) // 2
        sp = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"[ticks % 10]
        msg = f" {sp}  Fetching {ticker}… "
        col = max(c0 + 1, (c0 + c1) // 2 - len(msg) // 2)
        cv.box(mid - 1, mid + 1, c0 + 2, c1 - 2, C_GOLD)
        cv.put(mid, col, msg, C_GOLD + BOLD)

    def _err(self, cv: Canvas, r0: int, c0: int, msg: str) -> None:
        cv.put(r0, c0 + 2, f"⚠  {msg}", C_RED)

    def _demo_tag(self, cv: Canvas, r1: int, c0: int, sec: SecState | None) -> None:
        """Flag randomly generated demo-build data on the panel's last row."""
        if sec is not None and sec.is_demo:
            cv.put(r1, c0 + 1, "DEMO DATA (random)", C_RED + BOLD)

    def _load_failed(self, cv: Canvas, r0: int, r1: int, c0: int, c1: int, sec: SecState) -> bool:
        """Show an explicit error state when a real load failed. True if drawn."""
        if sec.pipeline_result is not None or not sec.error:
            return False
        msg = f"Could not load {sec.ticker}: {sec.error}"
        cv.box(r0 + 1, r0 + 3, c0 + 1, c1 - 2, C_RED)
        cv.put(r0 + 2, c0 + 3, msg[: max(0, c1 - c0 - 6)], C_RED + BOLD)
        return True


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
        system_state: SystemState | None = None,
        ticks: int = 0,
    ) -> None:
        if not sec:
            return
        if sec.loading:
            self._loading(cv, r0, r1, c0, c1, sec.ticker, ticks)
            return

        if self._load_failed(cv, r0, r1, c0, c1, sec):
            return

        rating = sec.rating
        confidence = sec.confidence
        upside = sec.upside
        price = sec.price
        fair = price * (1.0 + upside) if (price is not None and upside is not None) else None
        rc = _rc(rating)
        up_col = C_GREEN if (upside is not None and upside > 0) else C_RED
        price_text = f"${price:>9.2f}" if price is not None else "      n/a"
        fair_text = f"${fair:>9.2f}" if fair is not None else "      n/a"

        # Main verdict box
        bw = min(c1 - c0 - 3, 52)
        bx = c0 + 1
        by = r0 + 1
        cv.box(by, by + 6, bx, bx + bw, C_ACCENT)

        cv.put(by + 1, bx + 3, "RATING:", C_DIM)
        cv.put(by + 1, bx + 11, f"{rating}", rc + BOLD)
        cv.put(by + 1, bx + 11 + len(rating) + 2, f"Confidence: {confidence}", C_WHITE)

        cv.put(by + 3, bx + 3, f"Current:     {price_text}", C_WHITE)
        cv.put(by + 3, bx + 30, f"Fair Value: {fair_text}", C_WHITE)

        up_text = f"{upside:>+.1%}" if upside is not None else "    n/a"
        cv.put(by + 4, bx + 3, f"Implied Move: {up_text}", up_col + BOLD)
        cv.put(by + 5, bx + 3, f"Updated: {sec.last_updated:%H:%M:%S}", C_DIM)

        # Composite score meter
        comp = sec.composite
        comp_style = _vc(comp)
        comp_text = f"{int((comp + 1.0) * 50.0)}/100" if comp is not None else "n/a"
        mtr = _meter(comp, -1, 1, 28)
        cv.put(r0 + 9, c0 + 1, "Factor Score:", C_DIM)
        cv.put(r0 + 9, c0 + 15, "[", C_DIM)
        cv.put(r0 + 9, c0 + 16, mtr, comp_style)
        cv.put(r0 + 9, c0 + 44, f"] {comp_text}", C_WHITE)

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

        self._demo_tag(cv, r1, c0, sec)

        # Stage 7 Law Checks
        pr = sec.pipeline_result
        if pr and getattr(pr, "law_report", None):
            lr = pr.law_report
            if lr.violations or lr.flags:
                cv.hline(r1 - 4, c0, c1)
                cv.put(r1 - 3, c0 + 1, "DAMODARAN CONSISTENCY CHECKS:", C_ACCENT + BOLD)
                for i, check in enumerate(lr.violations + lr.flags):
                    if i > 1:
                        break
                    col = C_RED if check in lr.violations else C_YELLOW
                    cv.put(
                        r1 - 2 + i, c0 + 2, f"• LAW {check.number}: {check.narrative[:50]}...", col
                    )


def _num(v: object) -> float | None:
    """Finite float or None (NaN/inf/non-numeric all mean 'no data')."""
    if isinstance(v, bool):
        return None
    try:
        f = float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _pct_or_na(v: object) -> str:
    f = _num(v)
    return f"{f:.1%}" if f is not None else "n/a"


def _scenario_matrix(sec: SecState | None) -> list[tuple[str, dict]] | None:
    """Real FCFE scenario matrix from the pipeline report, or None if absent.

    Source: ``pipeline_result.intrinsic.components["scenarios"]`` (built in
    ``FCFEDCF.compute``). Entries lacking a finite prob/target are dropped.
    """
    pr = getattr(sec, "pipeline_result", None)
    intrinsic = getattr(pr, "intrinsic", None)
    comps = getattr(intrinsic, "components", None)
    if not isinstance(comps, dict):
        return None
    raw = comps.get("scenarios")
    if not isinstance(raw, dict):
        return None
    out: list[tuple[str, dict]] = []
    for name, d in raw.items():
        if not isinstance(d, dict):
            continue
        prob, target = _num(d.get("prob")), _num(d.get("target"))
        if prob is None or target is None:
            continue
        out.append((str(name), {**d, "prob": prob, "target": target}))
    return out or None


# ── Deep Valuation ────────────────────────────────────────────────────────


class DeepValPanel(_Panel):
    title = "DEEP DIVE VALUATION"

    STAGES = [
        ("Stage 1", "Reverse DCF", "Implied growth rate extracted from price"),
        ("Stage 2", "Relative Multiples", "Peer-adjusted EV/Sales, P/E, P/B"),
        ("Stage 3", "FCFE Intrinsic DCF", "Explicit free-cash-flow valuation"),
        ("Stage 4", "Triangulation", "Consensus across all three methods"),
        ("Stage 5", "Macro Overlay", "Regime-dependent discount adjustment"),
        ("Stage 6", "Thesis Engine", "Bayesian scenario weighting"),
        ("Stage 7", "Verdict", "Final BUY / HOLD / SELL signal"),
    ]

    def render(
        self,
        cv: Canvas,
        r0: int,
        r1: int,
        c0: int,
        c1: int,
        sec: SecState | None,
        system_state: SystemState | None = None,
        ticks: int = 0,
    ) -> None:
        if not sec:
            return
        if sec.loading:
            self._loading(cv, r0, r1, c0, c1, sec.ticker, ticks)
            return

        if self._load_failed(cv, r0, r1, c0, c1, sec):
            return

        self._demo_tag(cv, r1, c0, sec)
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
            scen = _scenario_matrix(sec)
            bear_t = bull_t = None
            if scen:
                bear_t = next((d["target"] for n, d in scen if "bear" in n.lower()), None)
                bull_t = next((d["target"] for n, d in scen if "bull" in n.lower()), None)
            if (
                _IAM_SPARKLINES
                and price is not None
                and cc is not None
                and bear_t is not None
                and bull_t is not None
            ):
                fair = price * (1.0 + cc)
                range_bar = MiniChart.range_bar(fair, bear_t, bull_t, width=18)
            else:
                range_bar = _meter(cc, -0.4, 0.4, 18)

            cc_text = f"{cc:>+7.1%}" if cc is not None else "    n/a"
            spr_text = (
                f"{tr.spread:>7.1%}" if getattr(tr, "spread", None) is not None else "    N/A"
            )

            cv.put(sep + 2, c0 + 3, f"Cluster Center:   {cc_text}", cc_col)
            cv.put(sep + 3, c0 + 3, f"Valuation Spread: {spr_text}", C_WHITE)
            cv.put(sep + 4, c0 + 3, f"Profile:          {vt}", vt_col)
            cv.put(sep + 5, c0 + 3, f"Range Position: [{range_bar}]", cc_col)


# ── Factor Scoring ────────────────────────────────────────────────────────


class FactorPanel(_Panel):
    title = "FACTOR SCORING ANALYSIS"

    FACTORS = [
        ("quality", "Quality"),
        ("intrinsic_value", "Intrinsic Value"),
        ("relative_value", "Relative Value"),
        ("sentiment", "Sentiment"),
        ("momentum", "Momentum"),
        ("macro_regime", "Macro Regime"),
        ("reflexivity", "Reflexivity"),
        ("runway", "Runway"),
        ("expectations_difficulty", "Expectations"),
        ("crowding", "Crowding"),
    ]

    def render(
        self,
        cv: Canvas,
        r0: int,
        r1: int,
        c0: int,
        c1: int,
        sec: SecState | None,
        system_state: SystemState | None = None,
        ticks: int = 0,
    ) -> None:
        if not sec:
            return
        if sec.loading:
            self._loading(cv, r0, r1, c0, c1, sec.ticker, ticks)
            return

        if self._load_failed(cv, r0, r1, c0, c1, sec):
            return

        self._demo_tag(cv, r1, c0, sec)
        sr = sec.score_result
        comp = sec.composite
        cs = _vc(comp)

        # Composite header
        if comp is not None:
            head = f"Composite Score: {int((comp + 1.0) * 50.0)}/100  ({comp:>+.4f})"
        else:
            head = "Composite Score: n/a"
        cv.put(r0, c0 + 1, head, C_ACCENT + BOLD)
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
            val = (
                float(contrib.value)
                if (contrib and getattr(contrib, "value", None) is not None)
                else None
            )
            conf = (
                float(getattr(contrib, "confidence", 1.0))
                if (contrib and getattr(contrib, "confidence", None) is not None)
                else 0.0
            )

            val_col = _vc(val)
            conf_col = C_DIM if conf < 0.5 else (C_YELLOW if conf < 0.75 else C_WHITE)
            bar = _meter(val, -1, 1, 12)

            val_text = f"{val:>+5.3f}" if val is not None else "  N/A"
            cv.put(r, c0 + 1, f"{label:<22}", C_WHITE)
            cv.put(r, c0 + 24, val_text, val_col)
            cv.put(r, c0 + 31, f"{conf:.0%}", conf_col)
            cv.put(r, c0 + 36, "[", C_DIM)
            cv.put(r, c0 + 37, bar, val_col)
            cv.put(r, c0 + 49, "]", C_DIM)


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
        system_state: SystemState | None = None,
        ticks: int = 0,
    ) -> None:
        if not sec:
            return
        if sec.loading:
            self._loading(cv, r0, r1, c0, c1, sec.ticker, ticks)
            return

        if self._load_failed(cv, r0, r1, c0, c1, sec):
            return

        self._demo_tag(cv, r1, c0, sec)
        price = sec.price
        cv.put(r0, c0 + 1, "Bayesian Scenario Thesis Engine", C_ACCENT + BOLD)
        cv.hline(r0 + 1, c0, c1)

        matrix = _scenario_matrix(sec)
        if not matrix:
            cv.put(
                r0 + 2,
                c0 + 2,
                f"Scenario table: n/a (no FCFE scenario matrix for {sec.ticker})",
                C_DIM,
            )
            return

        def _ret(target: float) -> float | None:
            return (target - price) / price if price else None

        # Scenario table (matches iam.ui.panels.ScenarioMatrixPanel format)
        scenarios = []
        for name, d in matrix:
            ret = _ret(d["target"])
            thesis = (
                f"g {_pct_or_na(d.get('g'))} · WACC {_pct_or_na(d.get('wacc'))}"
                f" · g∞ {_pct_or_na(d.get('tv_g'))}"
            )
            scenarios.append(
                (
                    name,
                    f"{d['prob']:.0%}",
                    d["target"],
                    f"{ret:>+.1%}" if ret is not None else "n/a",
                    thesis,
                )
            )
        hdrs = f"{'SCENARIO':<14} {'PROB':<6} {'TARGET':>12}  {'RETURN':>8}  ASSUMPTIONS"
        cv.put(r0 + 2, c0 + 2, hdrs, C_DIM)
        cv.hline(r0 + 3, c0, c1)

        def _color(name: str) -> str:
            n = name.lower()
            return C_RED if "bear" in n else (C_GREEN if "bull" in n else C_YELLOW)

        for i, (name, prob, target, ret, thesis) in enumerate(scenarios):
            r = r0 + 4 + i
            col = _color(name)
            cv.put(r, c0 + 2, f"{name:<14}", col)
            cv.put(r, c0 + 17, f"{prob:<6}", C_WHITE)
            cv.put(r, c0 + 24, f"${target:>10.2f}", C_WHITE)
            cv.put(r, c0 + 36, f"{ret:>8}", col)
            cv.put(r, c0 + 46, thesis, C_DIM)

        cv.hline(r0 + 7 + len(scenarios) - 3, c0, c1)

        # Visual bar chart
        bar_r = r0 + 8
        bw = c1 - c0 - 22
        max_t = max(t for _, _, t, _, _ in scenarios)
        cv.put(bar_r, c0 + 1, "Visual Range:", C_DIM)
        for i, (name, _, target, _, _) in enumerate(scenarios):
            bar_len = max(0, int((target / (max_t * 1.05)) * bw)) if max_t > 0 else 0
            col = _color(name)
            label = name[:4]
            cv.put(bar_r + 1 + i, c0 + 1, f"{label} ", col)
            cv.put(bar_r + 1 + i, c0 + 6, FULL * min(bar_len, bw), col)
            cv.put(bar_r + 1 + i, c0 + 6 + min(bar_len, bw) + 1, f"${target:.0f}", C_DIM)

        cv.hline(bar_r + 4 + len(scenarios) - 3, c0, c1)
        tot_p = sum(d["prob"] for _, d in matrix)
        exp = sum(d["prob"] * d["target"] for _, d in matrix) / tot_p if tot_p > 0 else None
        if exp is None:
            cv.put(bar_r + 5, c0 + 2, "Expected Value:  n/a", C_WHITE)
        else:
            prem = _ret(exp)
            cv.put(bar_r + 5, c0 + 2, f"Expected Value:  ${exp:.2f}", C_WHITE)
            if prem is None:
                cv.put(bar_r + 5, c0 + 26, "  vs Current: n/a", C_DIM)
            else:
                prem_col = C_GREEN if prem >= 0 else C_RED
                cv.put(bar_r + 5, c0 + 26, f"  vs Current: {prem:>+.1%}", prem_col + BOLD)
        cv.put(
            bar_r + 6,
            c0 + 2,
            "Run main.py → Option 4 to enter custom Bull/Bear inputs.",
            C_DIM + ITALIC,
        )


# ── Backtest ──────────────────────────────────────────────────────────────


class BacktestPanel(_Panel):
    title = "BACKTEST & RESEARCH INTEGRITY"

    def render(
        self,
        cv: Canvas,
        r0: int,
        r1: int,
        c0: int,
        c1: int,
        sec: SecState | None,
        system_state: SystemState | None = None,
        ticks: int = 0,
    ) -> None:
        cv.put(r0, c0 + 1, "Empirical Factor Backtest Summary (v0.5 Live)", C_ACCENT + BOLD)
        cv.put(r0 + 1, c0 + 1, "Spearman Rank IC / p-value / Quintile Spreads", C_DIM)
        cv.hline(r0 + 2, c0, c1)

        if system_state is None or system_state.loading:
            self._loading(cv, r0, r1, c0, c1, "Backtest", ticks)
            return
        if not system_state.backtest_metrics:
            cv.put(
                r0 + 3,
                c0 + 2,
                "Backtest metrics: n/a (run the IC backtest to produce "
                "data/results/ic/ic_horizon_1m.csv)",
                C_DIM,
            )
            return

        metrics = system_state.backtest_metrics
        cv.put(r0 + 3, c0 + 1, f"{'Factor':<22} {'IC':>6}  {'p-val':>6}  {'Spread':>7}  Sig", C_DIM)
        cv.hline(r0 + 4, c0, c1)

        # Draw factor-level metrics
        idx = 0
        factor_metrics = getattr(metrics, "factor_metrics", {})
        for factor, m in factor_metrics.items():
            r = r0 + 5 + idx
            if r > r1 - 15:
                break
            ic = _num(m.get("ic"))
            pv = _num(m.get("p_value"))
            spr = _num(m.get("spread"))
            sig = pv is not None and pv < 0.05
            col = C_GREEN if sig else C_RED

            cv.put(r, c0 + 1, f"{factor:<22}", C_WHITE)
            cv.put(r, c0 + 24, f"{ic:>+6.3f}" if ic is not None else f"{'n/a':>6}", col)
            cv.put(r, c0 + 32, f"{pv:>6.3f}" if pv is not None else f"{'n/a':>6}", C_WHITE)
            cv.put(r, c0 + 40, f"{spr:>+6.1%}" if spr is not None else f"{'n/a':>6}", col)
            cv.put(r, c0 + 49, "✓ sig" if sig else "—", C_GREEN if sig else C_DIM)
            idx += 1

        # Draw Research Integrity Stats
        mid_sep = r0 + 5 + idx + 1
        cv.hline(mid_sep, c0, c1)
        cv.put(
            mid_sep + 1,
            c0 + 1,
            "RESEARCH INTEGRITY LAYER (Statistical Validation)",
            C_ACCENT + BOLD,
        )

        pbo = _num(getattr(metrics, "pbo", None))
        dsr = _num(getattr(metrics, "dsr", None))
        psr = _num(getattr(metrics, "psr", None))
        pbo_t = f"{pbo:>6.1%}" if pbo is not None else f"{'n/a':>6}"
        dsr_t = f"{dsr:>5.2f}" if dsr is not None else f"{'n/a':>5}"
        psr_t = f"{psr:>6.1%}" if psr is not None else f"{'n/a':>6}"

        cv.put(
            mid_sep + 3,
            c0 + 2,
            f"Backtest Overfitting (PBO): {pbo_t}  (Target: <5.0%)",
            C_GREEN if (pbo is not None and pbo < 0.05) else C_RED,
        )
        cv.put(
            mid_sep + 4,
            c0 + 2,
            f"Deflated Sharpe Ratio (DSR): {dsr_t}  [Multiple Testing Corrected]",
            C_GREEN if (dsr is not None and dsr > 1.0) else C_WHITE,
        )
        cv.put(
            mid_sep + 5,
            c0 + 2,
            f"Probabilistic Sharpe (PSR): {psr_t}  (Confidence in SR > 0)",
            C_TEAL,
        )

        cv.hline(mid_sep + 7, c0, c1)
        cv.put(
            mid_sep + 8,
            c0 + 1,
            "Validation metrics ensure alpha is persistent, not lucky.",
            C_DIM + ITALIC,
        )


# ── Portfolio Overview ────────────────────────────────────────────────────


class PortfolioPanel(_Panel):
    """
    Equal-weight MODEL portfolio built from the watchlist.

    There is no holdings data source, so quantities, cost basis, P&L and market
    value are deliberately not shown. Prices and ratings come from real loaded
    securities / cached quotes; factor exposures are the weight-averaged factor
    scores of the holdings that have been scored.
    """

    title = "PORTFOLIO OVERVIEW"

    def __init__(self, sec_lookup: Callable[[str], SecState | None] | None = None) -> None:
        self._sec_lookup = sec_lookup or (lambda _t: None)

    @staticmethod
    def _effective(contrib: Any) -> float | None:
        """Confidence-weighted factor score of one contribution, or None."""
        try:
            return float(contrib.effective())
        except Exception:
            pass
        try:
            return float(contrib.value) * float(contrib.confidence)
        except Exception:
            return None

    @classmethod
    def factor_exposures(cls, holdings: list[tuple[float, SecState]]) -> dict[str, float]:
        """Weighted average of each scored holding's effective factor scores.

        ``holdings`` is a list of ``(weight, SecState)``. Holdings without a
        score result are ignored; weights are renormalised per factor over the
        holdings that actually have that factor. Empty dict when nothing is scored.
        """
        num: dict[str, float] = {}
        den: dict[str, float] = {}
        for weight, st in holdings:
            sr = getattr(st, "score_result", None)
            breakdown = getattr(sr, "factor_breakdown", None) if sr is not None else None
            if not breakdown:
                continue
            for name, contrib in breakdown.items():
                eff = cls._effective(contrib)
                if eff is None:
                    continue
                num[name] = num.get(name, 0.0) + weight * eff
                den[name] = den.get(name, 0.0) + weight
        return {k: num[k] / den[k] for k in num if den[k] > 0}

    def render(
        self,
        cv: Canvas,
        r0: int,
        r1: int,
        c0: int,
        c1: int,
        sec: SecState | None,
        system_state: SystemState | None = None,
        ticks: int = 0,
    ) -> None:
        cv.put(r0, c0 + 1, "Equal-Weight Model Portfolio (watchlist)", C_ACCENT + BOLD)
        cv.hline(r0 + 1, c0, c1)

        if not system_state or system_state.loading or not system_state.portfolio:
            self._loading(cv, r0, r1, c0, c1, "Portfolio", ticks)
            return

        portfolio = system_state.portfolio

        def lookup(t: str) -> SecState | None:
            st = self._sec_lookup(t)
            if st is None and sec is not None and sec.ticker == t:
                return sec
            return st

        cv.put(
            r0 + 2,
            c0 + 1,
            "Model only: equal weights, no holdings data (no quantity/cost/P&L/value).",
            C_YELLOW,
        )
        cv.put(
            r0 + 3,
            c0 + 1,
            f"{'Ticker':<7} {'Weight':>7}  {'Price':>10}  {'Rating':<8}  Conviction",
            C_DIM,
        )
        cv.hline(r0 + 4, c0, c1)

        scored: list[tuple[float, SecState]] = []
        any_demo = False
        for idx, p in enumerate(portfolio.positions):
            st = lookup(p.ticker)
            if st is not None and st.score_result is not None:
                scored.append((p.weight, st))
            any_demo = any_demo or (st is not None and st.is_demo)
            r = r0 + 5 + idx
            if r > r1 - 8:
                continue
            price = st.price if st is not None else None
            if price is None and p.current_price > 0:
                price = p.current_price
            price_text = f"${price:.2f}" if price is not None else "n/a"
            rating = st.rating if st is not None else "N/A"
            rating_text = rating if rating not in ("N/A", "") else "—"
            conv = getattr(p, "conviction", "UNRATED")
            conv_col = {"HIGH": C_GREEN, "MODERATE": C_YELLOW, "LOW": C_RED}.get(conv, C_DIM)
            cv.put(r, c0 + 1, f"{p.ticker:<7}", C_WHITE)
            cv.put(r, c0 + 9, f"{p.weight:>6.1%}", C_WHITE)
            cv.put(r, c0 + 17, f"{price_text:>10}", C_WHITE)
            cv.put(r, c0 + 31, f"{rating_text:<8}", _rc(rating) if rating_text != "—" else C_DIM)
            cv.put(r, c0 + 41, f"  {conv:<8}", conv_col)

        sep = r0 + 5 + len(portfolio.positions) + 1
        cv.hline(sep, c0, c1)
        if any_demo:
            cv.put(r1, c0 + 1, "DEMO DATA (random)", C_RED + BOLD)

        # Factor exposure section: real weighted average of scored holdings.
        exp_r = sep + 2
        cv.put(exp_r, c0 + 1, "Portfolio Risk Decomposition", C_ACCENT + BOLD)
        cv.hline(exp_r + 1, c0, c1)

        hhi = portfolio.concentration_herfindahl()
        cv.put(exp_r + 2, c0 + 1, f"Herfindahl-Hirschman Index (HHI): {hhi:.4f}", C_WHITE)
        cv.put(
            exp_r + 3,
            c0 + 1,
            f"Diversification Ratio:           {1.0 / hhi if hhi else 0:.1f}x",
            C_TEAL,
        )

        exposures = self.factor_exposures(scored)
        if not exposures:
            cv.put(exp_r + 5, c0 + 1, "Factor exposures: n/a (no scored holdings)", C_DIM)
        else:
            cv.put(
                exp_r + 5,
                c0 + 1,
                f"Factor exposures: weighted avg score of {len(scored)} scored holding(s), "
                "scale -1..+1",
                C_DIM,
            )
        for idx, (factor, exposure) in enumerate(exposures.items()):
            r = exp_r + 6 + idx
            if r > r1 - 1:
                break
            col = C_GREEN if exposure > 0 else C_RED
            bar_w = max(0, min(20, c1 - c0 - 30))
            bar_len = int(min(1.0, abs(exposure)) * bar_w)
            bar = FULL * min(bar_len, bar_w)
            arrow = "↑" if exposure > 0 else "↓"
            label = factor.replace("_", " ").title()
            cv.put(r, c0 + 1, f"{arrow} {label:<16.16}", col)
            cv.put(r, c0 + 19, f"{bar:<{bar_w}}", col)
            cv.put(r, c0 + 19 + bar_w + 1, f"{exposure:>+5.2f}", col)

        # Sector rotation signal — real sector weights from current holdings,
        # blended with the macro regime detected from the active security's
        # real MacroContext. Momentum defaults to empty (no live sector-level
        # return series is wired in yet) so the tilt shown is regime-only;
        # that limitation is stated in the panel rather than left implicit.
        rot_r = exp_r + 6 + max(1, len(exposures)) + 2
        if rot_r < r1 - 2:
            cv.put(rot_r, c0 + 1, "Sector Rotation Signal", C_ACCENT + BOLD)
            cv.hline(rot_r + 1, c0, c1)
            try:
                from iam.data.macro import MacroConditions
                from iam.pipeline.macro_regimes import MacroRegimeClassifier
                from iam.portfolio.analytics import PortfolioAnalyzer
                from iam.portfolio.sector_rotation import SectorRotationEngine

                sector_weights = PortfolioAnalyzer.compute_sector_concentration(portfolio)
                if not sector_weights:
                    cv.put(
                        rot_r + 2,
                        c0 + 1,
                        "No sector data on current holdings — signal unavailable.",
                        C_DIM,
                    )
                else:
                    macro_ctx = sec.security.macro if sec and sec.security else None
                    regime = (
                        MacroRegimeClassifier()
                        .classify(MacroConditions.from_context(macro_ctx))
                        .regime.value
                    )
                    tilts = SectorRotationEngine.recommend_sector_tilts(regime, {})
                    cv.put(
                        rot_r + 2,
                        c0 + 1,
                        f"Regime: {regime} (momentum signal not wired in — regime-only tilt)",
                        C_DIM,
                    )
                    if not tilts:
                        cv.put(rot_r + 3, c0 + 1, "No active tilt for this regime.", C_DIM)
                    else:
                        for idx, (sector, tilt) in enumerate(
                            sorted(tilts.items(), key=lambda kv: -kv[1])
                        ):
                            r = rot_r + 4 + idx
                            if r > r1 - 1:
                                break
                            col = C_GREEN if tilt > 0 else C_RED
                            arrow = "↑" if tilt > 0 else "↓"
                            current = sector_weights.get(sector, 0.0)
                            sector_label = sector[:23]
                            cv.put(r, c0 + 1, f"{arrow} {sector_label:<24}", col)
                            cv.put(r, c0 + 27, f"current {current:>5.1%}", C_DIM)
                            cv.put(r, c0 + 44, f"tilt {tilt:>+5.1%}", col)
            except Exception as e:
                cv.put(rot_r + 2, c0 + 1, f"Sector rotation signal unavailable: {e}", C_RED)


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
        system_state: SystemState | None = None,
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
        system_state: SystemState | None = None,
        ticks: int = 0,
    ) -> None:
        cols, rows = shutil.get_terminal_size()
        cv.put(r0, c0 + 1, "Platform Parameters", C_ACCENT + BOLD)
        cv.hline(r0 + 1, c0, c1)
        rows_data = [
            ("OS", sys.platform.upper()),
            ("Terminal", f"{cols}×{rows} cells"),
            ("Python", sys.version.split()[0]),
            ("IAM Core", "Available ✓" if _IAM_CORE else "Unavailable (mock mode)"),
            ("Sparklines", "iam.ui.sparklines ✓" if _IAM_SPARKLINES else "Built-in fallback"),
            ("Portfolio UI", "iam.portfolio ✓" if _IAM_PORTFOLIO else "Built-in fallback"),
            ("Active Ticker", sec.ticker if sec else "—"),
            ("Last Fetch", sec.last_updated.strftime("%H:%M:%S") if sec else "—"),
            ("Error State", (sec.error[:38] if sec and sec.error else "None")),
        ]
        for idx, (k, v) in enumerate(rows_data):
            r = r0 + 2 + idx * 2
            if r > r1 - 1:
                break
            v_col = (
                C_GREEN
                if "Available" in v or "✓" in v
                else C_RED
                if "Unavailable" in v or ("Error" in k and v != "None")
                else C_ACCENT
            )
            cv.put(r, c0 + 2, f"{k}:", C_DIM)
            cv.put(r, c0 + 22, v, v_col)

        cv.hline(r1 - 2, c0, c1)
        cv.put(r1 - 1, c0 + 1, "Press [R] to force-reload the active security.", C_DIM)


# ── Terrain & Topology ───────────────────────────────────────────────────


class TerrainPanel(_Panel):
    title = "VALUATION TERRAIN & TOPOLOGY"

    def render(
        self,
        cv: Canvas,
        r0: int,
        r1: int,
        c0: int,
        c1: int,
        sec: SecState | None,
        system_state: SystemState | None = None,
        ticks: int = 0,
    ) -> None:
        if not sec:
            return
        if sec.loading or not sec.terrain_render:
            self._loading(cv, r0, r1, c0, c1, sec.ticker, ticks)
            return

        # Render cached terrain surface
        lines = sec.terrain_render.split("\n")
        for i, line in enumerate(lines):
            if r0 + i > r1 - 6:
                break
            cv.put(r0 + i, c0 + 1, line, C_WHITE)

        # Draw topology metrics
        topo = sec.topology_metrics
        if topo:
            sep = r0 + len(lines)
            if sep > r1 - 4:
                sep = r1 - 5
            cv.hline(sep, c0, c1)
            cv.put(sep + 1, c0 + 1, "TOPOLOGY ANALYTICS:", C_ACCENT + BOLD)
            cv.put(
                sep + 2, c0 + 2, f"Dominant Driver: {topo.get('dominant_driver', 'N/A')}", C_WHITE
            )
            cv.put(
                sep + 2,
                c0 + 35,
                f"Fragility: {topo.get('fragility_score', 0):.2f}",
                C_RED if topo.get("fragility_score", 0) > 0.7 else C_GREEN,
            )
            cv.put(
                sep + 3, c0 + 2, f"Stability Ratio: {topo.get('stability_score', 0):.2f}", C_TEAL
            )


# ── SOTP Tower ───────────────────────────────────────────────────────────


class SOTPTowerPanel(_Panel):
    title = "SUM-OF-THE-PARTS (SOTP) TOWER"

    def render(
        self,
        cv: Canvas,
        r0: int,
        r1: int,
        c0: int,
        c1: int,
        sec: SecState | None,
        system_state: SystemState | None = None,
        ticks: int = 0,
    ) -> None:
        if not sec:
            return
        if sec.loading:
            self._loading(cv, r0, r1, c0, c1, sec.ticker, ticks)
            return

        from iam.engine.damodaran import DamodaranEngine
        from iam.ui.sotp_tower import render_sotp_tower
        from iam.valuation.sotp import SOTP

        cv.put(r0, c0 + 1, "Segment Enterprise Value Composition", C_ACCENT + BOLD)
        cv.hline(r0 + 1, c0, c1)

        # Real segments only; no mock segments, no assumed leverage.
        segments = (getattr(sec.security, "qualitative", None) or {}).get("segments", [])
        if not segments:
            cv.put(r0 + 2, c0 + 2, f"SOTP tower: n/a (no segment data for {sec.ticker})", C_DIM)
            return
        try:
            d_e = _num(sec.security.balance_sheet.debt_to_equity)
        except Exception:
            d_e = None
        if d_e is None:
            cv.put(r0 + 2, c0 + 2, f"SOTP tower: n/a (no debt/equity for {sec.ticker})", C_DIM)
            return

        damodaran = DamodaranEngine()

        ke = damodaran.compute_cost_of_equity(segments, d_e)
        result = SOTP.compute(segments, ke)

        # Render ASCII tower
        tower = render_sotp_tower(result.segments)
        lines = tower.split("\n")
        for i, line in enumerate(lines):
            if r0 + 2 + i > r1 - 4:
                break
            cv.put(r0 + 2 + i, c0 + 2, line, C_WHITE)

        sep = r0 + 2 + len(lines)
        if sep > r1 - 3:
            sep = r1 - 3
        cv.hline(sep, c0, c1)
        cv.put(
            sep + 1, c0 + 2, f"Weighted Asset Beta: {result.weighted_unlevered_beta:.2f}", C_TEAL
        )
        cv.put(sep + 1, c0 + 35, f"Implied CoE (Ke): {ke:.2%}", C_GOLD)


# ── Switch Security ───────────────────────────────────────────────────────


class LearningPanel(_Panel):
    title = "LEARNING & GLOSSARY"

    def __init__(self) -> None:
        self.lm = _LearningModule() if _IAM_CORE else None
        self.current_concept: str | None = None
        self.mode = "glossary"  # glossary or quiz
        self.quiz_question: dict | None = None
        self.quiz_status: str | None = None  # None, "correct", "incorrect"
        self.quiz_selection: int | None = None
        self._next_concept()

    def _next_concept(self) -> None:
        import random

        if self.lm and hasattr(self.lm, "concepts") and self.lm.concepts:
            self.current_concept = random.choice(list(self.lm.concepts.keys()))
        else:
            # Fallback glossaries
            concepts = {
                "Probability of Backtest Overfitting (PBO)": {
                    "definition": "The probability that the strategy chosen as optimal in-sample will underperform in out-of-sample tests.",
                    "code_ref": "src/iam/backtest/overfitting.py",
                    "formula": "PBO = sum(rank(OOS_i) != rank(IS_i)) / N",
                },
                "Deflated Sharpe Ratio (DSR)": {
                    "definition": "Adjusts the Sharpe ratio downwards to account for the number of trials performed, the variance of the trials, and the non-normality of returns.",
                    "code_ref": "src/iam/backtest/multiple_testing.py",
                    "formula": "DSR = SR * adjusting_factor",
                },
            }
            self.current_concept = random.choice(list(concepts.keys()))
            if not self.lm:
                self.lm = MagicMock()
                self.lm.concepts = concepts

    def _start_quiz(self) -> None:
        self.mode = "quiz"
        self.quiz_status = None
        self.quiz_selection = None

        # Hardcoded sample CFA / Quant questions matching our domain
        questions = [
            {
                "question": "What does a high Probability of Backtest Overfitting (PBO) signify?",
                "options": [
                    "1. The backtest has exceptional predictive power.",
                    "2. The optimal in-sample strategy is likely to perform poorly out-of-sample.",
                    "3. The multiple testing correction is too conservative.",
                    "4. The portfolio weights are close to the target benchmark.",
                ],
                "correct": 2,
                "explain": "High PBO implies the strategy's parameters fit the in-sample noise, meaning OOS returns are likely to be poor.",
            },
            {
                "question": "Which adjustment corrects the Sharpe Ratio for selection bias (multiple tests)?",
                "options": [
                    "1. Walk-forward optimization.",
                    "2. Deflated Sharpe Ratio (DSR).",
                    "3. Information Coefficient (IC).",
                    "4. Bottom-up beta adjustment.",
                ],
                "correct": 2,
                "explain": "DSR explicitly deflates the Sharpe ratio based on the total number of trial strategies evaluated.",
            },
            {
                "question": "What is the primary benefit of Combinatorial Purged Cross-Validation (CPCV)?",
                "options": [
                    "1. It increases in-sample Sharpe ratio.",
                    "2. It simulates multiple OOS backtesting paths while preventing overlap leakage.",
                    "3. It neutralizes sector exposure automatically.",
                    "4. It caps perpetuity terminal growth.",
                ],
                "correct": 2,
                "explain": "CPCV divides historical data into subsets and constructs multiple valid OOS backtesting paths.",
            },
        ]
        import random

        self.quiz_question = random.choice(questions)

    def _answer_quiz(self, opt: int) -> None:
        if not self.quiz_question:
            return
        self.quiz_selection = opt
        if opt == self.quiz_question["correct"]:
            self.quiz_status = "correct"
        else:
            self.quiz_status = "incorrect"

    def render(
        self,
        cv: Canvas,
        r0: int,
        r1: int,
        c0: int,
        c1: int,
        sec: SecState | None,
        system_state: SystemState | None = None,
        ticks: int = 0,
    ) -> None:
        if self.mode == "glossary":
            cv.put(
                r0 + 1, c0 + 2, "Educational & Reference Material (Glossary Mode)", C_GOLD + BOLD
            )

            if self.current_concept and self.lm:
                data = self.lm.concepts.get(self.current_concept, {})
                cv.put(r0 + 3, c0 + 2, f"Concept: {self.current_concept}", C_WHITE + BOLD)

                def_text = data.get("definition", "")
                words = def_text.split()
                lines = []
                cur_line = ""
                for w in words:
                    if len(cur_line) + len(w) + 1 < (c1 - c0 - 4):
                        cur_line += w + " "
                    else:
                        lines.append(cur_line)
                        cur_line = w + " "
                if cur_line:
                    lines.append(cur_line)

                for i, line in enumerate(lines):
                    if r0 + 5 + i > r1 - 7:
                        break
                    cv.put(r0 + 5 + i, c0 + 2, line, C_WHITE)

                end_r = r0 + 5 + len(lines)
                cv.put(end_r + 1, c0 + 2, "Code Reference:", C_DIM)
                cv.put(end_r + 2, c0 + 2, data.get("code_ref", "N/A"), C_ACCENT)

                if "formula" in data:
                    cv.put(end_r + 4, c0 + 2, "Formula:", C_DIM)
                    cv.put(end_r + 5, c0 + 2, data["formula"], C_WHITE)

            cv.hline(r1 - 2, c0, c1)
            cv.put(
                r1 - 1,
                c0 + 1,
                "Press [C] for another concept  │  Press [G] to start CFA / Quant Quiz",
                C_DIM,
            )
        else:
            # Quiz Mode
            cv.put(r0 + 1, c0 + 2, "CFA & Quant Finance Quiz Subsystem", C_GOLD + BOLD)
            if self.quiz_question:
                cv.put(r0 + 3, c0 + 2, self.quiz_question["question"], C_WHITE + BOLD)
                for idx, opt in enumerate(self.quiz_question["options"]):
                    row = r0 + 5 + idx * 2
                    style = C_WHITE
                    if self.quiz_selection == (idx + 1):
                        style = C_GOLD + BOLD
                    cv.put(row, c0 + 4, opt, style)

                if self.quiz_status:
                    stat_r = r0 + 13
                    cv.hline(stat_r, c0, c1)
                    if self.quiz_status == "correct":
                        cv.put(stat_r + 1, c0 + 2, "✓ CORRECT", C_GREEN + BOLD)
                    else:
                        cv.put(
                            stat_r + 1,
                            c0 + 2,
                            f"✗ INCORRECT (Correct: {self.quiz_question['correct']})",
                            C_RED + BOLD,
                        )

                    cv.put(
                        stat_r + 2, c0 + 2, f"Explanation: {self.quiz_question['explain']}", C_WHITE
                    )

            cv.hline(r1 - 2, c0, c1)
            cv.put(
                r1 - 1,
                c0 + 1,
                "Press [1-4] to select answer  │  Press [G] to load next question  │  Press [Esc] to exit quiz",
                C_DIM,
            )


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
        system_state: SystemState | None = None,
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
#  TI-89 PROJECTION PANEL
# ═══════════════════════════════════════════════════════════════════════════


class TI89Panel(_Panel):
    title = "TI-89 3D VALUATION PROJECTION"

    def render(
        self,
        cv: Canvas,
        r0: int,
        r1: int,
        c0: int,
        c1: int,
        sec: SecState | None,
        system_state: SystemState | None = None,
        ticks: int = 0,
    ) -> None:
        if sec and self._load_failed(cv, r0, r1, c0, c1, sec):
            return
        if not sec or not sec.pipeline_result:
            self._loading(cv, r0, r1, c0, c1, sec.ticker if sec else "N/A", ticks)
            return

        from iam.ui.ti89_graph import LEGEND, render_ti89_map
        from iam.valuation.value_grid import build_value_grid

        grid = build_value_grid(sec.pipeline_result)
        cv.put(
            r0 + 1,
            c0 + 2,
            "VALUATION MAP: value/share by growth (x) and discount rate (y)",
            C_ACCENT + BOLD,
        )
        if grid is None:
            cv.put(r0 + 3, c0 + 2, "n/a: needs an FCFE build-up (earnings, shares, price).", C_DIM)
            return

        lines = render_ti89_map(grid)
        for i, line in enumerate(lines):
            if r0 + 3 + i >= r1 - 3:
                break
            # Dark blue on grey-green, like a TI-89 LCD.
            cv.put(r0 + 3 + i, c0 + 2, line, "\x1b[38;2;0;0;139m\x1b[48;2;143;159;143m")
        foot = r0 + 4 + len(lines)
        if foot < r1:
            cv.put(foot, c0 + 2, LEGEND[: c1 - c0 - 4], C_DIM)
        if foot + 1 < r1:
            mk = "  M = market-implied" if grid.market else ""
            ref = f"price ${grid.price:,.2f}" if grid.price else f"our base ${grid.base[2]:,.2f}"
            cv.put(
                foot + 1,
                c0 + 2,
                f"B = our base (${grid.base[2]:,.2f}){mk}   reference: {ref}",
                C_DIM,
            )
        lines = lines + ["", ""]

        # Add ML Lens status if possible
        try:
            from iam.ml.ml_lens import MLDiagnosticLens

            lens = MLDiagnosticLens()
            res = lens.compute(sec.security) if hasattr(sec, "security") else None
            if res and r0 + 4 + len(lines) < r1:
                col = "\x1b[31m" if res.confidence < 1.0 else "\x1b[32m"
                cv.put(r0 + 4 + len(lines), c0 + 2, f"ML Diagnostics: {res.narrative}", col)
        except Exception:
            pass

        # Add Plugin status
        try:
            from iam.plugins.manager import PluginManager

            pm = PluginManager()
            plugins = pm.list_plugins() if hasattr(pm, "list_plugins") else []
            if r0 + 6 + len(lines) < r1:
                cv.put(r0 + 6 + len(lines), c0 + 2, f"Active Plugins: {len(plugins)}", C_DIM)
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN APPLICATION
# ═══════════════════════════════════════════════════════════════════════════


class AlphaTerminal:
    MENU_ITEMS: list[str] = [
        "Watchlist",
        "Global Markets",  # NEW
        "Quick Recommendation",
        "Deep Dive Valuation",
        "Expectations Battlefield",  # NEW
        "Reverse DCF Distribution",  # NEW
        "Valuation Fragility",  # NEW
        "Lens Arbitration",  # NEW
        "Thesis Drift",  # NEW
        "Valuation Terrain",
        "SOTP Tower",
        "Factor Scoring",
        "Scenario & Thesis",
        "Backtest Efficacy",
        "Portfolio Overview",
        "Learning & Glossary",
        "Matrix Digital Rain",
        "TI-89 3D Projection",
        "Settings",  # NEW
        "System Info",
        "Switch Security",
        "─────────────────",
        "Exit",
    ]

    DEFAULT_WATCHLIST = ["TSLA", "MSFT", "AAPL", "NVDA", "META"]

    def __init__(self) -> None:
        self._cfg = get_settings()

        # Apply display settings to the shared widget layer
        W.configure(
            theme=self._cfg.display.theme,
            color_mode=self._cfg.terminal.color_mode,
            unicode_enabled=self._cfg.terminal.unicode_enabled,
        )
        # Apply market-data cache TTLs
        MKT.configure(
            quote_ttl=self._cfg.market_data.quote_ttl_seconds,
            macro_ttl=self._cfg.market_data.macro_ttl_seconds,
        )

        self._active = self._cfg.display.default_ticker
        self._watchlist = list(self._cfg.display.watchlist)
        self._menu_idx = 0
        self._secs: dict[str, SecState] = {}
        self._sys = SystemState() if _IAM_STATE else None
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=self._cfg.async_config.max_workers)
        self._running = False
        self._canvas: Canvas | None = None
        self._ticks = 0

        self._panels: dict[str, _Panel] = {
            "Watchlist": RealWatchlistPanel(self._watchlist, sec_lookup=self._get_sec),
            "Global Markets": GlobalMarketsPanel(),
            "Quick Recommendation": QuickRecPanel(),
            "Deep Dive Valuation": DeepValPanel(),
            "Expectations Battlefield": ExpectationsBattlefieldPanel(),
            "Reverse DCF Distribution": ReverseDCFDistributionPanel(),
            "Valuation Fragility": FragilityMapPanel(),
            "Lens Arbitration": ArbitrationVisualizerPanel(),
            "Thesis Drift": ThesisDriftPanel(),
            "Valuation Terrain": TerrainPanel(),
            "SOTP Tower": SOTPTowerPanel(),
            "Factor Scoring": FactorPanel(),
            "Scenario & Thesis": ScenarioPanel(),
            "Backtest Efficacy": BacktestPanel(),
            "Portfolio Overview": PortfolioPanel(sec_lookup=self._get_sec),
            "Learning & Glossary": LearningPanel(),
            "Matrix Digital Rain": MatrixPanel(),
            "TI-89 3D Projection": TI89Panel(),
            "Settings": SettingsPanel(on_apply=self._apply_settings),
            "System Info": SysInfoPanel(),
            "Switch Security": SwitchPanel(),
        }

        atexit.register(self._teardown)

    def _get_sec(self, ticker: str) -> SecState | None:
        with self._lock:
            return self._secs.get(ticker)

    def _apply_settings(self, cfg: Any = None) -> None:
        self._cfg = get_settings()
        W.configure(
            theme=self._cfg.display.theme,
            color_mode=self._cfg.terminal.color_mode,
            unicode_enabled=self._cfg.terminal.unicode_enabled,
        )
        if self._canvas:
            self._canvas._dirty = True

    def start(self) -> None:
        if sys.platform == "win32":
            os.system("")
            try:
                sys.stdout.reconfigure(encoding="utf-8")  # type: ignore
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
        # Load global system data (Portfolio, Backtest)
        self._async_load_system()
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
            elif arrow in [b"K", b"M"]:
                # Intercept for Settings/Terrain panels
                if self.MENU_ITEMS[self._menu_idx] in ["Settings", "Valuation Terrain"]:
                    panel = self._panels[self.MENU_ITEMS[self._menu_idx]]
                    if hasattr(panel, "_handle_key"):
                        panel._handle_key(arrow)
                        if self._canvas:
                            self._canvas._dirty = True
        elif key == b"\x1b":
            nxt = _getch_nowait()
            if nxt is None:
                # Check if we can intercept Esc key for the Quiz screen
                if self.MENU_ITEMS[self._menu_idx] == "Learning & Glossary":
                    panel = self._panels["Learning & Glossary"]
                    if getattr(panel, "mode", None) == "quiz":
                        panel.mode = "glossary"  # type: ignore
                        if self._canvas:
                            self._canvas._dirty = True
                        return
                self._quit()
                return
            if nxt == b"[":
                code = _getch_block()
                if code == b"A":
                    self._nav(-1)
                elif code == b"B":
                    self._nav(+1)
                elif code in [b"C", b"D"]:
                    # Intercept for Settings/Terrain panels
                    if self.MENU_ITEMS[self._menu_idx] in ["Settings", "Valuation Terrain"]:
                        panel = self._panels[self.MENU_ITEMS[self._menu_idx]]
                        if hasattr(panel, "_handle_key"):
                            panel._handle_key(code)
                            if self._canvas:
                                self._canvas._dirty = True
        elif key.lower() == b"q":
            self._quit()
        elif key.lower() == b"k":
            self._nav(-1)
        elif key.lower() == b"j":
            self._nav(+1)
        elif key.lower() == b"s":
            self._switch_flow()
        elif key.lower() == b"r":
            self._force_reload()
        elif key.lower() == b"c":
            if self.MENU_ITEMS[self._menu_idx] == "Learning & Glossary":
                panel = self._panels["Learning & Glossary"]
                if hasattr(panel, "_next_concept"):
                    panel._next_concept()
                if self._canvas:
                    self._canvas._dirty = True
        elif key.lower() == b"g":
            if self.MENU_ITEMS[self._menu_idx] == "Learning & Glossary":
                panel = self._panels["Learning & Glossary"]
                if hasattr(panel, "_start_quiz"):
                    panel._start_quiz()
                if self._canvas:
                    self._canvas._dirty = True
        elif key in (b"1", b"2", b"3", b"4"):
            if self.MENU_ITEMS[self._menu_idx] == "Learning & Glossary":
                panel = self._panels["Learning & Glossary"]
                if getattr(panel, "mode", None) == "quiz":
                    panel._answer_quiz(int(key.decode()))  # type: ignore
                    if self._canvas:
                        self._canvas._dirty = True
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

    def _async_load_system(self) -> None:
        """Trigger background loading of global system data (Portfolio, Backtest)."""
        if not self._sys:
            return
        with self._lock:
            self._sys.loading = True
        self._executor.submit(self._system_worker)

    def _system_worker(self) -> None:
        """Background worker for portfolio and backtest analytics."""
        try:
            import pandas as pd

            from iam.backtest.multiple_testing import compute_validation_metrics
            from iam.engine.composite import DEFAULT_WEIGHTS
            from iam.portfolio import Portfolio, Position

            # 1. Equal-weight MODEL portfolio of the watchlist. There is no
            # holdings data source, so quantity/cost basis are not modelled:
            # quantity is 0 and entry == current price (no P&L, no value).
            with self._lock:
                watchlist = list(self._watchlist)[:8]

            positions = []
            for tkr in watchlist:
                # Reuse real data only if this ticker was already fetched
                # (loaded SecState, else the cached market quote).
                with self._lock:
                    loaded = self._secs.get(tkr)
                real_sector = (
                    loaded.security.sector
                    if loaded and loaded.security and getattr(loaded.security, "sector", None)
                    else None
                )
                price = loaded.price if loaded else None
                if price is None:
                    q = MKT.get_quote(tkr, refresh=False)
                    if q is not None and q.last is not None and not q.stale:
                        price = float(q.last)
                px = price if price is not None else 0.0  # 0.0 == unknown, shown as n/a
                band = (loaded.confidence if loaded else "").upper()
                if band == "HIGH":
                    conviction = "HIGH"
                elif band in ("MEDIUM", "MODERATE"):
                    conviction = "MODERATE"
                elif band == "LOW":
                    conviction = "LOW"
                else:
                    conviction = "UNRATED"
                positions.append(
                    Position(
                        ticker=tkr,
                        name=tkr,
                        quantity=0.0,
                        entry_price=px,
                        current_price=px,
                        weight=1.0 / len(watchlist),
                        sector=real_sector,
                        conviction=conviction,
                    )
                )
            portfolio = Portfolio(positions=positions)

            # 2. Load Backtest Results
            backtest_metrics = None
            csv_path = "data/results/ic/ic_horizon_1m.csv"
            if os.path.exists(csv_path):
                df = pd.read_csv(csv_path)
                backtest_metrics = compute_validation_metrics(df, list(DEFAULT_WEIGHTS.keys()))

            with self._lock:
                if self._sys:
                    self._sys.portfolio = portfolio
                    self._sys.backtest_metrics = backtest_metrics
                    self._sys.loading = False
                    self._sys.last_updated = datetime.now()
                    self._sys.error = None
        except Exception as e:
            with self._lock:
                if self._sys:
                    self._sys.loading = False
                    self._sys.error = str(e)

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
                import numpy as np

                sec = _fetch_security(ticker)
                sr = _score(sec)
                pr = _Pipeline().run(sec)
                hist = self._real_history(ticker, sec)

                # Phase 2: Background Terrain Generation
                cols, rows = shutil.get_terminal_size()
                tw = max(40, cols - MENU_W - 5)
                th = max(12, rows - HDR_ROWS - FTR_ROWS - 10)
                terrain = _render_dcf_surface(sec, width=tw, height=th, report=pr)

                # Topology Metrics
                dcf_surface = DCFValuationSurface(sec, report=pr)
                z_grid = dcf_surface.generate_z_grid()
                g_steps = np.linspace(
                    dcf_surface.x_min, dcf_surface.x_max, dcf_surface.grid_size
                ).tolist()
                m_steps = np.linspace(
                    dcf_surface.y_min, dcf_surface.y_max, dcf_surface.grid_size
                ).tolist()
                topo = _compute_gradients(z_grid, g_steps, m_steps)

                with self._lock:
                    st = self._secs[ticker]
                    st.security = sec
                    st.score_result = sr
                    st.pipeline_result = pr
                    st.history = hist
                    st.terrain_render = terrain
                    st.topology_metrics = topo
                    st.loading = False
                    st.last_updated = datetime.now()
                    st.error = None
            else:
                self._mock_load(ticker)
        except Exception as e:
            if _IAM_CORE:
                # Real build: never substitute fake data. Leave the result
                # fields empty and surface the error instead.
                with self._lock:
                    st = self._secs.get(ticker)
                    if st is not None:
                        st.security = None
                        st.score_result = None
                        st.pipeline_result = None
                        st.history = []
                        st.loading = False
                        st.last_updated = datetime.now()
                        st.error = str(e) or type(e).__name__
            else:
                self._mock_load(ticker, error=str(e))

    @staticmethod
    def _real_history(ticker: str, sec: Any) -> list[float]:
        """Real intraday history; never synthesised. Blocking (worker thread)."""
        try:
            q = MKT._fetch_one(ticker, want_history=True)
            if q is not None and not q.stale and q.history:
                return [float(h) for h in q.history]
        except Exception:
            pass
        try:
            p = sec.market.price
            return [float(p)] if p else []
        except Exception:
            return []

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
        """Refresh the active price from the real (cached) quote. Never simulates."""
        with self._lock:
            st = self._secs.get(self._active)
            if not st or st.loading or not st.security or st.is_demo:
                return
            try:
                q = MKT.get_quote(self._active)
                if q is None or q.stale or q.last is None:
                    return
                new_price = float(q.last)
                if st.security.market.price != new_price:
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
        print(
            f"{V1}  Enter a ticker symbol or company name (e.g. 'Apple' or 'AAPL'):".ljust(bw + 1)
            + V1
        )
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
        print("\n  Press any key to return...")
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
        print("\n  Press any key...")
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
        if cv is None:
            raise ValueError("cv cannot be None")
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
            self._secs.get(self._active)

        # New Ribbon
        render_ribbon(cv, 1, w, self._ticks)
        cv.put(1, 0, V2, C_ACCENT)
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
            sys_state = self._sys

        # Pass ticks so loading spinners can animate
        panel.render(cv, r0 + 2, r1, c0, c1, sec, sys_state, self._ticks)


# ═══════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════


def main():
    terminal = AlphaTerminal()
    terminal.start()


if __name__ == "__main__":
    main()
