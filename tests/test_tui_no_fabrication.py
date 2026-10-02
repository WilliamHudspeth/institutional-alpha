"""The full-screen TUI must never show fabricated numbers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from iam.data.markets import Quote
from iam.ui import alpha_terminal as at
from iam.ui.alpha_terminal import (
    AlphaTerminal,
    Canvas,
    FactorPanel,
    PortfolioPanel,
    QuickRecPanel,
    SecState,
    SystemState,
)


def _text(cv: Canvas) -> str:
    return "\n".join("".join(ch for ch, _ in row).rstrip() for row in cv._back)


def _render(panel, sec, sys_state=None, rows=40, cols=110):
    cv = Canvas(rows, cols)
    panel.render(cv, 2, rows - 3, 2, cols - 2, sec, sys_state, ticks=1)
    return _text(cv)


def _real_sec(
    ticker="AAPL", price=100.0, composite=0.4, band="HIGH", factors=None, upside=0.1
) -> SecState:
    factors = factors or {}
    breakdown = {
        k: SimpleNamespace(value=v, confidence=c, effective=lambda v=v, c=c: v * c)
        for k, (v, c) in factors.items()
    }
    verdict = SimpleNamespace(rating="BUY", confidence_band=band, blended_upside=upside)
    return SecState(
        ticker=ticker,
        security=SimpleNamespace(name=ticker, market=SimpleNamespace(price=price), sector=None),
        score_result=SimpleNamespace(composite=composite, factor_breakdown=breakdown),
        pipeline_result=SimpleNamespace(
            final_verdict=verdict, implied_move_pct=None, triangulation=None, law_report=None
        ),
        loading=False,
    )


@pytest.fixture
def term():
    return AlphaTerminal()


# 3. failed load -> no mock data -------------------------------------------------
def test_failed_load_leaves_state_empty_and_sets_error(term):
    term._secs["ZZZZ"] = SecState(ticker="ZZZZ", loading=True)
    with (
        patch.object(at, "_IAM_CORE", True),
        patch.object(at, "_fetch_security", side_effect=RuntimeError("boom")),
    ):
        term._worker("ZZZZ")
    st = term._secs["ZZZZ"]
    assert st.security is None
    assert st.score_result is None
    assert st.pipeline_result is None
    assert st.history == []
    assert st.loading is False
    assert "boom" in st.error
    assert st.price is None and st.upside is None and st.composite is None


def test_quickrec_shows_error_not_rating():
    sec = SecState(ticker="ZZZZ", loading=False, error="boom")
    out = _render(QuickRecPanel(), sec)
    assert "Could not load ZZZZ: boom" in out
    assert "RATING" not in out
    assert "$0.00" not in out and "50/100" not in out


# 4. unknown values are None / n/a ----------------------------------------------
def test_secstate_unknowns_are_none():
    sec = SecState(ticker="X")
    assert sec.price is None
    assert sec.upside is None
    assert sec.composite is None
    assert sec.is_demo is False


def test_quickrec_na_when_price_upside_composite_unknown():
    sec = SecState(ticker="X", loading=False)
    sec.pipeline_result = SimpleNamespace(
        final_verdict=SimpleNamespace(rating="HOLD", confidence_band="LOW", blended_upside=None),
        implied_move_pct=None,
        law_report=None,
    )
    out = _render(QuickRecPanel(), sec)
    assert "n/a" in out
    assert "$0.00" not in out
    assert "50/100" not in out
    assert "+0.0%" not in out


def test_factor_panel_handles_unscored():
    sec = SecState(ticker="X", loading=False)
    sec.pipeline_result = object()
    out = _render(FactorPanel(), sec)
    assert "Composite Score: n/a" in out
    assert "50/100" not in out


def test_demo_data_is_flagged():
    sec = SecState(ticker="X", loading=False)
    sec.security = at._MockSec("X", 123.0)
    sec.score_result = at._MockScore()
    sec.pipeline_result = at._MockPipeline()
    for panel in (QuickRecPanel(), FactorPanel()):
        assert "DEMO DATA (random)" in _render(panel, sec)


# 2. _tick_prices uses real quotes only ------------------------------------------
@pytest.mark.parametrize(
    "quote",
    [None, Quote(symbol="AAPL", last=111.0, stale=True), Quote(symbol="AAPL", last=None)],
)
def test_tick_prices_ignores_missing_or_stale_quote(term, quote):
    sec = _real_sec("AAPL", 100.0)
    sec.history = [100.0]
    term._active = "AAPL"
    term._secs["AAPL"] = sec
    with patch("iam.data.markets.get_quote", return_value=quote):
        for _ in range(5):
            term._tick_prices()
    assert sec.security.market.price == 100.0
    assert sec.history == [100.0]


def test_tick_prices_applies_fresh_quote_only_when_changed(term):
    sec = _real_sec("AAPL", 100.0)
    sec.history = [100.0]
    term._active = "AAPL"
    term._secs["AAPL"] = sec
    with patch("iam.data.markets.get_quote", return_value=Quote(symbol="AAPL", last=101.5)):
        term._tick_prices()
        term._tick_prices()
    assert sec.security.market.price == 101.5
    assert sec.history == [100.0, 101.5]


# 1. history is real -------------------------------------------------------------
def test_real_history_uses_fetched_history_when_fresh():
    q = Quote(symbol="AAPL", last=3.0, history=[1.0, 2.0, 3.0], stale=False)
    with patch("iam.data.markets._fetch_one", return_value=q):
        h = AlphaTerminal._real_history("AAPL", SimpleNamespace(market=SimpleNamespace(price=3.0)))
    assert h == [1.0, 2.0, 3.0]


@pytest.mark.parametrize("fail", [True, False])
def test_real_history_falls_back_to_single_real_price(fail):
    stale = Quote(symbol="AAPL", last=9.0, history=[8.0, 9.0], stale=True)
    sec = SimpleNamespace(market=SimpleNamespace(price=150.5))
    kw = {"side_effect": RuntimeError("net")} if fail else {"return_value": stale}
    with patch("iam.data.markets._fetch_one", **kw):
        assert AlphaTerminal._real_history("AAPL", sec) == [150.5]


def test_real_history_empty_without_price():
    sec = SimpleNamespace(market=SimpleNamespace(price=None))
    with patch("iam.data.markets._fetch_one", side_effect=RuntimeError("net")):
        assert AlphaTerminal._real_history("AAPL", sec) == []


# 5. model portfolio ---------------------------------------------------------------
def _build_portfolio(term):
    term._sys = SystemState()
    term._watchlist = ["AAPL", "MSFT", "NVDA"]
    term._secs["AAPL"] = _real_sec("AAPL", 190.0, band="HIGH")
    term._secs["MSFT"] = _real_sec("MSFT", 400.0, band="MEDIUM")
    with patch("iam.data.markets.get_quote", return_value=None):
        term._system_worker()
    return term._sys.portfolio


def test_system_worker_builds_honest_model_portfolio(term):
    pf = _build_portfolio(term)
    by = pf.by_ticker
    assert by["AAPL"].conviction == "HIGH"
    assert by["MSFT"].conviction == "MODERATE"
    assert by["NVDA"].conviction == "UNRATED"
    assert by["AAPL"].current_price == 190.0
    assert by["NVDA"].current_price == 0.0  # unknown, rendered n/a
    for p in pf.positions:
        assert p.pnl_pct == 0.0 and p.market_value == 0.0
        assert p.weight == pytest.approx(1 / 3)
        assert p.current_price != 110.0 and p.entry_price != 100.0


def test_portfolio_panel_has_no_fabricated_pnl_or_value(term):
    pf = _build_portfolio(term)
    sys_state = SystemState(portfolio=pf, loading=False)
    out = _render(PortfolioPanel(sec_lookup=term._get_sec), None, sys_state)
    assert "Equal-Weight Model Portfolio" in out
    assert "no holdings data" in out
    assert "$190.00" in out and "n/a" in out
    assert "+10.0%" not in out
    assert "110,000" not in out
    assert "Total AUM" not in out
    assert "σ" not in out


def test_portfolio_exposures_come_from_score_results():
    a = _real_sec("AAPL", factors={"quality": (0.8, 1.0), "momentum": (0.2, 1.0)})
    b = _real_sec("MSFT", factors={"quality": (-0.4, 0.5)})
    exp = PortfolioPanel.factor_exposures([(0.5, a), (0.25, b)])
    # quality: (0.5*0.8 + 0.25*(-0.2)) / 0.75 ; momentum only from AAPL
    assert exp["quality"] == pytest.approx((0.4 - 0.05) / 0.75)
    assert exp["momentum"] == pytest.approx(0.2)
    assert PortfolioPanel.factor_exposures([(1.0, SecState(ticker="X"))]) == {}


def test_portfolio_panel_exposures_na_when_nothing_scored(term):
    pf = _build_portfolio(term)
    term._secs["AAPL"].score_result = None
    term._secs["MSFT"].score_result = None
    out = _render(
        PortfolioPanel(sec_lookup=term._get_sec), None, SystemState(portfolio=pf, loading=False)
    )
    assert "Factor exposures: n/a (no scored holdings)" in out


def test_portfolio_panel_renders_real_exposures(term):
    pf = _build_portfolio(term)
    term._secs["AAPL"].score_result.factor_breakdown = {
        "quality": SimpleNamespace(value=0.5, confidence=1.0, effective=lambda: 0.5)
    }
    out = _render(
        PortfolioPanel(sec_lookup=term._get_sec), None, SystemState(portfolio=pf, loading=False)
    )
    assert "Quality" in out and "+0.50" in out
    assert "n/a (no scored holdings)" not in out


# 7 / 8. removed fabricated code ----------------------------------------------------
def test_dead_fabrication_removed():
    assert not hasattr(at, "WatchlistPanel")
    assert not hasattr(PortfolioPanel, "_EXPOSURES")
    assert not hasattr(PortfolioPanel, "_HOLDINGS")


@pytest.mark.parametrize("module", ["iam.ui.terrain", "iam.engine.simulations"])
def test_demo_terrain_modules_are_gone(module):
    """The old terrain panel drew invented grids (saddle_demo_grid, a fixed 0.10/0.09 DCF).

    The TUI terrain now comes from visualization_lab.render_dcf_surface, so these must not return.
    """
    import importlib.util

    assert importlib.util.find_spec(module) is None
