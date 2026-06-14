"""Interactive settings editor panel for the Alpha Terminal.

Backed by :class:`iam.config.settings.TerminalSettings`.  Renders a two-pane
editor (section list | fields) and exposes a small command surface the terminal
drives from ``_handle_key``:

    nav_field(±1)      move the field cursor
    nav_section(±1)    switch section
    activate()         toggle/cycle in place, OR signal the terminal to collect
                       text for an editable field, OR run an action
    apply_input(raw)   set the active field from collected text (validated)

Actions (Save / Reload / Reset) live in their own section so everything is
driven by Enter — no global hotkey collisions.

Each field is a small spec:
    (label, kind, getter, setter, meta)
kind ∈ {bool, choice, int, float, pct, list, str, action}
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from iam.config.settings import TerminalSettings, default_settings_path, get_settings, set_settings
from iam.ui import widgets as w


@dataclass
class Field:
    label: str
    kind: str
    get: Callable[[], Any]
    set: Callable[[Any], None]
    meta: dict[str, Any]


class SettingsPanel:
    title = "SETTINGS & CONFIGURATION"

    def __init__(self, on_apply: Callable[[TerminalSettings], None] | None = None) -> None:
        self.cfg: TerminalSettings = get_settings()
        self._on_apply = on_apply  # callback so the terminal can hot-apply
        self.section_idx = 0
        self.field_idx = 0
        self.status = ""
        self.dirty = False
        self._sections = self._build_sections()

    # ── schema ───────────────────────────────────────────────────────────────
    def _build_sections(self) -> dict[str, list[Field]]:
        c = self.cfg

        def num(obj, attr, lo, hi, pct=False, integer=False):
            return Field(
                attr.replace("_", " ").title(),
                "int" if integer else ("pct" if pct else "float"),
                lambda o=obj, a=attr: getattr(o, a),
                lambda v, o=obj, a=attr: setattr(o, a, v),
                {"lo": lo, "hi": hi, "pct": pct},
            )

        def boolean(obj, attr):
            return Field(
                attr.replace("_", " ").title(),
                "bool",
                lambda o=obj, a=attr: getattr(o, a),
                lambda v, o=obj, a=attr: setattr(o, a, v),
                {},
            )

        def choice(obj, attr, options):
            return Field(
                attr.replace("_", " ").title(),
                "choice",
                lambda o=obj, a=attr: getattr(o, a),
                lambda v, o=obj, a=attr: setattr(o, a, v),
                {"options": options},
            )

        def tickerlist(obj, attr):
            return Field(
                attr.replace("_", " ").title(),
                "list",
                lambda o=obj, a=attr: getattr(o, a),
                lambda v, o=obj, a=attr: setattr(o, a, v),
                {},
            )

        return {
            "Display": [
                choice(c.display, "theme", ["cyan", "amber", "green"]),
                choice(c.terminal, "color_mode", ["auto", "color", "mono"]),
                boolean(c.terminal, "unicode_enabled"),
                num(c.terminal, "refresh_rate", 0.02, 1.0),
                boolean(c.terminal, "show_debug_info"),
                boolean(c.terminal, "force_window"),
                num(c.terminal, "window_px_width", 200, 4000, integer=True),
                num(c.terminal, "window_px_height", 200, 4000, integer=True),
                num(c.terminal, "cell_px_width", 4, 32, integer=True),
                num(c.terminal, "cell_px_height", 6, 48, integer=True),
            ],
            "Watchlist": [
                tickerlist(c.display, "watchlist"),
                tickerlist(c.display, "coverage"),
                Field(
                    "Default Ticker", "str",
                    lambda: c.display.default_ticker,
                    lambda v: setattr(c.display, "default_ticker", v), {},
                ),
                choice(c.display, "watchlist_sort", ["manual", "change", "upside", "composite"]),
            ],
            "Market Data": [
                boolean(c.market_data, "enabled"),
                boolean(c.market_data, "ribbon_enabled"),
                num(c.market_data, "quote_ttl_seconds", 5, 3600),
                num(c.market_data, "macro_ttl_seconds", 30, 7200),
                num(c.market_data, "tick_refresh_seconds", 0.5, 60),
                num(c.market_data, "ribbon_cycle_seconds", 1, 30),
                boolean(c.market_data, "after_hours_backoff"),
            ],
            "Pipeline": [
                num(c.pipeline, "default_forecast_growth", -0.5, 1.0, pct=True),
                num(c.pipeline, "terminal_growth_rate", 0.0, 0.06, pct=True),
                num(c.pipeline, "discount_rate_floor", 0.0, 0.30, pct=True),
                num(c.pipeline, "discount_rate_ceiling", 0.0, 0.40, pct=True),
                num(c.pipeline, "forecast_periods", 1, 30, integer=True),
                boolean(c.pipeline, "enable_dcf"),
                boolean(c.pipeline, "enable_multiples"),
                boolean(c.pipeline, "enable_scenario"),
            ],
            "Factor Weights": [
                num(c.factor_weights, k, 0.0, 1.0, pct=True)
                for k in c.factor_weights.as_dict()
            ],
            "Risk Limits": [
                num(c.risk_limits, "max_concentration", 0.0, 1.0, pct=True),
                num(c.risk_limits, "max_drawdown", 0.0, 1.0, pct=True),
                num(c.risk_limits, "var_confidence", 0.50, 0.999, pct=True),
                num(c.risk_limits, "stress_test_percentile", 0.0, 0.50, pct=True),
            ],
            "Performance": [
                num(c.async_config, "max_workers", 1, 32, integer=True),
                num(c.async_config, "task_timeout_seconds", 1, 600),
                boolean(c.async_config, "enable_event_bus"),
                num(c.data_source, "cache_ttl_seconds", 0, 86400, integer=True),
                num(c.data_source, "timeout_seconds", 1, 120),
                num(c.data_source, "max_retries", 0, 10, integer=True),
            ],
            "Actions": [
                Field("Save to ~/.iam/settings.yml", "action", lambda: "", self._action_save, {}),
                Field("Reload from disk", "action", lambda: "", self._action_reload, {}),
                Field("Reset to defaults", "action", lambda: "", self._action_reset, {}),
            ],
        }

    @property
    def section_names(self) -> list[str]:
        return list(self._sections.keys())

    def _cur_section(self) -> list[Field]:
        self.section_idx = max(0, min(self.section_idx, len(self.section_names) - 1))
        return self._sections[self.section_names[self.section_idx]]

    def _cur_field(self) -> Field:
        fields = self._cur_section()
        self.field_idx = max(0, min(self.field_idx, len(fields) - 1))
        return fields[self.field_idx]

    # ── navigation ─────────────────────────────────────────────────────────
    def nav_field(self, d: int) -> None:
        fields = self._cur_section()
        self.field_idx = (self.field_idx + d) % len(fields)

    def nav_section(self, d: int) -> None:
        self.section_idx = (self.section_idx + d) % len(self.section_names)
        self.field_idx = 0

    # ── activation ───────────────────────────────────────────────────────────
    def activate(self):
        """Return one of:
        ('toggled', msg) | ('edit', prompt, current) | ('action', msg) | ('none', None)
        """
        f = self._cur_field()
        if f.kind == "bool":
            f.set(not bool(f.get()))
            self._mark_dirty()
            return ("toggled", f"{f.label} = {f.get()}")
        if f.kind == "choice":
            opts = f.meta["options"]
            cur = f.get()
            nxt = opts[(opts.index(cur) + 1) % len(opts)] if cur in opts else opts[0]
            f.set(nxt)
            self._mark_dirty()
            return ("toggled", f"{f.label} = {nxt}")
        if f.kind == "action":
            msg = f.set(None)  # action setters return a message
            return ("action", msg or f.label)
        # editable text/number/list
        cur = f.get()
        if f.kind == "list":
            current = ", ".join(cur)
        elif f.kind == "pct":
            current = f"{float(cur) * 100:.2f}"
        else:
            current = str(cur)
        prompt = self._prompt_for(f)
        return ("edit", prompt, current)

    def _prompt_for(self, f: Field) -> str:
        if f.kind == "list":
            return f"Enter {f.label} (comma-separated tickers)"
        if f.kind == "pct":
            lo, hi = f.meta["lo"], f.meta["hi"]
            return f"Enter {f.label} in % (range {lo * 100:.0f}–{hi * 100:.0f})"
        if f.kind in ("int", "float"):
            return f"Enter {f.label} (range {f.meta['lo']}–{f.meta['hi']})"
        return f"Enter {f.label}"

    def apply_input(self, raw: str):
        """Validate + set the active field from collected text.  -> (ok, msg)."""
        f = self._cur_field()
        raw = (raw or "").strip()
        if not raw:
            return (False, "No change.")
        try:
            if f.kind == "list":
                items = [t.strip().upper() for t in raw.replace(";", ",").split(",") if t.strip()]
                f.set(items)
            elif f.kind == "pct":
                v = float(raw.rstrip("%")) / 100.0
                v = w.clamp(v, f.meta["lo"], f.meta["hi"])
                f.set(v)
            elif f.kind == "int":
                v = int(w.clamp(float(raw), f.meta["lo"], f.meta["hi"]))
                f.set(v)
            elif f.kind == "float":
                v = w.clamp(float(raw), f.meta["lo"], f.meta["hi"])
                f.set(v)
            else:  # str
                f.set(raw)
        except (ValueError, TypeError) as exc:
            return (False, f"Invalid value: {exc}")
        self._mark_dirty()
        return (True, f"{f.label} updated.")

    def _mark_dirty(self) -> None:
        self.dirty = True
        if self._on_apply:
            try:
                self._on_apply(self.cfg)
            except Exception:  # noqa: BLE001
                pass

    # ── actions ──────────────────────────────────────────────────────────────
    def _action_save(self, _ignored=None) -> str:
        try:
            path = default_settings_path()
            self.cfg.to_file(path)
            set_settings(self.cfg)
            self.dirty = False
            return f"Saved to {path}"
        except Exception as exc:  # noqa: BLE001
            return f"Save failed: {exc}"

    def _action_reload(self, _ignored=None) -> str:
        try:
            self.cfg = TerminalSettings.from_env()
            set_settings(self.cfg)
            self._sections = self._build_sections()
            self._clamp_cursor()
            self.dirty = False
            if self._on_apply:
                self._on_apply(self.cfg)
            return "Reloaded settings from disk."
        except Exception as exc:  # noqa: BLE001
            return f"Reload failed: {exc}"

    def _action_reset(self, _ignored=None) -> str:
        self.cfg = TerminalSettings()
        set_settings(self.cfg)
        self._sections = self._build_sections()
        self._clamp_cursor()
        self.dirty = True
        if self._on_apply:
            self._on_apply(self.cfg)
        return "Reset to defaults (unsaved)."

    def _clamp_cursor(self) -> None:
        """Keep section/field indices valid after the schema is rebuilt."""
        self.section_idx = max(0, min(self.section_idx, len(self.section_names) - 1))
        self.field_idx = max(0, min(self.field_idx, len(self._cur_section()) - 1))

    def set_status(self, msg: str) -> None:
        self.status = msg

    # ── render ─────────────────────────────────────────────────────────────
    def render(self, cv, r0, r1, c0, c1, sec=None, system_state=None, ticks=0) -> None:
        width = c1 - c0
        sec_w = 18
        # left: section list
        cv.put(r0, c0 + 1, "SECTIONS", w.C_ACCENT() + w.BOLD)
        cv.hline(r0 + 1, c0, c0 + sec_w, style=w.C_DIM())
        for i, name in enumerate(self.section_names):
            r = r0 + 2 + i
            if r > r1 - 1:
                break
            if i == self.section_idx:
                cv.put(r, c0 + 1, f"{w.flat_arrow()} {name:<{sec_w - 3}}", w.C_GOLD() + w.BOLD)
            else:
                cv.put(r, c0 + 1, f"  {name:<{sec_w - 3}}", w.C_WHITE())

        # vertical divider
        for r in range(r0, r1):
            cv.put(r, c0 + sec_w, "│" if w._UNICODE else "|", w.C_DIM())

        # right: fields of the active section
        fx = c0 + sec_w + 2
        fw = c1 - fx
        sect_name = self.section_names[self.section_idx]
        cv.put(r0, fx, sect_name.upper(), w.C_ACCENT() + w.BOLD)
        cv.hline(r0 + 1, fx, c1, style=w.C_DIM())

        fields = self._cur_section()
        sumline = None
        if sect_name == "Factor Weights":
            sumline = self.cfg.factor_weights.total_weight()

        for i, f in enumerate(fields):
            r = r0 + 2 + i
            if r > r1 - 3:
                break
            sel = i == self.field_idx
            lbl_col = (w.C_GOLD() + w.BOLD) if sel else w.C_WHITE()
            cur_col = w.C_TEAL() if sel else w.C_DIM()
            marker = (w.flat_arrow() + " ") if sel else "  "
            cv.put(r, fx, f"{marker}{f.label:<28}", lbl_col)
            cv.put(r, fx + 31, self._display_value(f), cur_col)

        if sumline is not None:
            srow = min(r1 - 3, r0 + 2 + len(fields))
            scol = w.C_GREEN() if abs(sumline - 1.0) < 0.01 else w.C_YELLOW()
            cv.put(srow, fx, f"Σ weights = {sumline:.2f}", scol + w.BOLD)
            if abs(sumline - 1.0) >= 0.01:
                cv.put(srow, fx + 22, "(edit then Reload normalizes at scoring)", w.C_DIM())

        # status / help footer
        cv.hline(r1 - 2, c0, c1, style=w.C_DIM())
        dirty = " ●UNSAVED" if self.dirty else ""
        help_txt = "[↑↓] field  [←→/Tab] section  [Enter] edit/toggle  · Actions section to Save"
        cv.put(r1 - 1, c0 + 1, help_txt, w.C_DIM())
        if self.status:
            cv.put(r1 - 1, c1 - len(self.status) - len(dirty) - 2, self.status, w.C_GREEN())
        if dirty:
            cv.put(r1 - 1, c1 - len(dirty) - 1, dirty, w.C_RED() + w.BOLD)

    def _display_value(self, f: Field) -> str:
        v = f.get()
        if f.kind == "bool":
            return ("✓ ON" if v else "✗ OFF") if w._UNICODE else ("ON" if v else "OFF")
        if f.kind == "choice":
            return f"< {v} >"
        if f.kind == "pct":
            try:
                return f"{float(v) * 100:.2f}%"
            except (TypeError, ValueError):
                return str(v)
        if f.kind == "list":
            items = list(v)
            shown = ", ".join(items[:6])
            more = f" +{len(items) - 6}" if len(items) > 6 else ""
            return (shown + more) or "(empty)"
        if f.kind == "action":
            return ""
        return str(v)
