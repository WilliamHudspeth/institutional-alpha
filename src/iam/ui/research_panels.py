"""Research-grade analytic panels for the Alpha Terminal.

These surface engine outputs that previously only appeared in verbose console
logs.  Each binds to fields already produced by the pipeline / topology layers
and degrades gracefully when a given block is missing.

* :class:`ExpectationsBattlefieldPanel` — our vs market-implied assumptions and
  how much each one moves value (which input explains the gap). [report.battlefield]
* :class:`ReverseDCFDistributionPanel` — market-implied growth placed against our
  bear/base/bull scenario growth.     [report.market_implied_engine, report.intrinsic]
* :class:`FragilityMapPanel` — sensitivity / stability read from the valuation
  topology, with a SAFE↔DANGEROUS position bar.                 [sec.topology_metrics]
* :class:`ArbitrationVisualizerPanel` — per-lens fair values and their influence
  on the consensus.                                  [report.intrinsic/relative/...]
* :class:`ThesisDriftPanel` — registered-thesis breaches and confidence decay.
                                                                [report.drift_report]
"""

from __future__ import annotations

from iam.pipeline.battlefield import PARAM_LABELS
from iam.ui import widgets as w


def _report(sec):
    return getattr(sec, "pipeline_result", None) if sec else None


def _need_data(cv, r0, c0, msg="No valuation loaded — press [R] to run.") -> None:
    cv.put(r0 + 1, c0 + 2, msg, w.C_DIM())


# ─────────────────────────────────────────────────────────────────────────────
class ExpectationsBattlefieldPanel:
    title = "EXPECTATIONS BATTLEFIELD"

    def render(self, cv, r0, r1, c0, c1, sec=None, system_state=None, ticks=0) -> None:
        rpt = _report(sec)
        bf = getattr(rpt, "battlefield", None) if rpt else None
        if bf is None:
            _need_data(cv, r0, c0, "Battlefield needs a reverse DCF and an FCFE build-up.")
            return
        width = c1 - c0
        lx = c0 + 1

        cv.put(r0, lx, "KEY DISAGREEMENT: ", w.C_DIM())
        cv.put(r0, lx + 18, str(getattr(bf, "key_disagreement", "") or "—"), w.C_GOLD() + w.BOLD)
        cv.hline(r0 + 1, c0, c1, style=w.C_DIM())

        contributions = list(getattr(bf, "contributions", None) or [])
        if not contributions:
            notes = list(getattr(bf, "notes", None) or [])
            cv.put(
                r0 + 2,
                lx,
                (notes[0] if notes else "No shared parameters to compare.")[: width - 2],
                w.C_DIM(),
            )
            return

        cv.put(
            r0 + 2,
            lx,
            f"{'ASSUMPTION':<19}{'OURS':>8}{'MARKET':>9}{'VALUE Δ/sh':>12}",
            w.C_ACCENT() + w.BOLD,
        )
        bar_x = lx + 50
        bar_w = max(6, c1 - bar_x - 6)
        for i, c in enumerate(contributions):
            r = r0 + 3 + i
            if r >= r1 - 2:
                break
            label = PARAM_LABELS.get(c.parameter, c.parameter)
            cv.put(r, lx, f"{label:<19}", w.C_WHITE())
            cv.put(r, lx + 19, f"{w.fmt_pct(c.value_intrinsic, 2, signed=False):>8}", w.C_GREEN())
            cv.put(r, lx + 27, f"{w.fmt_pct(c.value_market, 2, signed=False):>9}", w.C_RED())
            cv.put(r, lx + 36, f"{c.delta_value:>+12.2f}", w.value_color(c.delta_value))
            if bar_x + bar_w < c1:
                cv.put(r, bar_x, w.hbar(c.share, bar_w), w.C_TEAL())
                cv.put(r, bar_x + bar_w + 1, f"{c.share * 100:3.0f}%", w.C_DIM())

        gap = getattr(bf, "value_gap_pct", None)
        if gap is not None and r1 - 1 > r0 + 3 + len(contributions):
            cv.hline(r1 - 2, c0, c1, style=w.C_DIM())
            cv.put(r1 - 1, lx, "Market-implied value vs ours: ", w.C_DIM())
            cv.put(r1 - 1, lx + 30, w.fmt_pct(gap), w.value_color(gap) + w.BOLD)
            cv.put(
                r1 - 1,
                lx + 40,
                "(Δ = value change if only that input moved to market's)",
                w.C_DIM(),
            )


