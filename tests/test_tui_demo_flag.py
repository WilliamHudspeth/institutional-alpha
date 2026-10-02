"""Tests for the explicit --demo flag on AlphaTerminal.

Rule: demo data is only allowed behind an explicit demo=True flag.
Without the flag, a missing core import must surface as an error state
(security/pipeline_result remain None) instead of filling the state with
random mock objects.

These tests are written BEFORE the implementation, so they should fail
initially and pass after the implementation is complete.
"""

from __future__ import annotations

from unittest.mock import patch

from iam.ui import alpha_terminal as at
from iam.ui.alpha_terminal import AlphaTerminal, Canvas, SecState


def _text(cv: Canvas) -> str:
    return "\n".join("".join(ch for ch, _ in row).rstrip() for row in cv._back)


def _render(panel, sec, sys_state=None, rows=40, cols=110):
    cv = Canvas(rows, cols)
    panel.render(cv, 2, rows - 3, 2, cols - 2, sec, sys_state, ticks=1)
    return _text(cv)


# ---------------------------------------------------------------------------
# (a) Without demo flag: _IAM_CORE=False must NOT call _mock_load;
#     security and pipeline_result stay None; error mentions import failure.
# ---------------------------------------------------------------------------


def test_no_demo_core_missing_sets_error_not_mock(monkeypatch):
    """With _IAM_CORE=False and demo=False, _worker must NOT call _mock_load.

    security and pipeline_result must remain None, and st.error must mention
    the import failure message stored in _IAM_IMPORT_ERROR.
    """
    term = AlphaTerminal(demo=False)
    term._secs["TSLA"] = SecState(ticker="TSLA", loading=True)

    with patch.object(at, "_IAM_CORE", False):
        term._worker("TSLA")

    st = term._secs["TSLA"]
    assert st.security is None, "security must be None when core unavailable and demo=False"
    assert st.pipeline_result is None, "pipeline_result must be None"
    assert st.score_result is None, "score_result must be None"
    assert st.loading is False
    assert st.error is not None, "error must be set when core unavailable"
    # The error message must reference the import failure
    assert len(st.error) > 0


def test_no_demo_core_missing_error_mentions_import(monkeypatch):
    """Error message must reference the import failure, not a generic string."""
    term = AlphaTerminal(demo=False)
    term._secs["TSLA"] = SecState(ticker="TSLA", loading=True)

    with patch.object(at, "_IAM_CORE", False):
        term._worker("TSLA")

    st = term._secs["TSLA"]
    assert st.error == "iam core packages unavailable"


def test_no_demo_error_carries_the_real_import_error():
    term = AlphaTerminal(demo=False)
    term._secs["TSLA"] = SecState(ticker="TSLA", loading=True)
    with (
        patch.object(at, "_IAM_CORE", False),
        patch.object(at, "_IAM_IMPORT_ERROR", "ImportError: No module named 'yfinance'"),
    ):
        term._worker("TSLA")
    assert term._secs["TSLA"].error == "ImportError: No module named 'yfinance'"


def test_demo_flag_uses_demo_data_even_when_core_is_available():
    """--demo means demo data: the DEMO banner must never sit on top of real data."""
    term = AlphaTerminal(demo=True)
    term._secs["TSLA"] = SecState(ticker="TSLA", loading=True)
    calls = []
    term._mock_load = lambda ticker, error=None: calls.append(ticker)  # type: ignore[method-assign]
    with (
        patch.object(at, "_IAM_CORE", True),
        patch.object(at, "_fetch_security", side_effect=AssertionError("fetched real data")),
    ):
        term._worker("TSLA")
    assert calls == ["TSLA"]


def test_no_demo_mock_load_never_called(monkeypatch):
    """_mock_load must NOT be called when demo=False."""
    term = AlphaTerminal(demo=False)
    term._secs["TSLA"] = SecState(ticker="TSLA", loading=True)

    mock_load_calls = []

    def fake_mock_load(ticker, error=None):
        mock_load_calls.append(ticker)

    term._mock_load = fake_mock_load  # type: ignore[method-assign]

    with patch.object(at, "_IAM_CORE", False):
        term._worker("TSLA")

    assert mock_load_calls == [], "_mock_load must not be called when demo=False"


# ---------------------------------------------------------------------------
# (b) With demo=True: data must load (mock) and the header must show "DEMO"
# ---------------------------------------------------------------------------


def test_demo_on_calls_mock_load(monkeypatch):
    """With demo=True and _IAM_CORE=False, _worker must call _mock_load."""
    term = AlphaTerminal(demo=True)
    term._secs["TSLA"] = SecState(ticker="TSLA", loading=True)

    mock_load_calls = []

    def fake_mock_load(ticker, error=None):
        mock_load_calls.append(ticker)
        # Simulate what _mock_load does to avoid KeyError
        st = term._secs[ticker]
        st.security = at._MockSec(ticker, 123.0)
        st.score_result = at._MockScore()
        st.pipeline_result = at._MockPipeline()
        st.loading = False
        st.error = None

    term._mock_load = fake_mock_load  # type: ignore[method-assign]

    with patch.object(at, "_IAM_CORE", False):
        term._worker("TSLA")

    assert "TSLA" in mock_load_calls, "_mock_load must be called when demo=True"


def test_demo_on_sets_is_demo_on_secstate(monkeypatch):
    """After demo=True load, st.is_demo must be True."""
    term = AlphaTerminal(demo=True)
    term._secs["TSLA"] = SecState(ticker="TSLA", loading=True)

    with (
        patch.object(at, "_IAM_CORE", False),
        patch("time.sleep"),  # don't actually sleep
    ):
        term._worker("TSLA")

    st = term._secs["TSLA"]
    assert st.is_demo is True, "is_demo must be True when demo=True"
    assert st.security is not None, "security must not be None in demo mode"
    assert st.pipeline_result is not None, "pipeline_result must not be None in demo mode"


def test_demo_header_contains_demo_banner():
    """When demo=True, the header row drawn by _draw_header must include 'DEMO'."""
    term = AlphaTerminal(demo=True)
    cv = Canvas(30, 120)
    term._draw_header(cv, 30, 120)
    rendered = _text(cv)
    assert "DEMO" in rendered, f"'DEMO' not found in header. Got:\n{rendered}"


def test_no_demo_header_has_no_demo_banner():
    """When demo=False, the header must NOT include a 'DEMO' banner."""
    term = AlphaTerminal(demo=False)
    cv = Canvas(30, 120)
    term._draw_header(cv, 30, 120)
    rendered = _text(cv)
    assert "DEMO" not in rendered, f"'DEMO' found in non-demo header. Got:\n{rendered}"


# ---------------------------------------------------------------------------
# AlphaTerminal constructor accepts demo kwarg
# ---------------------------------------------------------------------------


def test_alphaterminal_accepts_demo_kwarg():
    """AlphaTerminal(demo=True) and AlphaTerminal(demo=False) must not raise."""
    t1 = AlphaTerminal(demo=True)
    assert t1._demo is True

    t2 = AlphaTerminal(demo=False)
    assert t2._demo is False


def test_alphaterminal_default_demo_is_false():
    """AlphaTerminal() with no args must default to demo=False."""
    t = AlphaTerminal()
    assert t._demo is False
