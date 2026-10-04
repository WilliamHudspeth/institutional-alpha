"""Scenario / DeepVal / Backtest / SOTP panels must show real data or n/a."""

from types import SimpleNamespace

from iam.backtest.multiple_testing import ValidationMetrics
from iam.ui.alpha_terminal import (
    BacktestPanel,
    Canvas,
    DeepValPanel,
    ScenarioPanel,
    SecState,
    SOTPTowerPanel,
    SystemState,
)

SCEN = {
    "Bear Case": {
        "prob": 0.2,
        "target": 70.0,
        "upside": -0.3,
        "g": 0.036,
        "wacc": 0.115,
        "tv_g": 0.016,
    },
    "Base Case": {
        "prob": 0.6,
        "target": 120.0,
        "upside": 0.2,
        "g": 0.06,
        "wacc": 0.097,
        "tv_g": 0.02,
    },
    "Bull Case": {
        "prob": 0.2,
        "target": 150.0,
        "upside": 0.5,
        "g": 0.078,
        "wacc": 0.087,
        "tv_g": 0.024,
    },
}


def _sec(scenarios=None, price=100.0, with_intrinsic=True):
    sec = SecState(ticker="TEST")
    sec.loading = False
    sec.security = SimpleNamespace(market=SimpleNamespace(price=price))
    comps = {} if scenarios is None else {"scenarios": scenarios}
    sec.pipeline_result = SimpleNamespace(
        final_verdict=SimpleNamespace(blended_upside=0.2),
        implied_move_pct=0.2,
        intrinsic=SimpleNamespace(components=comps) if with_intrinsic else None,
        triangulation=SimpleNamespace(cluster_center=0.1, spread=0.05, verdict="BUY"),
    )
    return sec


def _text(cv):
    return "\n".join("".join(ch for ch, _ in row) for row in cv._back)


def _render(panel, sec, system_state=None):
    cv = Canvas(40, 120)
    panel.render(cv, 2, 38, 1, 118, sec, system_state, ticks=0)
    return _text(cv)


def test_scenario_uses_real_matrix():
    out = _render(ScenarioPanel(), _sec(SCEN))
    assert "$     70.00" in out and "$    150.00" in out
    assert "-30.0%" in out and "+50.0%" in out
    assert "g 3.6% · WACC 11.5% · g∞ 1.6%" in out
    assert "Stressed execution" not in out
    # PWEV = 0.2*70 + 0.6*120 + 0.2*150 = 116
    assert "$116.00" in out and "+16.0%" in out
    assert "72.00" not in out and "138.00" not in out


def test_scenario_missing_matrix_is_na():
    for sec in (_sec(None), _sec(None, with_intrinsic=False)):
        out = _render(ScenarioPanel(), sec)
        assert "Scenario table: n/a (no FCFE scenario matrix for TEST)" in out
        assert "Bear" not in out


def _spy_range_bar(monkeypatch):
    import iam.ui.alpha_terminal as at

    seen = []
    monkeypatch.setattr(at, "_IAM_SPARKLINES", True)
    monkeypatch.setattr(
        at.MiniChart, "range_bar", lambda *a, **k: seen.append(a) or "X", raising=False
    )
    return seen


def test_deepval_range_bar_uses_real_bounds(monkeypatch):
    seen = _spy_range_bar(monkeypatch)
    _render(DeepValPanel(), _sec(SCEN))
    assert seen and seen[0][1:] == (70.0, 150.0)


def test_deepval_no_scenarios_falls_back_to_meter(monkeypatch):
    seen = _spy_range_bar(monkeypatch)
    _render(DeepValPanel(), _sec(None))
    assert not seen


def test_backtest_absent_shows_na_no_rows():
    ss = SystemState()
    ss.loading = False
    ss.backtest_metrics = None
    out = _render(BacktestPanel(), None, ss)
    assert "Backtest metrics: n/a (run the IC backtest" in out
    assert "ic_horizon_1m.csv" in out
    assert "Intrinsic Value" not in out and "+0.112" not in out
    assert not hasattr(BacktestPanel, "ROWS")


def test_backtest_renders_real_and_nan_as_na():
    ss = SystemState()
    ss.loading = False
    ss.backtest_metrics = ValidationMetrics(
        psr=float("nan"),
        dsr=1.5,
        pbo=0.04,
        spa_pvalue=0.02,
        effective_tests=8.0,
        factor_metrics={"Quality": {"ic": 0.05, "p_value": 0.01, "spread": float("nan")}},
    )
    out = _render(BacktestPanel(), None, ss)
    assert "+0.050" in out and "0.010" in out
    assert "nan" not in out.lower()
    assert "n/a" in out


def test_sotp_without_segments_is_na():
    sec = _sec(None)
    sec.security.qualitative = {}
    out = _render(SOTPTowerPanel(), sec)
    assert "SOTP tower: n/a (no segment data for TEST)" in out
