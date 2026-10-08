"""F9 Visualization Lab SOTP tower must never value invented segments (no fabricated values)."""

from __future__ import annotations

from unittest.mock import patch

from iam.data.security import MarketData
from iam.ui import visualization_lab as vl
from tests.fixtures.sample_securities import make_security, sample_segments


def test_no_segments_reports_insufficient_data_without_computing():
    sec = make_security(ticker="NOSEG", total_debt=1e9)
    sec.market = MarketData(market_cap=1e10)
    assert not sec.qualitative.get("segments")

    with patch.object(vl.SOTP, "compute") as compute:
        text = vl.sotp_tower_report(sec)

    compute.assert_not_called()
    assert "insufficient data" in text
    assert "no segment data for NOSEG" in text
    for invented in ("iShares", "Aladdin", "GIP", "HPS", "Cost of Equity"):
        assert invented not in text


def test_mock_blk_segments_is_gone():
    assert not hasattr(vl, "mock_blk_segments")


def test_no_debt_to_equity_reports_insufficient_data():
    # Segments present but neither a D/E ratio nor both debt and market cap.
    sec = make_security(ticker="NODE")
    sec.qualitative["segments"] = sample_segments()

    with patch.object(vl.SOTP, "compute") as compute:
        text = vl.sotp_tower_report(sec)

    compute.assert_not_called()
    assert "insufficient data" in text
    assert "no debt/equity for NODE" in text


def test_missing_market_cap_does_not_default_to_one():
    sec = make_security(ticker="NOCAP", total_debt=5e9)
    sec.qualitative["segments"] = sample_segments()

    text = vl.sotp_tower_report(sec)

    assert "insufficient data" in text


def test_real_segments_render_tower_with_cost_of_equity():
    sec = make_security(ticker="SEG", total_debt=2e9)
    sec.market = MarketData(market_cap=1e10)
    sec.qualitative["segments"] = sample_segments()

    text = vl.sotp_tower_report(sec)

    assert "insufficient data" not in text
    assert "SegmentA" in text and "SegmentB" in text
    assert "Cost of Equity:" in text
    assert "Weighted Unlevered Beta:" in text
    # The relevering tax is the company's marginal rate, stated with its source (no 21% default).
    assert "Marginal tax rate: 25.00% (United States statutory tax 25.00%" in text


def test_qualitative_de_ratio_is_used():
    sec = make_security(ticker="QDE")
    sec.qualitative["segments"] = sample_segments()
    sec.qualitative["current_de_ratio"] = 0.3

    with patch.object(vl.DamodaranEngine, "compute_cost_of_equity", return_value=0.09) as coe:
        text = vl.sotp_tower_report(sec)

    assert coe.call_args.args[1] == 0.3
    assert "Cost of Equity: 9.00%" in text