# ─────────────────────────────────────────────────────────────────────────────
class ReverseDCFDistributionPanel:
    title = "REVERSE DCF — IMPLIED vs INTRINSIC"

    def render(self, cv, r0, r1, c0, c1, sec=None, system_state=None, ticks=0) -> None:
        """Market-implied growth placed against our own bear/base/bull growth.

        Every point drawn is a real engine output: the reverse-DCF implied
        growth and the FCFE scenario matrix (growth and probability).
        """
        rpt = _report(sec)
        mie = getattr(rpt, "market_implied_engine", None) if rpt else None
        implied = getattr(mie, "implied", None) if mie else None
        mkt_g = getattr(implied, "implied_revenue_growth", None) if implied else None
        intrinsic = getattr(rpt, "intrinsic", None) if rpt else None
        comps = getattr(intrinsic, "components", None) if intrinsic else None
        scenarios = comps.get("scenarios") if isinstance(comps, dict) else None
        if not isinstance(mkt_g, int | float) or not isinstance(scenarios, dict) or not scenarios:
            _need_data(cv, r0, c0, "Needs reverse-DCF implied growth and FCFE scenarios.")
            return

        rows = []
        for name, data in scenarios.items():
            g = data.get("g") if isinstance(data, dict) else None
            prob = data.get("prob") if isinstance(data, dict) else None
            if isinstance(g, int | float):
                rows.append((str(name), float(g), prob))
        if not rows:
            _need_data(cv, r0, c0, "FCFE scenarios carry no growth rates.")
            return
        rows.sort(key=lambda t: t[1])
        rows_all = rows + [("Market-implied", float(mkt_g), None)]

        lo = min(g for _, g, _ in rows_all)
        hi = max(g for _, g, _ in rows_all)
        span = (hi - lo) or 0.01
        label_w = 16
        axis_x = c0 + 1 + label_w + 8
        axis_w = max(10, c1 - axis_x - 2)

        def pos(g: float) -> int:
            return int(axis_x + round((g - lo) / span * (axis_w - 1)))

        cv.put(r0, c0 + 1, "GROWTH: OUR SCENARIOS vs MARKET-IMPLIED", w.C_ACCENT() + w.BOLD)
        cv.hline(r0 + 1, c0, c1, style=w.C_DIM())
        for i, (name, g, prob) in enumerate(rows_all):
            r = r0 + 2 + i
            if r >= r1 - 2:
                break
            is_mkt = prob is None
            col = w.C_RED() if is_mkt else w.C_GREEN()
            tag = "" if is_mkt else f" {prob * 100:.0f}%" if isinstance(prob, int | float) else ""
            cv.put(r, c0 + 1, f"{(name + tag)[:label_w]:<{label_w}}", col)
            cv.put(r, c0 + 1 + label_w, f"{w.fmt_pct(g, 1, signed=False):>7}", w.C_WHITE())
            cv.put(r, axis_x, "·" * axis_w if w._UNICODE else "." * axis_w, w.C_DIM())
            cv.put(r, pos(g), "◆" if w._UNICODE else "*", col + w.BOLD)

        # Where does the market sit relative to our own range?
        bear, bull = rows[0][1], rows[-1][1]
        if mkt_g > bull:
            msg, col = "Market prices in MORE growth than our bull case.", w.C_RED()
        elif mkt_g < bear:
            msg, col = "Market prices in LESS growth than our bear case.", w.C_GREEN()
        else:
            msg, col = "Market-implied growth sits inside our scenario range.", w.C_YELLOW()
        cv.put(r1 - 1, c0 + 1, msg[: c1 - c0 - 2], col + w.BOLD)


