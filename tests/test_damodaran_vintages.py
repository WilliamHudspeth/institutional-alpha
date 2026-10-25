"""Offline tests for Damodaran historical vintage parsing and caching."""

from __future__ import annotations

import hashlib
import io
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from iam.backtest.track_a.damodaran_vintages import (
    ParsedDataset,
    TrackADataError,
    industry_value,
    load_vintage,
    normalise_industry,
    parse_dataset,
    resolve_vintage,
    vintage_for,
    vintage_url,
)
from iam.backtest.track_b.cache import TrackBDataError


def _grid(rows: list[list[object]]) -> pd.DataFrame:
    width = max(len(r) for r in rows)
    padded = [r + [np.nan] * (width - len(r)) for r in rows]
    return pd.DataFrame(padded)


def test_vintage_for_january_cutoff() -> None:
    assert vintage_for(date(2024, 1, 14)) == 2023
    assert vintage_for(date(2024, 1, 15)) == 2024
    assert vintage_for("2010-01-14") == 2009
    assert vintage_for("2010-01-15") == 2010


def test_resolve_vintage_cases() -> None:
    c_2025 = resolve_vintage(date(2025, 3, 1))
    assert (c_2025.year_wanted, c_2025.year_used, c_2025.stale) == (2025, 2025, False)

    c_2026 = resolve_vintage(date(2026, 2, 1))
    assert (c_2026.year_wanted, c_2026.year_used, c_2026.stale) == (2026, 2026, False)

    c_2010 = resolve_vintage(date(2010, 6, 30))
    assert (c_2010.year_wanted, c_2010.year_used, c_2010.stale) == (2010, 2010, False)

    # A year after the current file: fall back to it, flagged stale, never forward.
    c_2027 = resolve_vintage(date(2027, 3, 1))
    assert (c_2027.year_used, c_2027.stale) == (2026, True)
    assert c_2027.reason is not None and "2026" in c_2027.reason

    with pytest.raises(ValueError, match="1999"):
        resolve_vintage(date(1999, 6, 1))
    with pytest.raises(ValueError, match="1999"):
        resolve_vintage(date(2000, 1, 14))


def test_vintage_url_uses_the_data_year_suffix() -> None:
    # The file suffix is the data year: the January 2000 vintage is betas99.xls and the
    # January 2025 vintage is betas24.xls ("Date updated: 2025-01-05").
    base = "https://pages.stern.nyu.edu/~adamodar/pc/"
    assert vintage_url("betas", 2000) == base + "archives/betas99.xls"
    assert vintage_url("betas", 2006) == base + "archives/betas05.xls"
    assert vintage_url("wacc", 2025) == base + "archives/wacc24.xls"
    assert vintage_url("betas", 2026) == base + "datasets/betas.xls"
    with pytest.raises(ValueError, match="1999"):
        vintage_url("betas", 1999)
    with pytest.raises(ValueError, match="2027"):
        vintage_url("betas", 2027)


def test_crosswalk_entries_are_well_formed() -> None:
    from iam.backtest.track_a.industry_crosswalk import INDUSTRY_CROSSWALK

    keys = set(INDUSTRY_CROSSWALK)
    for old, (target, source, _note) in INDUSTRY_CROSSWALK.items():
        assert target is None or target not in keys, f"{old} maps to another old name"
        assert source
    for region in (
        "Electric Util. (Central)",
        "Electric Utility (East)",
        "Electric Utility (West)",
    ):
        assert INDUSTRY_CROSSWALK[region][0] == "Power"
    assert INDUSTRY_CROSSWALK["Bank (Canadian)"][0] is None


def test_old_vintage_is_rekeyed_to_current_names_with_firm_weights() -> None:
    from iam.backtest.track_a.damodaran_vintages import current_industry, to_current_industries

    grid = _grid(
        [
            ["Industry Name", "Number of Firms", "ROE", "Retention Ratio", "Fundamental Growth"],
            ["Electric Util. (Central)", 30, 0.10, 0.4, 0.04],
            ["Electric Utility (East)", 10, 0.06, 0.5, 0.03],
            ["Bank (Canadian)", 8, 0.15, 0.6, 0.09],
            ["Advertising", 20, 0.12, 0.3, 0.036],
        ]
    )
    parsed = parse_dataset("fundgr", {"Sheet1": grid})
    current, unmapped = to_current_industries(parsed)
    assert unmapped == ("Bank (Canadian)",)
    assert current.loc["Power", "n_firms"] == 40
    assert current.loc["Power", "roe"] == pytest.approx((30 * 0.10 + 10 * 0.06) / 40)
    assert current.loc["Advertising", "roe"] == pytest.approx(0.12)
    assert industry_value(parsed, "Power", "fundamental_growth") == pytest.approx(
        (30 * 0.04 + 10 * 0.03) / 40
    )
    assert industry_value(parsed, "Bank (Canadian)", "roe") is None
    assert current_industry("Advertising") == "Advertising"
    assert current_industry("Bank (Canadian)") is None


