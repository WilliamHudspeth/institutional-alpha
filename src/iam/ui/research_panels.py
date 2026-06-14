"""Research-grade analytic panels for the Alpha Terminal.

These surface engine outputs that previously only appeared in verbose console
logs.  Each binds to fields already produced by the pipeline / topology layers
and degrades gracefully when a given block is missing.

* :class:`ExpectationsBattlefieldPanel` — market vs model assumptions + the
  attribution bars (which variable explains the mispricing).   [report.battlefield]
* :class:`ReverseDCFDistributionPanel` — market-implied vs intrinsic growth as
  overlaid bands with an alignment score.                       [report.battlefield]
* :class:`FragilityMapPanel` — sensitivity / stability read from the valuation
  topology, with a SAFE↔DANGEROUS position bar.                 [sec.topology_metrics]
* :class:`ArbitrationVisualizerPanel` — per-lens fair values and their influence
  on the consensus.                                  [report.intrinsic/relative/...]
* :class:`ThesisDriftPanel` — registered-thesis breaches and confidence decay.
                                                                [report.drift_report]
"""

from __future__ import annotations

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
            _need_data(cv, r0, c0)
            return
        width = c1 - c0

        col_w = max(26, width // 2 - 2)
        lx, rx = c0 + 1, c0 + col_w + 3

        cv.put(r0, lx, "MARKET EXPECTATIONS", w.C_RED() + w.BOLD)
        cv.put(r0, rx, "MODEL EXPECTATIONS", w.C_GREEN() + w.BOLD)
        cv.hline(r0 + 1, c0, c1, style=w.C_DIM())

        rows = [
            ("Revenue / FCFE Growth", bf.market_growth, bf.intrinsic_growth),
            ("Operating Margin", bf.market_margin, bf.intrinsic_margin),
            ("ROIC", bf.market_roic, bf.intrinsic_roic),
        ]
        for i, (lbl, mkt_v, mod_v) in enumerate(rows):
            r = r0 + 2 + i
            cv.put(r, lx, f"{lbl:<22}", w.C_WHITE())
            cv.put(r, lx + 22, w.fmt_pct(mkt_v), w.C_WHITE())
            cv.put(r, rx, f"{lbl:<22}", w.C_WHITE())
            cv.put(r, rx + 22, w.fmt_pct(mod_v), w.C_WHITE())

        # Gap analysis line
        gap_row = r0 + 6
        cv.hline(gap_row, c0, c1, style=w.C_DIM())
        cv.put(gap_row + 1, lx, "GAP ANALYSIS", w.C_ACCENT() + w.BOLD)
        gaps = [
            ("Growth", bf.growth_gap),
            ("Margin", bf.margin_gap),
            ("ROIC", bf.roic_gap),
        ]
        gx = lx
        for name, g in gaps:
            col = w.value_color(g)
            seg = f"{name} {w.fmt_pct(g)}"
            cv.put(gap_row + 2, gx, seg, col)
            gx += len(seg) + 4

        # Battlefield attribution bars
        bar_row = gap_row + 4
        cv.put(bar_row, lx, "PRICE EXPLAINED BY", w.C_ACCENT() + w.BOLD)
        # Weight each driver by the magnitude of its gap.
        drivers = {
            "Growth": abs(bf.growth_gap or 0.0),
            "Margin": abs(bf.margin_gap or 0.0),
            "Capital Eff. (ROIC)": abs(bf.roic_gap or 0.0),
        }
        total = sum(drivers.values()) or 1.0
        bar_w = max(10, width - 30)
        for i, (name, mag) in enumerate(
            sorted(drivers.items(), key=lambda kv: kv[1], reverse=True)
        ):
            r = bar_row + 1 + i
            frac = mag / total
            bar = w.hbar(frac, bar_w)
            cv.put(r, lx, f"{name:<20}", w.C_WHITE())
            cv.put(r, lx + 20, bar, w.C_TEAL())
            cv.put(r, lx + 20 + bar_w + 1, f"{frac * 100:4.0f}%", w.C_DIM())

        # Footer: primary disagreement + alignment / mismatch scores
        if r1 - 2 > bar_row + 4:
            cv.hline(r1 - 3, c0, c1, style=w.C_DIM())
            prim = (getattr(bf, "primary_disagreement", "") or "").upper()
            cv.put(r1 - 2, lx, "PRIMARY DRIVER: ", w.C_DIM())
            cv.put(r1 - 2, lx + 16, prim or "—", w.C_GOLD() + w.BOLD)
            align = getattr(bf, "alignment_score", None)
            mismatch = getattr(bf, "expectation_mismatch_score", None)
            if align is not None:
                cv.put(r1 - 1, lx, f"Alignment {align:.0f}/100", w.C_GREEN())
            if mismatch is not None:
                cv.put(r1 - 1, lx + 22, f"Mismatch {mismatch:.0f}/100", w.C_RED())


# ─────────────────────────────────────────────────────────────────────────────
class ReverseDCFDistributionPanel:
    title = "REVERSE DCF — IMPLIED vs INTRINSIC"

    def render(self, cv, r0, r1, c0, c1, sec=None, system_state=None, ticks=0) -> None:
        rpt = _report(sec)
        bf = getattr(rpt, "battlefield", None) if rpt else None
        if bf is None:
            _need_data(cv, r0, c0)
            return
        width = c1 - c0
        bar_w = max(14, width - 24)

        mkt_g = bf.market_growth or 0.0
        mod_g = bf.intrinsic_growth or 0.0

        # Build a discrete growth axis around the two anchors.
        lo = min(mkt_g, mod_g) - 0.04
        hi = max(mkt_g, mod_g) + 0.04
        steps = 7
        axis = [lo + (hi - lo) * i / (steps - 1) for i in range(steps)]

        def band(center, spread=0.025):
            # crude gaussian-ish weight per axis bucket
            return [
                max(0.0, 1.0 - abs(g - center) / (spread * 2.5)) for g in axis
            ]

        mkt_band = band(mkt_g)
        mod_band = band(mod_g)
        mmax = max(max(mkt_band), max(mod_band)) or 1.0

        cv.put(r0, c0 + 1, "MARKET-IMPLIED GROWTH", w.C_RED() + w.BOLD)
        cv.hline(r0 + 1, c0, c1, style=w.C_DIM())
        for i, g in enumerate(axis):
            r = r0 + 2 + i
            if r > r1 - 1:
                break
            cv.put(r, c0 + 1, f"{g * 100:5.1f}%", w.C_DIM())
            cv.put(r, c0 + 8, w.distribution_row(mkt_band[i], mmax, bar_w, "█"), w.C_RED())

        # Intrinsic band overlaid in a second column band
        mid = r0 + 2 + steps + 1
        if mid < r1 - 1:
            cv.put(mid, c0 + 1, "INTRINSIC / MODEL GROWTH", w.C_GREEN() + w.BOLD)
            cv.hline(mid + 1, c0, c1, style=w.C_DIM())
            for i, g in enumerate(axis):
                r = mid + 2 + i
                if r > r1 - 2:
                    break
                cv.put(r, c0 + 1, f"{g * 100:5.1f}%", w.C_DIM())
                glyph = "▒" if w._UNICODE else ":"
                cv.put(r, c0 + 8, w.distribution_row(mod_band[i], mmax, bar_w, glyph), w.C_GREEN())

        # Alignment score = overlap of the two bands.
        overlap = sum(min(a, b) for a, b in zip(mkt_band, mod_band))
        union = sum(max(a, b) for a, b in zip(mkt_band, mod_band)) or 1.0
        align = overlap / union
        gap = getattr(bf, "growth_overlap", None)
        if gap is not None:
            align = (align + gap) / 2.0  # blend with engine's own overlap if present
        col = w.C_GREEN() if align > 0.6 else w.C_YELLOW() if align > 0.35 else w.C_RED()
        cv.put(r1 - 1, c0 + 1, f"Alignment Score: {align * 100:.0f}%", col + w.BOLD)
        cv.put(
            r1 - 1,
            c0 + 26,
            "(overlap of market vs model growth bands)",
            w.C_DIM(),
        )


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
        sg_col = (
            w.C_GREEN() if stab_100 > 66 else w.C_YELLOW() if stab_100 > 40 else w.C_RED()
        )
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
            vcol = (
                w.C_GREEN() if frag_100 < 40 else w.C_RED() if frag_100 > 66 else w.C_YELLOW()
            )
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
        for name, obj in (("DCF Intrinsic", intrinsic), ("Relative", relative),
                          ("Reverse DCF", market_impl)):
            if obj is not None:
                v = fv_from(obj)
                if v:
                    lenses.append((name, float(v)))

        # Optional SOTP / Bayesian if attached to the report
        for attr, name in (("sotp", "SOTP"), ("bayesian_target", "Bayesian")):
            obj = getattr(rpt, attr, None)
            if obj is not None:
                v = getattr(obj, "fair_value", None) or (obj if isinstance(obj, (int, float)) else None)
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
            cv.put(crow + 2, c0 + 1, f"Blended upside: {w.fmt_pct(blended)}", w.value_color(blended))


# ─────────────────────────────────────────────────────────────────────────────
class ThesisDriftPanel:
    title = "THESIS DRIFT DETECTOR"

    def render(self, cv, r0, r1, c0, c1, sec=None, system_state=None, ticks=0) -> None:
        rpt = _report(sec)
        dr = getattr(rpt, "drift_report", None) if rpt else None
        if dr is None:
            _need_data(cv, r0, c0, "No thesis registered for this security (define YAML bounds).")
            return

        has_drift = bool(getattr(dr, "has_drift", False))
        status = "DRIFT BREACH" if has_drift else "WITHIN THESIS BOUNDS"
        scol = w.C_RED() if has_drift else w.C_GREEN()
        cv.put(r0, c0 + 1, "STATUS: ", w.C_DIM())
        cv.put(r0, c0 + 9, status, scol + w.BOLD)
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