# ─────────────────────────────────────────────────────────────────────────────
class FragilityMapPanel:
    title = "VALUATION FRAGILITY MAP"

    def render(self, cv, r0, r1, c0, c1, sec=None, system_state=None, ticks=0) -> None:
        topo = getattr(sec, "topology_metrics", None) if sec else None
        if not topo:
            _need_data(cv, r0, c0, "No topology computed — open a security first.")
            return
        width = c1 - c0

        fragility = float(topo.get("fragility_score", 0.0) or 0.0)
        stability = float(topo.get("stability_score", 1.0) or 0.0)
        gx = abs(float(topo.get("gradient_x_mean", 0.0) or 0.0))  # growth sensitivity
        gy = abs(float(topo.get("gradient_y_mean", 0.0) or 0.0))  # discount sensitivity
        cxv = abs(float(topo.get("curvature_x_mean", 0.0) or 0.0))
        dom = topo.get("dominant_driver", "—")

        cv.put(r0, c0 + 1, "SENSITIVITY ANALYSIS", w.C_ACCENT() + w.BOLD)
        cv.hline(r0 + 1, c0, c1, style=w.C_DIM())

        # Normalize the gradients to qualitative buckets.
        def bucket(v, scale):
            x = v / scale if scale else 0.0
            if x > 1.2:
                return "EXTREME", w.C_RED()
            if x > 0.7:
                return "HIGH", w.C_RED()
            if x > 0.35:
                return "MEDIUM", w.C_YELLOW()
            return "LOW", w.C_GREEN()

        scale = max(gx, gy, cxv, 1e-9)
        rows = [
            ("Growth Sensitivity", gx),
            ("Discount Rate Sensitivity", gy),
            ("Convexity (Terminal)", cxv),
        ]
        for i, (lbl, v) in enumerate(rows):
            r = r0 + 2 + i
            tag, col = bucket(v, scale)
            cv.put(r, c0 + 2, f"{lbl:<28}", w.C_WHITE())
            cv.put(r, c0 + 31, f"{tag:<8}", col + w.BOLD)
            cv.put(r, c0 + 41, w.hbar(min(1.0, v / scale), max(8, width - 45)), col)

        # Stability gauge
        sg_row = r0 + 6
        cv.hline(sg_row, c0, c1, style=w.C_DIM())
        stab_100 = stability * 100 if stability <= 1 else stability
        cv.put(sg_row + 1, c0 + 2, "Valuation Stability:", w.C_DIM())
        sg_col = w.C_GREEN() if stab_100 > 66 else w.C_YELLOW() if stab_100 > 40 else w.C_RED()
        cv.put(sg_row + 1, c0 + 23, f"{stab_100:.0f}/100", sg_col + w.BOLD)
        cv.put(sg_row + 1, c0 + 33, w.gauge(stab_100, max(8, width - 38)), sg_col)
        cv.put(sg_row + 2, c0 + 2, f"Dominant driver: {dom}", w.C_DIM())

        # SAFE ↔ DANGEROUS position bar
        pos_row = sg_row + 4
        if pos_row < r1 - 2:
            cv.put(pos_row, c0 + 2, "PRICE POSITION", w.C_ACCENT() + w.BOLD)
            frag_100 = fragility * 100 if fragility <= 1 else fragility
            track_w = max(20, width - 16)
            pos = int((frag_100 / 100.0) * (track_w - 1))
            track = ["─" if w._UNICODE else "-"] * track_w
            marker = "◆" if w._UNICODE else "*"
            pos = max(0, min(track_w - 1, pos))
            track[pos] = marker
            cv.put(pos_row + 1, c0 + 2, "SAFE ", w.C_GREEN())
            cv.put(pos_row + 1, c0 + 7, "".join(track), w.C_DIM())
            cv.put(pos_row + 1, c0 + 7 + track_w + 1, " FRAGILE", w.C_RED())
            verdict = (
                "Robust — small assumption changes barely move value."
                if frag_100 < 40
                else "Knife-edge — tiny input changes swing valuation hard."
                if frag_100 > 66
                else "Moderate sensitivity to key assumptions."
            )
            vcol = w.C_GREEN() if frag_100 < 40 else w.C_RED() if frag_100 > 66 else w.C_YELLOW()
            cv.put(pos_row + 2, c0 + 2, verdict, vcol)


# ─────────────────────────────────────────────────────────────────────────────
class ArbitrationVisualizerPanel:
    title = "MULTI-LENS ARBITRATION"

    def render(self, cv, r0, r1, c0, c1, sec=None, system_state=None, ticks=0) -> None:
        rpt = _report(sec)
        if rpt is None:
            _need_data(cv, r0, c0)
            return
        price = getattr(sec, "price", 0.0) or 0.0
        width = c1 - c0

        # Collect per-lens fair values where present.
        lenses: list[tuple[str, float]] = []

        def fv_from(obj):
            r = getattr(obj, "fair_value_to_price", None)
            if r is not None and price:
                return price * (1.0 + r)
            return getattr(obj, "fair_value", None) or getattr(obj, "target", None)

        intrinsic = getattr(rpt, "intrinsic", None)
        relative = getattr(rpt, "relative", None)
        market_impl = getattr(rpt, "market_implied_engine", None)
        for name, obj in (
            ("DCF Intrinsic", intrinsic),
            ("Relative", relative),
            ("Reverse DCF", market_impl),
        ):
            if obj is not None:
                v = fv_from(obj)
                if v:
                    lenses.append((name, float(v)))

        # Optional SOTP / Bayesian if attached to the report
        for attr, name in (("sotp", "SOTP"), ("bayesian_target", "Bayesian")):
            obj = getattr(rpt, attr, None)
            if obj is not None:
                v = getattr(obj, "fair_value", None) or (
                    obj if isinstance(obj, int | float) else None
                )
                if v:
                    lenses.append((name, float(v)))

        if not lenses:
            _need_data(cv, r0, c0, "Lens fair values unavailable for this security.")
            return

        cv.put(r0, c0 + 1, f"Current Price: ${price:,.2f}", w.C_WHITE())
        cv.hline(r0 + 1, c0, c1, style=w.C_DIM())

        vals = [v for _n, v in lenses]
        vmin, vmax = min(vals + [price]), max(vals + [price])
        span = (vmax - vmin) or 1.0
        track_w = max(20, width - 30)

        cv.put(r0 + 2, c0 + 1, "FAIR VALUE BY LENS", w.C_ACCENT() + w.BOLD)
        for i, (name, v) in enumerate(lenses):
            r = r0 + 3 + i
            if r > r1 - 6:
                break
            pos = int((v - vmin) / span * (track_w - 1))
            track = [" "] * track_w
            track[max(0, min(track_w - 1, pos))] = "◆" if w._UNICODE else "*"
            # mark current price position with a pipe
            ppos = int((price - vmin) / span * (track_w - 1))
            if 0 <= ppos < track_w and track[ppos] == " ":
                track[ppos] = "│" if w._UNICODE else "|"
            col = w.C_GREEN() if v > price else w.C_RED() if v < price else w.C_YELLOW()
            cv.put(r, c0 + 1, f"{name:<13}", w.C_WHITE())
            cv.put(r, c0 + 14, f"${v:>8,.2f}", col)
            cv.put(r, c0 + 24, "".join(track), w.C_DIM())

        # Consensus + influence weights
        consensus = getattr(getattr(rpt, "final_verdict", None), "rating", None)
        blended = getattr(getattr(rpt, "final_verdict", None), "blended_upside", None)
        crow = r1 - 4
        cv.hline(crow, c0, c1, style=w.C_DIM())
        avg = sum(vals) / len(vals)
        cv.put(crow + 1, c0 + 1, f"Consensus FV ≈ ${avg:,.2f}", w.C_GOLD() + w.BOLD)
        if consensus:
            cv.put(crow + 1, c0 + 28, f"Rating: {consensus}", w.rating_color(consensus) + w.BOLD)
        if blended is not None:
            cv.put(
                crow + 2, c0 + 1, f"Blended upside: {w.fmt_pct(blended)}", w.value_color(blended)
            )