def test_2014_layout_with_plain_industry_header() -> None:
    grid = _grid(
        [
            ["Date updated:", "2015-01-05"],
            ["Industry definitions:", "see the Industry list"],
            ["Industry", "Number of firms", "Beta ", "D/E Ratio", "Tax rate", "Unlevered beta",
             "Cash/Firm value", "Unlevered beta corrected for cash"],
            ["Advertising", 52, 1.18, 0.51, 0.04, 0.80, 0.05, 0.84],
        ]
    )  # fmt: skip
    parsed = parse_dataset("betas", {"Sheet1": grid})
    assert parsed.header_row == 2
    assert parsed.frame.loc["Advertising", "unlevered_beta_cash_corrected"] == pytest.approx(0.84)


def test_parse_2005_style_betas_header_at_row_zero() -> None:
    grid = _grid(
        [
            [
                "Industry Name",
                "Number of Firms",
                "Average Beta",
                "Market D/E Ratio",
                "Tax Rate",
                "Unlevered Beta",
                "Unlevered Beta corrected for cash",
            ],
            ["Aerospace/Defense", 65, 0.95, "18.50%", "24.00%", 0.84, 0.88],
            ["Banks (Regional)", 210, 0.72, "85.00%", "30.00%", 0.45, 0.46],
        ]
    )
    parsed = parse_dataset("betas", {"Sheet1": grid})
    assert parsed.sheet == "Sheet1"
    assert parsed.header_row == 0
    assert parsed.missing_optional == ()
    assert list(parsed.frame.index) == ["Aerospace/Defense", "Banks (Regional)"]
    assert parsed.frame.at["Aerospace/Defense", "beta"] == pytest.approx(0.95)
    assert parsed.frame.at["Aerospace/Defense", "de_ratio"] == pytest.approx(0.185)
    assert parsed.frame.at["Aerospace/Defense", "tax_rate"] == pytest.approx(0.24)
    assert parsed.frame.at["Aerospace/Defense", "unlevered_beta_cash_corrected"] == pytest.approx(
        0.88
    )


def test_parse_2024_style_betas_with_faq_sheet_year_cols_and_totals() -> None:
    faq = _grid([["Notes"], ["Explain columns"]])
    preamble = [[f"meta {i}"] for i in range(9)]
    header = [
        "Industry Name",
        "Number of firms",
        "Beta",
        "D/E Ratio",
        "Effective Tax rate",
        "Unlevered beta",
        "Unlevered beta corrected for cash",
        "2021",
        2022.0,
    ]
    body = [
        ["Software (System & Application)", 350, 1.24, 0.08, "15.2%", 1.17, 1.21, 1.10, 1.15],
        ["Retail (General)", 45, 1.05, 0.32, "21.0%", 0.84, 0.87, 0.90, 0.95],
        ["Total Market", 6500, 1.00, 0.40, "18.0%", 0.76, 0.79, 0.75, 0.77],
        ["Total Market (without financials)", 5200, 1.04, 0.25, "17.5%", 0.86, 0.90, 0.82, 0.85],
        [None, None, None],
        ["Trailing note that must not be read", 1, 1, 1, 1, 1, 1, 1, 1],
    ]
    averages = _grid(preamble + [header] + body)
    parsed = parse_dataset(
        "betas",
        {"Explanations & FAQ": faq, "Industry Averages": averages},
    )
    assert parsed.sheet == "Industry Averages"
    assert parsed.header_row == 9
    assert list(parsed.frame.index) == ["Software (System & Application)", "Retail (General)"]
    assert "2021" not in parsed.frame.columns
    assert parsed.frame.at["Retail (General)", "tax_rate"] == pytest.approx(0.21)


def test_parse_wacc_ignores_local_currency_column() -> None:
    grid = _grid(
        [
            [
                "Industry Name",
                "Number of Firms",
                "Cost of Equity",
                "Cost of Debt",
                "After-tax Cost of Debt",
                "Cost of Capital",
                "Cost of Capital (Local Currency)",
            ],
            ["Drugs (Biotechnology)", 480, "10.50%", "5.20%", "4.10%", "9.40%", "99.90%"],
        ]
    )
    parsed = parse_dataset("wacc", {"Industry Averages": grid})
    assert parsed.frame.at["Drugs (Biotechnology)", "cost_of_capital"] == pytest.approx(0.094)


def test_parse_vebitda_duplicate_column_takes_first() -> None:
    grid = _grid(
        [
            [
                "Industry Name",
                "Number of firms",
                "EV/EBITDA",
                "EV/EBIT",
                "EV/EBITDA",
                "EV/EBITDA3",
            ],
            ["Semiconductor", 70, 22.5, 28.0, 16.2, 15.8],
        ]
    )
    parsed = parse_dataset("vebitda", {"Industry Averages": grid})
    assert parsed.frame.at["Semiconductor", "ev_ebitda"] == pytest.approx(22.5)
    assert parsed.frame.at["Semiconductor", "ev_ebit"] == pytest.approx(28.0)


