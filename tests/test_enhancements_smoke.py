"""Smoke tests for the Alpha Terminal enhancement bundle.

These do not require network access: the market layer is forced into mock mode.
Run with:  python -m pytest tests/test_enhancements_smoke.py -q
"""

from __future__ import annotations

import tempfile
import time
import types
from pathlib import Path

from iam.config.settings import TerminalSettings
from iam.data import markets as mkt
from iam.ui import market_panels as mp
from iam.ui import research_panels as rp
from iam.ui import settings_panel as sp
from iam.ui import widgets as w


class _Canvas:
    """Minimal Canvas stand-in that validates row bounds."""

    def __init__(self, rows: int, cols: int) -> None:
        self.rows, self.cols, self.calls = rows, cols, 0
        self._dirty = False

    def put(self, r, c, text, style="") -> None:
        self.calls += 1
        assert 0 <= r < self.rows, f"row {r} out of bounds (rows={self.rows})"
        assert c >= 0

    def hline(self, r, c0, c1, ch="-", style="") -> None:
        self.calls += 1
        assert 0 <= r < self.rows

    def box(self, *a, **k) -> None:
        self.calls += 1


def _mock_sec():
    bf = types.SimpleNamespace(
        market_growth=0.182, intrinsic_growth=0.121,
        market_margin=0.224, intrinsic_margin=0.185,
        market_roic=0.30, intrinsic_roic=0.26,
        growth_gap=0.061, margin_gap=0.039, roic_gap=0.04,
        growth_overlap=0.6, alignment_score=71, expectation_mismatch_score=42,
        primary_disagreement="growth",
    )
    breach = types.SimpleNamespace(describe=lambda: "ROIC 22% < floor 25%")
    drift = types.SimpleNamespace(
        has_drift=True, breaches=[breach], degrade_levels=1, skipped=["margin_floor"]
    )
    report = types.SimpleNamespace(
        battlefield=bf, drift_report=drift,
        intrinsic=types.SimpleNamespace(fair_value_to_price=0.12),
        relative=types.SimpleNamespace(fair_value_to_price=-0.03),
        market_implied_engine=types.SimpleNamespace(fair_value_to_price=0.05),
        final_verdict=types.SimpleNamespace(
            rating="HOLD", blended_upside=0.04, confidence_band="MODERATE"
        ),
    )
    topo = {
        "fragility_score": 0.62, "stability_score": 0.55,
        "gradient_x_mean": 0.8, "gradient_y_mean": 1.4,
        "curvature_x_mean": 0.3, "dominant_driver": "Discount Rate",
    }
    return types.SimpleNamespace(
        ticker="AAPL", price=195.0, rating="HOLD", composite=0.2,
        pipeline_result=report, topology_metrics=topo,
    )


def test_widgets():
    w.configure("amber", "color", True)
    assert len(w.spark_line([1, 2, 3, 5, 4, 6, 2, 1], 8)) == 8
    assert len(w.hbar(0.5, 10)) == 10
    assert w.fmt_pct(0.034) == "+3.4%"
    assert w.fmt_bps(0.0003) == "+3bp"


def test_settings_round_trip():
    cfg = TerminalSettings()
    assert cfg.display.watchlist[0] == "TSLA"
    cfg.display.theme = "amber"
    cfg.pipeline.default_forecast_growth = 0.11
    p = Path(tempfile.gettempdir()) / "iam_test_settings.yml"
    cfg.to_file(p)
    reloaded = TerminalSettings.from_file(p)
    assert reloaded.display.theme == "amber"
    assert abs(reloaded.pipeline.default_forecast_growth - 0.11) < 1e-9


def test_market_snapshot_mock():
    mkt._HAS_YF = False
    snap = mkt.fetch_market_snapshot()
    assert len(snap.group("US")) == 4
    assert len(snap.rate_curve()) == 4
    assert snap.group("US")[0].last is not None


def test_panels_render():
    mkt._HAS_YF = False
    mkt._snapshot = mkt.fetch_market_snapshot()
    mkt._snapshot_ts = time.time()
    w.configure("cyan", "color", True)
    cv = _Canvas(40, 120)
    sec = _mock_sec()
    panels = [
        rp.ExpectationsBattlefieldPanel(),
        rp.ReverseDCFDistributionPanel(),
        rp.FragilityMapPanel(),
        rp.ArbitrationVisualizerPanel(),
        rp.ThesisDriftPanel(),
        mp.GlobalMarketsPanel(),
    ]
    for p in panels:
        cv.calls = 0
        p.render(cv, 3, 36, 27, 118, sec, None, 0)
        assert cv.calls > 0, f"{type(p).__name__} drew nothing"


def test_watchlist_and_ribbon():
    mkt._HAS_YF = False
    mkt._snapshot = mkt.fetch_market_snapshot()
    mkt._snapshot_ts = time.time()
    cv = _Canvas(40, 120)
    sec = _mock_sec()
    wl = mp.RealWatchlistPanel(["AAPL", "MSFT"], sec_lookup=lambda t: sec if t == "AAPL" else None)
    wl.render(cv, 3, 36, 27, 118, sec, None, 0)
    mp.render_ribbon(cv, 1, 120, 0)
    assert cv.calls > 0


