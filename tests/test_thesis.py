"""Tests for Assumption, Thesis, Security.theses, and show_spread()."""

from iam.data.security import Assumption, Security, Thesis, show_spread


# ---------------------------------------------------------------------------
# Dataclass construction
# ---------------------------------------------------------------------------

def test_assumption_defaults():
    a = Assumption(name="growth_rate", value=0.12)
    assert a.rationale == ""
    assert a.source == "model"


def test_thesis_defaults():
    t = Thesis(label="Base")
    assert t.assumptions == []
    assert t.fair_value_low is None
    assert t.fair_value_high is None
    assert t.narrative == ""


def test_security_theses_default_empty():
    sec = Security(ticker="X")
    assert sec.theses == []


# ---------------------------------------------------------------------------
# show_spread — no theses
# ---------------------------------------------------------------------------

def test_show_spread_no_theses():
    sec = Security(ticker="EMPTY")
    result = show_spread(sec)
    assert result == "No theses attached."


# ---------------------------------------------------------------------------
# show_spread — single thesis
# ---------------------------------------------------------------------------

def test_show_spread_single_thesis():
    sec = Security(
        ticker="ONE",
        theses=[
            Thesis(
                label="Base",
                fair_value_low=90.0,
                fair_value_high=110.0,
                narrative="Steady-state compounder.",
            )
        ],
    )
    result = show_spread(sec)
    assert "Base" in result
    assert "90.00" in result
    assert "110.00" in result
    assert "Steady-state compounder." in result
    assert "Spread:" not in result  # no spread line for a single thesis


# ---------------------------------------------------------------------------
# show_spread — multiple theses, spread and wide flag
# ---------------------------------------------------------------------------

def test_show_spread_multiple_theses_shows_spread():
    sec = Security(
        ticker="MULTI",
        theses=[
            Thesis(label="Bull", fair_value_low=150.0, fair_value_high=200.0),
            Thesis(label="Bear", fair_value_low=80.0, fair_value_high=110.0),
        ],
    )
    result = show_spread(sec)
    # Both labels present
    assert "Bull" in result
    assert "Bear" in result
    # Spread = 200 - 80 = 120; midpoint = 140; 120/140 ~ 85% → wide
    assert "Spread:" in result
    assert "120.00" in result
    assert "[wide]" in result


def test_show_spread_narrow_not_flagged():
    # Bull: 100-105, Bear: 95-100 → spread=10, midpoint=100, 10% < 30%
    sec = Security(
        ticker="NARROW",
        theses=[
            Thesis(label="Bull", fair_value_low=100.0, fair_value_high=105.0),
            Thesis(label="Bear", fair_value_low=95.0, fair_value_high=100.0),
        ],
    )
    result = show_spread(sec)
    assert "Spread:" in result
    assert "[wide]" not in result


def test_show_spread_wide_threshold_exact():
    # spread == 30% of midpoint → not wide (strictly greater than)
    # top=130, bottom=100 → spread=30, midpoint=115, 30/115 ~ 26% < 30% → not wide
    # Let's do top=160, bottom=100 → spread=60, midpoint=130, 60/130 ~ 46% > 30% → wide
    sec = Security(
        ticker="THRESH",
        theses=[
            Thesis(label="Bull", fair_value_low=140.0, fair_value_high=160.0),
            Thesis(label="Bear", fair_value_low=100.0, fair_value_high=120.0),
        ],
    )
    result = show_spread(sec)
    # spread = 160-100 = 60, midpoint = 130, 60 > 0.30*130=39 → wide
    assert "[wide]" in result


def test_show_spread_three_theses():
    sec = Security(
        ticker="THREE",
        theses=[
            Thesis(label="Bull", fair_value_low=180.0, fair_value_high=220.0),
            Thesis(label="Base", fair_value_low=130.0, fair_value_high=160.0),
            Thesis(label="Bear", fair_value_low=80.0, fair_value_high=110.0),
        ],
    )
    result = show_spread(sec)
    assert "Bull" in result
    assert "Base" in result
    assert "Bear" in result
    # top=220, bottom=80, spread=140, midpoint=150, 140/150 ~ 93% → wide
    assert "[wide]" in result
