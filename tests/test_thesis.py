"""Tests for the Thesis dataclass and show_spread functionality."""

import pytest

from iam.data.security import Security, Thesis, Assumption, show_spread


def test_thesis_validation_prevents_inverted_range():
    """Ensures that fair_value_low cannot be greater than fair_value_high."""
    with pytest.raises(ValueError, match="must not exceed"):
        Thesis(label="Inverted", fair_value_low=120.0, fair_value_high=100.0)


def test_show_spread_no_theses():
    """Test formatting when a security has no theses."""
    sec = Security(ticker="TEST")
    assert show_spread(sec) == "No theses attached."


def test_show_spread_single_thesis():
    """Test formatting with a single thesis."""
    thesis = Thesis(
        label="Base Case",
        fair_value_low=100.0,
        fair_value_high=120.0,
        narrative="Steady state compounding.",
        assumptions=[Assumption(name="Growth", value="5%")]
    )
    sec = Security(ticker="TEST", theses=[thesis])
    output = show_spread(sec)
    
    assert "Thesis: Base Case" in output
    assert "Fair value range: 100.00 - 120.00" in output
    assert "Steady state compounding." in output
    assert "Spread" not in output


def test_show_spread_multiple_theses_narrow():
    """Test multiple theses where spread is <= 30% of midpoint (no [wide] flag)."""
    theses = [
        Thesis(label="Bear", fair_value_low=90.0, fair_value_high=100.0),
        Thesis(label="Bull", fair_value_low=105.0, fair_value_high=115.0),
    ]
    sec = Security(ticker="TEST", theses=theses)
    output = show_spread(sec)
    
    # Max high = 115, Min low = 90. Spread = 25. Midpoint = 102.5. 30% of mid = 30.75
    assert "Spread: 25.00 (high 115.00 - low 90.00)" in output
    assert "[wide]" not in output


def test_show_spread_multiple_theses_wide():
    """Test multiple theses where spread is > 30% of midpoint (triggers [wide] flag)."""
    theses = [
        Thesis(label="Bear", fair_value_low=50.0, fair_value_high=60.0),
        Thesis(label="Bull", fair_value_low=140.0, fair_value_high=150.0),
    ]
    sec = Security(ticker="TEST", theses=theses)
    output = show_spread(sec)
    
    # Max high = 150, Min low = 50. Spread = 100. Midpoint = 100. 30% of mid = 30.00
    assert "Spread: 100.00 (high 150.00 - low 50.00) [wide]" in output