def test_terrain_panel():
    from iam.ui import terrain as tr

    w.configure("cyan", "color", True)
    cv = _Canvas(40, 120)
    sec = _mock_sec()
    panel = tr.TerrainPanel()
    for _mode in tr.TerrainPanel.MODES:
        cv.calls = 0
        panel.render(cv, 3, 36, 2, 118, sec, None, 0)
        assert cv.calls > 0
        panel.cycle_mode()
    panel.toggle_wireframe()
    cv.calls = 0
    panel.render(cv, 3, 36, 2, 118, sec, None, 0)
    assert cv.calls > 0
    panel.rotate(0.3, 0.1)
    panel.zoom(1.2)
    panel.reset_view()


def test_example_config_loads():
    cfg = TerminalSettings.from_file(Path(__file__).parent.parent / "config.example.yml")
    assert cfg.display.theme in ("cyan", "amber", "green")
    assert cfg.market_data.ribbon_enabled is True
    assert cfg.pipeline.default_forecast_growth == 0.08


def test_force_window_size():
    # default cell size -> 800/8 = 100 cols, 800/16 = 50 rows; emit=False (no tty write)
    cols, rows = w.force_window_size(800, 800, 8, 16, emit=False)
    assert (cols, rows) == (100, 50)
    # custom cell size is honored
    cols2, rows2 = w.force_window_size(1024, 768, 16, 24, emit=False)
    assert cols2 == 64 and rows2 == 32
    # omitting cell args reads the live globals (regression guard for early-binding)
    w.configure("cyan", "color", True, cell_px=(10, 20))
    cols3, rows3 = w.force_window_size(1000, 1000, emit=False)
    assert cols3 == 100 and rows3 == 50


def test_settings_actions():
    panel = sp.SettingsPanel()
    save_msg = panel._action_save()
    assert "Saved" in save_msg or "failed" in save_msg.lower()
    reload_msg = panel._action_reload()
    assert "Reload" in reload_msg
    reset_msg = panel._action_reset()
    assert "Reset" in reset_msg
    # cursor stays in bounds even if we point it past the new schema
    panel.section_idx = 999
    panel.field_idx = 999
    panel._clamp_cursor()
    assert 0 <= panel.section_idx < len(panel.section_names)
    assert 0 <= panel.field_idx < len(panel._cur_section())


def test_market_session_helpers():
    assert isinstance(mkt.us_market_open(), bool)
    assert isinstance(mkt.session_label(), str)


def test_graceful_degradation_renders():
    """Panels must draw a placeholder, not crash, when their data is absent."""
    w.configure("cyan", "color", True)
    # GlobalMarkets with no snapshot cached
    mkt._snapshot = None
    mkt._snapshot_ts = 0.0
    cv = _Canvas(40, 120)
    mp.GlobalMarketsPanel().render(cv, 3, 36, 0, 120, None, None, 0)
    assert cv.calls > 0  # drew the "fetching" placeholder
    # Battlefield with no battlefield on the report
    sec = _mock_sec()
    sec.pipeline_result.battlefield = None
    cv.calls = 0
    rp.ExpectationsBattlefieldPanel().render(cv, 3, 36, 0, 120, sec, None, 0)
    assert cv.calls > 0  # drew the "no data" placeholder
    # Fragility with no topology
    sec.topology_metrics = None
    cv.calls = 0
    rp.FragilityMapPanel().render(cv, 3, 36, 0, 120, sec, None, 0)
    assert cv.calls > 0


def test_terrain_wireframe_and_modes():
    from iam.ui import terrain as tr

    w.configure("cyan", "color", True, cell_px=(8, 16))
    cv = _Canvas(50, 120)
    sec = _mock_sec()
    panel = tr.TerrainPanel()
    panel.toggle_wireframe()
    for _ in tr.TerrainPanel.MODES:
        cv.calls = 0
        panel.render(cv, 3, 46, 0, 118, sec, None, 0)
        assert cv.calls > 0
        panel.cycle_mode()


def test_settings_panel_interaction():
    panel = sp.SettingsPanel()
    # cycle theme
    panel.section_idx, panel.field_idx = 0, 0
    kind, _ = panel.activate()
    assert kind == "toggled"
    # edit watchlist
    panel.section_idx = panel.section_names.index("Watchlist")
    panel.field_idx = 0
    sig = panel.activate()
    assert sig[0] == "edit"
    ok, _ = panel.apply_input("aapl, msft, googl")
    assert ok and panel.cfg.display.watchlist == ["AAPL", "MSFT", "GOOGL"]
    # pct clamp
    panel.section_idx = panel.section_names.index("Pipeline")
    panel.field_idx = 2  # discount_rate_floor (0..0.30)
    panel.activate()
    panel.apply_input("999")
    assert panel.cfg.pipeline.discount_rate_floor == 0.30