# ─────────────────────────────────────────────────────────────────────────────
class ThesisDriftPanel:
    title = "THESIS DRIFT DETECTOR"

    def render(self, cv, r0, r1, c0, c1, sec=None, system_state=None, ticks=0) -> None:
        rpt = _report(sec)
        dr = getattr(rpt, "drift_report", None) if rpt else None
        if dr is None:
            ticker = getattr(rpt, "ticker", None) or getattr(sec, "ticker", None) or "this security"
            from iam.thesis.drift import no_thesis_message

            _need_data(cv, r0, c0, no_thesis_message(str(ticker))[: c1 - c0 - 3])
            return

        has_drift = bool(getattr(dr, "has_drift", False))
        status = "DRIFT BREACH" if has_drift else "WITHIN THESIS BOUNDS"
        scol = w.C_RED() if has_drift else w.C_GREEN()
        cv.put(r0, c0 + 1, "STATUS: ", w.C_DIM())
        cv.put(r0, c0 + 9, status, scol + w.BOLD)
        banner = getattr(dr, "source_banner", None)
        if isinstance(banner, str) and banner:
            cv.put(
                r0,
                c0 + 32,
                "EXAMPLE THRESHOLDS — not your thesis"[: max(0, c1 - c0 - 33)],
                w.C_YELLOW() + w.BOLD,
            )
        cv.hline(r0 + 1, c0, c1, style=w.C_DIM())

        breaches = list(getattr(dr, "breaches", []) or [])
        if breaches:
            cv.put(r0 + 2, c0 + 1, f"BREACHES ({len(breaches)}):", w.C_RED() + w.BOLD)
            for i, b in enumerate(breaches):
                r = r0 + 3 + i
                if r > r1 - 4:
                    cv.put(r, c0 + 3, f"…and {len(breaches) - i} more", w.C_DIM())
                    break
                try:
                    desc = b.describe()
                except Exception:  # noqa: BLE001
                    desc = str(b)
                cv.put(r, c0 + 3, f"• {desc[: (c1 - c0 - 6)]}", w.C_YELLOW())
            degrade = getattr(dr, "degrade_levels", 0)
            if isinstance(banner, str) and banner:
                cv.put(r1 - 3, c0 + 1, "Example bounds: no effect on the verdict.", w.C_DIM())
            else:
                cv.put(r1 - 3, c0 + 1, f"Confidence degradation: -{degrade} level(s)", w.C_RED())
        else:
            cv.put(r0 + 2, c0 + 2, "All registered constraints satisfied.", w.C_GREEN())

        skipped = list(getattr(dr, "skipped", []) or [])
        if skipped and r1 - 2 > r0 + 3:
            cv.put(
                r1 - 2,
                c0 + 1,
                f"Skipped (missing data): {', '.join(skipped)[: (c1 - c0 - 26)]}",
                w.C_DIM(),
            )