def test_missing_required_raises_and_missing_optional_reported() -> None:
    bad_wacc = _grid(
        [
            ["Industry Name", "Number of Firms", "Cost of Equity", "Cost of Debt"],
            ["Auto & Truck", 30, 0.09, 0.05],
        ]
    )
    with pytest.raises(TrackADataError) as exc_info:
        parse_dataset("wacc", {"Sheet1": bad_wacc})
    msg = str(exc_info.value)
    assert "wacc" in msg
    assert "cost_of_capital" in msg
    assert "Cost of Equity" in msg

    capex_1999 = _grid(
        [
            ["Industry Name", "Number of Firms", "Net Cap Ex/Sales"],
            ["Chemical (Basic)", 40, "6.5%"],
        ]
    )
    parsed = parse_dataset("capex", {"Sheet1": capex_1999})
    assert parsed.missing_optional == ("sales_to_capital",)
    assert "sales_to_capital" not in parsed.frame.columns
    assert parsed.frame.at["Chemical (Basic)", "net_capex_sales"] == pytest.approx(0.065)


def test_duplicate_industry_raises_and_stops_at_first_blank() -> None:
    dup_grid = _grid(
        [
            ["Industry Name", "Number of Firms", "ROE", "Retention Ratio", "Fundamental Growth"],
            ["Steel", 20, 0.12, 0.60, 0.072],
            ["Steel", 22, 0.14, 0.65, 0.091],
        ]
    )
    with pytest.raises(TrackADataError, match="Steel"):
        parse_dataset("fundgr", {"Sheet1": dup_grid})

    stop_grid = _grid(
        [
            ["Industry Name", "Number of Firms", "ROE", "Retention Ratio", "Fundamental Growth"],
            ["Steel", 20, "12.0%", "60.0%", "7.2%"],
            ["", 10, 0.10, 0.50, 0.05],
            ["Coal", 15, 0.08, 0.40, 0.032],
        ]
    )
    parsed = parse_dataset("fundgr", {"Sheet1": stop_grid})
    assert list(parsed.frame.index) == ["Steel"]
    assert parsed.frame.at["Steel", "roe"] == pytest.approx(0.12)


def test_normalise_industry_and_lookup() -> None:
    assert normalise_industry("Banks (Regional)") == "banks regional"
    assert (
        normalise_industry("Oil/Gas (Production and Exploration)")
        == "oil/gas production and exploration"
    )
    assert normalise_industry("Retail (General)") == "retail"
    assert normalise_industry("R.E.I.T.") == "reit"
    assert normalise_industry("Metals & Mining") == "metals and mining"

    grid = _grid(
        [
            ["Industry Name", "Number of Firms", "Price/Sales", "EV/Sales"],
            ["Retail (General)", 40, 1.2, 1.5],
            ["R.E.I.T.", 120, 8.4, 14.2],
        ]
    )
    parsed = parse_dataset("psdata", {"Sheet1": grid})
    assert industry_value(parsed, "Retail", "price_sales") == pytest.approx(1.2)
    assert industry_value(parsed, "REIT", "ev_sales") == pytest.approx(14.2)
    assert industry_value(parsed, "Nonexistent", "price_sales") is None
    assert industry_value(parsed, "Retail", "nonexistent_col") is None


def test_load_vintage_caches_and_records_sha256(tmp_path: Path) -> None:
    grid = _grid(
        [
            ["Industry Name", "Number of Firms", "ROE", "Retention Ratio", "Fundamental Growth"],
            ["Machinery", 55, "15.0%", "70.0%", "10.5%"],
        ]
    )
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        grid.to_excel(writer, sheet_name="Industry Averages", header=False, index=False)
    payload = buf.getvalue()
    expected_sha = hashlib.sha256(payload).hexdigest()

    calls: list[str] = []

    def fake_transport(url: str) -> bytes:
        calls.append(url)
        return payload

    parsed, record = load_vintage("fundgr", 2015, cache_root=tmp_path, transport=fake_transport)
    assert isinstance(parsed, ParsedDataset)
    # Publication year 2015 is the file with data year 2014.
    assert calls == ["https://pages.stern.nyu.edu/~adamodar/pc/archives/fundgr14.xls"]
    assert record.sha256 == expected_sha
    assert (tmp_path / "2015" / "fundgr14.xls").read_bytes() == payload
    assert industry_value(parsed, "Machinery", "fundamental_growth") == pytest.approx(0.105)

    # Second call uses the cached file without hitting the transport.
    parsed_cached, record_cached = load_vintage(
        "fundgr", 2015, cache_root=tmp_path, transport=fake_transport
    )
    assert len(calls) == 1
    assert record_cached.sha256 == expected_sha
    assert parsed_cached.frame.equals(parsed.frame)


def test_load_vintage_rejects_corrupt_bytes(tmp_path: Path) -> None:
    assert issubclass(TrackADataError, TrackBDataError)
    with pytest.raises(TrackADataError):
        load_vintage("fundgr", 2015, cache_root=tmp_path, transport=lambda _url: b"not-an-excel")
