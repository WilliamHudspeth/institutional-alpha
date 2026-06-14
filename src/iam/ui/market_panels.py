"""Market-data panels for the Alpha Terminal.

* :class:`GlobalMarketsPanel` — US / Europe / Asia indices, the rates curve, FX
  & commodities, and a macro-regime read-out.
* :class:`RealWatchlistPanel` — drop-in replacement for the simulated
  ``WatchlistPanel``; shows real quotes for *every* row plus the model's rating
  and composite score when loaded (a valuation-aware tape).
* :func:`render_ribbon` — the always-on scrolling market tape for the header.

All panels match the existing ``_Panel.render`` signature and draw through the
Canvas API (``cv.put`` / ``cv.hline`` / ``cv.box``).
"""

from __future__ import annotations

from iam.data import markets as mkt
from iam.ui import widgets as w


# ─────────────────────────────────────────────────────────────────────────────
class GlobalMarketsPanel:
    title = "GLOBAL MARKETS"

    def render(self, cv, r0, r1, c0, c1, sec=None, system_state=None, ticks=0) -> None:
        snap = mkt.get_snapshot()
        width = c1 - c0
        if snap is None:
            cv.put(r0 + 1, c0 + 2, "Fetching global market tape…", w.C_DIM())
            return

        stale = " (stale)" if snap.stale else ""
        ts = snap.updated.astimezone().strftime("%H:%M:%S")
        sess = mkt.session_label()
        sess_col = w.C_GREEN() if "OPEN" in sess else w.C_DIM()
        cv.put(r0, c0 + 1, f"{sess}", sess_col + w.BOLD)
        cv.put(r0, c0 + 14, f"updated {ts}{stale}", w.C_DIM())

        # Two columns of regional index blocks.
        col_w = max(34, width // 2 - 2)
        left_x = c0 + 1
        right_x = c0 + col_w + 2
        row = r0 + 2

        self._region(cv, "UNITED STATES", snap.group("US"), row, left_x, col_w)
        self._region(cv, "EUROPE", snap.group("EUROPE"), row, right_x, col_w)
        row2 = row + 6
        self._region(cv, "ASIA", snap.group("ASIA"), row2, left_x, col_w)
        self._fx_block(cv, snap, row2, right_x, col_w)

        # Rates strip + curve sparkline across the bottom.
        rate_row = row2 + 6
        if rate_row < r1 - 3:
            self._rates(cv, snap, rate_row, c0 + 1, width - 2)

        # Macro-regime read-out (ties live data to the macro_regime factor).
        regime_row = r1 - 2
        self._regime(cv, snap, regime_row, c0 + 1, width - 2)

    # ── helpers ──────────────────────────────────────────────────────────────
    def _region(self, cv, title, quotes, row, x, col_w) -> None:
        cv.put(row, x, title, w.C_ACCENT() + w.BOLD)
        cv.hline(row + 1, x, x + col_w, style=w.C_DIM())
        for i, q in enumerate(quotes[:4]):
            r = row + 2 + i
            chg = q.change_pct
            arrow = w.up_arrow() if (chg or 0) >= 0 else w.down_arrow()
            col = w.delta_color(chg)
            cv.put(r, x, f"{q.label:<14}", w.C_WHITE())
            cv.put(r, x + 14, f"{w.fmt_num(q.last):>9}", w.C_WHITE())
            cv.put(r, x + 24, f"{arrow}{w.fmt_pct(chg)}", col)

    def _fx_block(self, cv, snap, row, x, col_w) -> None:
        cv.put(row, x, "FX · COMMODITIES · VOL", w.C_ACCENT() + w.BOLD)
        cv.hline(row + 1, x, x + col_w, style=w.C_DIM())
        rows = snap.group("FX_COMMODITIES")[:3] + snap.group("VOL")[:1]
        for i, q in enumerate(rows[:4]):
            r = row + 2 + i
            chg = q.change_pct
            arrow = w.up_arrow() if (chg or 0) >= 0 else w.down_arrow()
            col = w.delta_color(chg)
            cv.put(r, x, f"{q.label:<14}", w.C_WHITE())
            cv.put(r, x + 14, f"{w.fmt_num(q.last):>9}", w.C_WHITE())
            cv.put(r, x + 24, f"{arrow}{w.fmt_pct(chg)}", col)

    def _rates(self, cv, snap, row, x, width) -> None:
        cv.put(row, x, "US TREASURY CURVE", w.C_ACCENT() + w.BOLD)
        cv.hline(row + 1, x, x + width, style=w.C_DIM())
        curve = snap.rate_curve()
        cx = x
        for label, y in curve:
            q = next((q for q in snap.group("RATES") if q.label == label), None)
            bps = q.change_bps if q else None
            seg = f"{label} {y:.2f}%"
            cv.put(row + 2, cx, seg, w.C_WHITE())
            if bps is not None:
                bcol = w.C_GREEN() if bps >= 0 else w.C_RED()
                cv.put(row + 2, cx + len(seg) + 1, f"{bps:+.0f}bp", bcol)
            cx += len(seg) + 9
        # curve shape sparkline
        spark = w.yield_curve(curve, width=min(28, width - 2))
        cv.put(row + 3, x, "shape ", w.C_DIM())
        cv.put(row + 3, x + 6, spark, w.C_TEAL())

    def _regime(self, cv, snap, row, x, width) -> None:
        ten = snap.get("^TNX")
        vix = snap.get("^VIX")
        spx = snap.get("^GSPC")
        bits = []
        if ten and ten.last is not None:
            bits.append(("10Y", f"{ten.last:.2f}%", w.C_WHITE()))
        if vix and vix.last is not None:
            vcol = w.C_RED() if vix.last > 20 else w.C_GREEN() if vix.last < 15 else w.C_YELLOW()
            bits.append(("VIX", f"{vix.last:.1f}", vcol))
        # Simple risk regime read
        regime = "NEUTRAL"
        rcol = w.C_YELLOW()
        if vix and vix.last is not None:
            if vix.last < 15 and (spx.change_pct or 0) >= 0 if spx else False:
                regime, rcol = "RISK-ON", w.C_GREEN()
            elif vix.last > 22:
                regime, rcol = "RISK-OFF", w.C_RED()
        cv.put(row, x, "REGIME: ", w.C_DIM())
        cx = x + 8
        cv.put(row, cx, regime, rcol + w.BOLD)
        cx += len(regime) + 3
        for k, v, col in bits:
            cv.put(row, cx, f"{k} ", w.C_DIM())
            cx += len(k) + 1
            cv.put(row, cx, v, col)
            cx += len(v) + 3


# ─────────────────────────────────────────────────────────────────────────────
class RealWatchlistPanel:
    """Real-quote watchlist with model rating + composite score per row."""

    title = "LIVE WATCHLIST"

    def __init__(self, watchlist, sec_lookup=None) -> None:
        """``sec_lookup`` is a callable ``ticker -> SecState | None`` so each row
        can show the model verdict/score without coupling to terminal internals.
        """
        self._wl = watchlist
        self._sec_lookup = sec_lookup or (lambda _t: None)

    def render(self, cv, r0, r1, c0, c1, sec=None, system_state=None, ticks=0) -> None:
        header = f"{'TICKER':<6} {'LAST':>9} {'CHG':>8}  {'RATING':<10} {'SCORE':>5}  SPARK"
        cv.put(r0, c0 + 1, header, w.C_DIM())
        cv.hline(r0 + 1, c0, c1, style=w.C_DIM())

        for idx, tkr in enumerate(self._wl):
            r = r0 + 2 + idx
            if r > r1 - 1:
                break
            active = sec and getattr(sec, "ticker", None) == tkr
            base_style = (w.C_GOLD() + w.BOLD) if active else w.C_WHITE()
            prefix = (w.flat_arrow() + " ") if active else "  "

            q = mkt.get_quote(tkr)
            st = self._sec_lookup(tkr)

            last = q.last if q else None
            chg = q.change_pct if q else None
            hist = q.history if (q and q.history) else []

            arrow = w.up_arrow() if (chg or 0) >= 0 else w.down_arrow()
            d_col = w.delta_color(chg)

            cv.put(r, c0, prefix, base_style)
            cv.put(r, c0 + 2, f"{tkr:<6}", base_style)
            cv.put(r, c0 + 9, f"{w.fmt_num(last):>9}", w.C_WHITE())
            cv.put(r, c0 + 19, f"{arrow}{w.fmt_pct(chg)}", d_col)

            # Model verdict + composite score, if this ticker has been valued.
            rating = getattr(st, "rating", None) if st else None
            comp = getattr(st, "composite", None) if st else None
            if rating and rating not in ("N/A", "—"):
                cv.put(r, c0 + 30, f"{rating:<10}", w.rating_color(rating))
            else:
                cv.put(r, c0 + 30, f"{'—':<10}", w.C_DIM())
            if comp is not None:
                cv.put(r, c0 + 41, f"{int((comp + 1) * 50):>4}", w.value_color(comp))
            # sparkline
            if hist:
                cv.put(r, c0 + 48, w.spark_line(hist, max(8, c1 - (c0 + 50))), d_col)

        cv.hline(r1 - 1, c0, c1, style=w.C_DIM())
        flag = " (mock/stale data)" if (mkt.get_snapshot() and mkt.get_snapshot().stale) else ""
        cv.put(
            r1 - 1,
            c0 + 1,
            f"[W] add  ·  [S] switch  ·  real quotes via market layer{flag}",
            w.C_DIM(),
        )


# ─────────────────────────────────────────────────────────────────────────────
def render_ribbon(cv, row: int, cols: int, ticks: int, cycle_frames: int = 125) -> None:
    """Draw the scrolling market ribbon on ``row`` (the header tape).

    Cycles through region groups so the whole tape fits any width.  Call from
    ``_draw_header``; ``ticks`` is the terminal's frame counter.
    """
    snap = mkt.get_snapshot()
    if snap is None:
        cv.put(row, 1, "  Loading market tape…", w.C_DIM())
        return

    groups = ["US", "EUROPE", "ASIA", "RATES", "FX_COMMODITIES"]
    gi = (ticks // max(1, cycle_frames)) % len(groups)
    group = groups[gi]
    label = {"FX_COMMODITIES": "FX/CMDTY"}.get(group, group)

    cv.put(row, 1, f" {label} ", w.C_ACCENT() + w.BOLD)
    x = 1 + len(label) + 3
    sep = " │ " if w._UNICODE else " | "

    for q in snap.group(group):
        if x > cols - 14:
            break
        if q.is_rate:
            val = f"{q.last:.2f}%" if q.last is not None else "—"
            chg = q.change_bps
            chg_s = f"{chg:+.0f}bp" if chg is not None else ""
        else:
            val = w.fmt_num(q.last)
            chg = q.change_pct
            chg_s = w.fmt_pct(chg) if chg is not None else ""
        col = w.delta_color(q.change_pct if not q.is_rate else q.change)
        arrow = w.up_arrow() if (q.change or 0) >= 0 else w.down_arrow()
        seg = f"{q.label} {val} {arrow}{chg_s}"
        cv.put(row, x, seg, col)
        x += len(seg)
        cv.put(row, x, sep, w.C_DIM())
        x += len(sep)
