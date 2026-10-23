"""Offline tests for the Track B loaders (JKP, OSAP, French, Damodaran ERP) and factor map."""

import hashlib
import io
import json
import zipfile
from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from iam.backtest import weight_selection as ws
from iam.backtest.track_b import damodaran_erp, factor_map, french, jkp, osap
from iam.backtest.track_b.cache import DownloadCache, TrackBDataError
from iam.backtest.weight_selection import CandidateContext, run_horse_race


class FakeTransport:
    """Serves canned bodies by URL and counts calls."""

    def __init__(self, bodies=None, fail=False):
        self.bodies = dict(bodies or {})
        self.fail = fail
        self.calls = []

    def __call__(self, url):
        self.calls.append(url)
        if self.fail:
            raise OSError("network down")
        return self.bodies[url]


class Clock:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


def _zip(name, text):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(name, text)
    return buf.getvalue()


def _cache(tmp_path, bodies, **kw):
    transport = FakeTransport(bodies)
    return DownloadCache(tmp_path, transport=transport, **kw), transport


# --------------------------------------------------------------------------- #
# DownloadCache
# --------------------------------------------------------------------------- #


class TestDownloadCache:
    def test_second_fetch_is_served_from_disk(self, tmp_path):
        cache, transport = _cache(tmp_path, {"https://x/a": b"hello"})
        assert cache.fetch("a", "https://x/a") == b"hello"
        assert cache.fetch("a", "https://x/a") == b"hello"
        assert len(transport.calls) == 1

        again = DownloadCache(tmp_path, transport=FakeTransport())
        assert again.fetch("a", "https://x/a") == b"hello"
        assert again.network_calls == 0

    def test_provenance_records_sha256(self, tmp_path):
        cache, _ = _cache(tmp_path, {"https://x/a": b"hello"})
        cache.fetch("a", "https://x/a")
        (rec,) = cache.provenance()
        assert rec["sha256"] == hashlib.sha256(b"hello").hexdigest()
        assert rec["size_bytes"] == 5
        assert rec["url"] == "https://x/a"

    def test_corrupted_file_is_downloaded_again(self, tmp_path):
        cache, transport = _cache(tmp_path, {"https://x/a": b"hello"})
        cache.fetch("a", "https://x/a")
        (tmp_path / "a").write_bytes(b"tampered")
        assert cache.fetch("a", "https://x/a") == b"hello"
        assert len(transport.calls) == 2

    def test_stale_copy_is_refreshed(self, tmp_path):
        clock = Clock()
        cache, transport = _cache(
            tmp_path, {"https://x/a": b"v1"}, ttl_seconds=10, wall_clock=clock
        )
        cache.fetch("a", "https://x/a")
        transport.bodies["https://x/a"] = b"v2"
        clock.t += 11
        assert cache.fetch("a", "https://x/a") == b"v2"

    def test_failed_refresh_falls_back_to_cached_copy(self, tmp_path):
        cache, transport = _cache(tmp_path, {"https://x/a": b"v1"})
        cache.fetch("a", "https://x/a")
        transport.fail = True
        assert cache.fetch("a", "https://x/a", refresh=True) == b"v1"

    def test_failure_without_cache_raises(self, tmp_path):
        cache = DownloadCache(tmp_path, transport=FakeTransport(fail=True))
        with pytest.raises(TrackBDataError, match="download failed"):
            cache.fetch("a", "https://x/a")

    def test_empty_body_raises(self, tmp_path):
        cache, _ = _cache(tmp_path, {"https://x/a": b""})
        with pytest.raises(TrackBDataError, match="empty"):
            cache.fetch("a", "https://x/a")

    def test_changed_url_triggers_download(self, tmp_path):
        cache, transport = _cache(tmp_path, {"https://x/a": b"v1", "https://x/b": b"v2"})
        cache.fetch("k", "https://x/a")
        assert cache.fetch("k", "https://x/b") == b"v2"
        assert len(transport.calls) == 2

    def test_lazy_url_is_not_resolved_when_cached(self, tmp_path):
        cache, _ = _cache(tmp_path, {"https://x/a": b"v1"})
        resolved = []

        def url():
            resolved.append(1)
            return "https://x/a"

        cache.fetch("k", url)
        cache.fetch("k", url)
        assert resolved == [1]
        meta = json.loads((tmp_path / "k.json").read_text())
        assert meta["url"] == "https://x/a"

    def test_bracketed_keys_are_file_system_safe(self, tmp_path):
        cache, _ = _cache(tmp_path, {"https://x/a": b"v"})
        cache.fetch("jkp_[usa]_[all_factors].zip", "https://x/a")
        assert all("[" not in p.name for p in tmp_path.iterdir())


# --------------------------------------------------------------------------- #
# Kenneth French
# --------------------------------------------------------------------------- #

FF5_TEXT = """This file was created using the 202608 CRSP database.
The 1-month TBill rate data until 202405 are from Ibbotson Associates.

,Mkt-RF,SMB,HML,RMW,CMA,RF
196307,   -0.39,   -0.48,   -0.84,    0.64,   -1.15,    0.27
196308,    5.08,   -0.80,    1.72,    0.40,   -0.38,    0.25
196309,   -1.57,   -0.43,  -99.99,   -0.78,    0.15,    0.27

 Annual Factors: January-December
,Mkt-RF,SMB,HML,RMW,CMA,RF
  1964,   12.00,    0.10,    9.00,    1.00,    2.00,    3.50

Copyright 2026 Eugene F. Fama and Kenneth R. French
"""

IND_TEXT = """It contains value- and equal-weighted returns for 49 industry portfolios.

  Average Value Weighted Returns -- Monthly
,Agric,Food ,Soda
192607,   2.37,   0.12,  -999
192608,   2.23,   2.68,   1.00

  Average Equal Weighted Returns -- Monthly
,Agric,Food,Soda
192607,   1.00,   2.00,   3.00

  Number of Firms in Portfolios
,Agric,Food,Soda
192607,   5,   30,   1
"""


class TestFrench:
    def test_tables_split_by_date_width(self):
        tables = french.parse_french_csv(FF5_TEXT)
        assert [t.frequency for t in tables] == ["monthly", "annual"]
        monthly, annual = tables
        assert list(monthly.data.columns) == ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "RF"]
        assert monthly.data.index[0] == pd.Timestamp("1963-07-31")
        assert annual.data.index[0] == pd.Timestamp("1964-12-31")
        assert annual.title == "Annual Factors: January-December"

    def test_missing_codes_become_nan(self):
        monthly = french.parse_french_csv(FF5_TEXT)[0].data
        assert np.isnan(monthly.loc["1963-09-30", "HML"])
        industries = french.parse_french_csv(IND_TEXT)[0].data
        assert np.isnan(industries.loc["1926-07-31", "Soda"])

    def test_column_names_are_stripped(self):
        assert list(french.parse_french_csv(IND_TEXT)[0].data.columns) == ["Agric", "Food", "Soda"]

    def test_ff5_loader_returns_decimals(self, tmp_path):
        url = french.french_url(french.FF5_DATASET)
        cache, _ = _cache(tmp_path, {url: _zip("F-F_Research_Data_5_Factors_2x3.csv", FF5_TEXT)})
        ff5 = french.french_ff5_monthly(cache)
        assert ff5.loc["1963-08-31", "Mkt-RF"] == pytest.approx(0.0508)
        assert len(ff5) == 3

    def test_industry_loader_picks_weighting_by_title(self, tmp_path):
        url = french.french_url(french.INDUSTRY49_DATASET)
        cache, _ = _cache(tmp_path, {url: _zip("49_Industry_Portfolios.csv", IND_TEXT)})
        vw = french.french_industry49_monthly(cache, "value")
        ew = french.french_industry49_monthly(cache, "equal")
        assert vw.loc["1926-07-31", "Agric"] == pytest.approx(0.0237)
        assert ew.loc["1926-07-31", "Agric"] == pytest.approx(0.01)
        with pytest.raises(ValueError):
            french.french_industry49_monthly(cache, "cap")

    def test_momentum_loader(self, tmp_path):
        text = "Mom header text\n\n,Mom\n192701,   0.57\n192702,  -1.50\n"
        url = french.french_url(french.MOMENTUM_DATASET)
        cache, _ = _cache(tmp_path, {url: _zip("F-F_Momentum_Factor.csv", text)})
        mom = french.french_momentum_monthly(cache)
        assert mom.iloc[1] == pytest.approx(-0.015)

    def test_missing_expected_column_raises(self, tmp_path):
        text = FF5_TEXT.replace("CMA", "XXX")
        url = french.french_url(french.FF5_DATASET)
        cache, _ = _cache(tmp_path, {url: _zip("f.csv", text)})
        with pytest.raises(TrackBDataError, match="CMA"):
            french.french_ff5_monthly(cache)

    def test_file_without_tables_raises(self):
        with pytest.raises(TrackBDataError):
            french.parse_french_csv("just text\nno tables here\n")


# --------------------------------------------------------------------------- #
# Damodaran ERP
# --------------------------------------------------------------------------- #


def _histimpl_grid(drop=None):
    header = [
        "Year",
        "Earnings Yield",
        "Dividend Yield",
        "S&P 500",
        "T.Bill Rate",
        "T.Bond Rate",
        "Implied Premium (DDM)",
        "Implied ERP (FCFE)",
    ]
    if drop:
        header = [h if h != drop else "Something else" for h in header]
    rows = [
        ["Date updated:", datetime(2025, 1, 5)] + [None] * 6,
        ["Created by:", "Aswath Damodaran"] + [None] * 6,
        [None] * 8,
        header,
        [1960, 0.0534, 0.0341, 58.11, 0.0266, 0.0276, None, None],
        [1961, 0.0471, 0.0285, 71.55, 0.0213, 0.0235, 0.0292, 0.0292],
        [2024, 0.0414, 0.0125, 5881.6, 0.043, 0.0458, 0.0390, 0.0433],
        [None] * 8,
        [None, "1960-2024", 0.04, 0.07, None, None, None, None],
        ["Arithmetic Average", 0.01, None, None, None, None, None, None],
    ]
    return pd.DataFrame(rows)


def _monthly_grid():
    header = ["Start of month", "S&P 500", "T.Bond Rate", "ERP (T12m)", "ERP (Normalized)", "Notes"]
    rows = [
        header,
        [datetime(2008, 9, 1), 1252, 0.0372, 0.0422, None, None],
        [datetime(2008, 10, 1), 1166, 0.0383, 0.0451, None, None],
        [datetime(2026, 10, 1), 7652, 0.0529, 0.037, 0.0361, "Updated"],
        [None] * 6,
        ["Average", 0.05, None, None, None, None],
    ]
    return pd.DataFrame(rows)


class TestDamodaranERP:
    def test_annual_rows_stop_at_summary_block(self):
        out = damodaran_erp.parse_histimpl(_histimpl_grid())
        assert list(out.index) == [1960, 1961, 2024]
        assert out.loc[2024, "erp_fcfe"] == pytest.approx(0.0433)
        assert out.loc[1961, "erp_ddm"] == pytest.approx(0.0292)
        assert np.isnan(out.loc[1960, "erp_fcfe"])
        assert "erp_fcfe_sustainable" not in out.columns  # optional and absent

    def test_annual_value_is_usable_from_mid_january_next_year(self):
        out = damodaran_erp.parse_histimpl(_histimpl_grid())
        assert out.loc[2024, "available_from"] == pd.Timestamp("2025-01-15")
        assert damodaran_erp.erp_as_of(
            out, pd.Timestamp("2025-01-14"), "erp_fcfe"
        ) == pytest.approx(0.0292)
        assert damodaran_erp.erp_as_of(
            out, pd.Timestamp("2025-01-15"), "erp_fcfe"
        ) == pytest.approx(0.0433)
        assert damodaran_erp.erp_as_of(out, pd.Timestamp("1961-01-01"), "erp_fcfe") is None

    def test_missing_required_header_fails_loudly(self):
        with pytest.raises(TrackBDataError, match="Implied ERP"):
            damodaran_erp.parse_histimpl(_histimpl_grid(drop="Implied ERP (FCFE)"))

    def test_header_row_must_exist(self):
        with pytest.raises(TrackBDataError, match="header row"):
            damodaran_erp.parse_histimpl(pd.DataFrame([["nothing"], ["here"]]))

    def test_monthly_table(self):
        out = damodaran_erp.parse_erp_monthly(_monthly_grid())
        assert list(out.index) == [
            pd.Timestamp("2008-09-01"),
            pd.Timestamp("2008-10-01"),
            pd.Timestamp("2026-10-01"),
        ]
        assert out.loc["2026-10-01", "erp_t12m"] == pytest.approx(0.037)
        assert out["available_from"].iloc[0] == pd.Timestamp("2008-09-08")

    def test_monthly_row_typed_as_text_is_kept(self):
        # The live file has one such row (September 2024); the table must not stop there.
        grid = _monthly_grid()
        grid.iloc[2] = ["1-Oct-08", "1,166", "3.83%", "4.51%", None, None]
        out = damodaran_erp.parse_erp_monthly(grid)
        assert len(out) == 3
        assert out.loc["2008-10-01", "erp_t12m"] == pytest.approx(0.0451)
        assert out.loc["2008-10-01", "sp500"] == pytest.approx(1166)

    def test_monthly_loader_reads_xlsx(self, tmp_path):
        buf = io.BytesIO()
        _monthly_grid().to_excel(buf, header=False, index=False, engine="openpyxl")
        cache, _ = _cache(tmp_path, {damodaran_erp.ERP_MONTHLY_URL: buf.getvalue()})
        out = damodaran_erp.load_erp_monthly(cache)
        assert len(out) == 3
        assert out["tbond"].iloc[-1] == pytest.approx(0.0529)


# --------------------------------------------------------------------------- #
# JKP
# --------------------------------------------------------------------------- #

ALL_CODES = sorted({lk.jkp for links in factor_map.ENGINE_TO_JKP.values() for lk in links})


def _jkp_long(codes=ALL_CODES, months=72, directions=None, seed=0):
    """Long JKP table; each factor's return is a constant plus noise."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("1960-01-31", periods=months, freq="ME")
    directions = directions or {}
    rows = []
    for k, code in enumerate(codes):
        for d in dates:
            rows.append(
                {
                    "location": "usa",
                    "name": code,
                    "freq": "monthly",
                    "weighting": "vw_cap",
                    "direction": directions.get(code, 1),
                    "n_stocks": 500,
                    "n_stocks_min": 10,
                    "date": d.strftime("%Y-%m-%d"),
                    "ret": 0.002 * (k % 3) + 0.01 * rng.standard_normal(),
                }
            )
    return pd.DataFrame(rows)


class TestJKP:
    def test_url_encodes_brackets(self):
        name = jkp.jkp_file_name()
        assert name == "[usa]_[all_factors]_[monthly]_[vw_cap]"
        assert jkp.jkp_url(name).endswith(
            "%5Busa%5D_%5Ball_factors%5D_%5Bmonthly%5D_%5Bvw_cap%5D.zip"
        )

    def test_bad_options_raise(self):
        with pytest.raises(ValueError):
            jkp.jkp_file_name(weighting="cap")

    def test_load_through_cache(self, tmp_path):
        name = jkp.jkp_file_name()
        body = _zip(name + ".csv", _jkp_long(["be_me", "ret_12_1"], months=3).to_csv(index=False))
        cache, _ = _cache(tmp_path, {jkp.jkp_url(name): body})
        long = jkp.load_jkp(cache=cache)
        assert set(long["name"]) == {"be_me", "ret_12_1"}
        wide = jkp.jkp_wide(long)
        assert wide.shape == (3, 2)
        assert wide.index[0] == pd.Timestamp("1960-01-31")

    def test_missing_column_raises(self):
        raw = _jkp_long(["be_me"], months=2).drop(columns="direction")
        with pytest.raises(TrackBDataError, match="direction"):
            jkp.parse_jkp_csv(raw)

    def test_duplicates_raise(self):
        raw = _jkp_long(["be_me"], months=2)
        with pytest.raises(TrackBDataError, match="duplicate"):
            jkp.parse_jkp_csv(pd.concat([raw, raw]))

    def test_directions(self):
        long = jkp.parse_jkp_csv(
            _jkp_long(["be_me", "at_gr1"], months=2, directions={"at_gr1": -1})
        )
        assert jkp.jkp_directions(long) == {"at_gr1": -1, "be_me": 1}
        long.loc[long.index[long["name"] == "be_me"][0], "direction"] = -1
        with pytest.raises(TrackBDataError, match="changes over time"):
            jkp.jkp_directions(long)


# --------------------------------------------------------------------------- #
# OSAP
# --------------------------------------------------------------------------- #

OSAP_CSV = """signalname,port,date,ret,signallag,Nlong,Nshort
AM,01,1951-07-31,7.66,0.68,67,0
AM,LS,1951-07-31,1.50,NA,67,60
AM,LS,1951-09-28,-0.50,NA,67,60
BM,LS,1951-07-31,2.00,NA,80,80
"""
SIGNAL_DOC = "Acronym,Sign,Cat.Signal\nAM,1,Predictor\nAccruals,-1,Predictor\nBroken,NA,Predictor\n"


class TestOSAP:
    def _resolver(self, calls):
        def resolve(release, name):
            calls.append((release, name))
            return f"https://drive/{release}/{name}"

        return resolve

    def test_portfolios_are_decimal_and_month_end(self, tmp_path):
        calls = []
        cache, _ = _cache(tmp_path, {"https://drive/202510/op": OSAP_CSV.encode()})
        ports = osap.load_osap_portfolios(cache=cache, resolver=self._resolver(calls))
        assert ports["port"].tolist()[:2] == ["01", "LS"]
        ls = osap.osap_long_short(ports)
        assert ls.loc["1951-07-31", "AM"] == pytest.approx(0.015)
        assert pd.Timestamp("1951-09-30") in ls.index
        assert calls == [(202510, "op")]

    def test_cached_file_needs_no_resolver(self, tmp_path):
        calls = []
        cache, _ = _cache(tmp_path, {"https://drive/202510/op": OSAP_CSV.encode()})
        osap.load_osap_portfolios(cache=cache, resolver=self._resolver(calls))
        osap.load_osap_portfolios(cache=cache, resolver=self._resolver(calls))
        assert len(calls) == 1

    def test_signal_signs_skip_missing(self, tmp_path):
        cache, _ = _cache(tmp_path, {"https://drive/202510/signal_doc": SIGNAL_DOC.encode()})
        signs = osap.load_osap_signal_signs(cache=cache, resolver=self._resolver([]))
        assert signs == {"AM": 1, "Accruals": -1}

    def test_missing_columns_raise(self):
        with pytest.raises(TrackBDataError, match="ret"):
            osap.parse_osap_portfolios(pd.DataFrame({"signalname": [], "port": [], "date": []}))

    def test_no_long_short_rows_raise(self):
        ports = osap.parse_osap_portfolios(pd.read_csv(io.StringIO(OSAP_CSV), dtype={"port": str}))
        with pytest.raises(TrackBDataError, match="LS"):
            osap.osap_long_short(ports[ports["port"] != "LS"])


# --------------------------------------------------------------------------- #
# Factor map and candidate E
# --------------------------------------------------------------------------- #


class TestFactorMap:
    def test_map_covers_backtestable_factors_once(self):
        mapped = set(factor_map.ENGINE_TO_JKP)
        assert not mapped & set(factor_map.UNMAPPED)
        assert {"intrinsic_value", "quality", "sentiment", "earnings_quality"} <= mapped
        for links in factor_map.ENGINE_TO_JKP.values():
            assert all(lk.engine_direction in (1, -1) for lk in links)
            assert len({lk.jkp for lk in links}) == len(links)

    def test_sign_is_engine_direction_times_jkp_direction(self):
        directions = dict.fromkeys(ALL_CODES, 1)
        directions.update({"debt_me": 1, "netdebt_me": -1, "oaccruals_at": -1})
        signs = factor_map.link_signs(directions)
        # Engine dislikes debt; the literature finds high debt-to-market earns more.
        assert signs["leverage_penalty"]["debt_me"] == -1
        assert signs["leverage_penalty"]["netdebt_me"] == 1
        assert signs["earnings_quality"]["oaccruals_at"] == 1

    def test_unknown_jkp_code_raises(self):
        with pytest.raises(TrackBDataError, match="lacks mapped"):
            factor_map.link_signs({"be_me": 1})

    def test_engine_returns_average_signed_components(self):
        long = jkp.parse_jkp_csv(_jkp_long(months=3))
        out = factor_map.engine_factor_returns(long)
        wide = jkp.jkp_wide(long)
        assert out.loc[wide.index[0], "fragility_penalty"] == pytest.approx(wide["ni_me"].iloc[0])
        expected = (
            wide["oaccruals_at"] * -1 + wide["taccruals_at"] * -1 + wide["oaccruals_ni"] * -1
        ) / 3
        assert out["earnings_quality"].tolist() == pytest.approx(expected.tolist())

    def test_month_with_a_missing_component_is_dropped(self):
        long = jkp.parse_jkp_csv(_jkp_long(months=3))
        long.loc[(long["name"] == "qmj") & (long["date"] == long["date"].min()), "ret"] = np.nan
        out = factor_map.engine_factor_returns(long)
        assert np.isnan(out["quality"].iloc[0])
        assert np.isfinite(out["intrinsic_value"].iloc[0])

    def test_theme_returns(self):
        themes = pd.DataFrame(
            [
                {"name": t, "date": "2000-01-31", "ret": 0.01, "n_factors": 3}
                for t in set(factor_map.ENGINE_TO_JKP_THEME.values())
            ]
        )
        out = factor_map.engine_theme_returns(jkp.parse_jkp_csv(themes, "all_themes"))
        assert set(out.columns) == set(factor_map.ENGINE_TO_JKP_THEME)
        with pytest.raises(TrackBDataError, match="themes"):
            factor_map.engine_theme_returns(jkp.parse_jkp_csv(themes.iloc[:1], "all_themes"))

    def test_window_stats_need_enough_months(self):
        idx = pd.date_range("1963-07-31", periods=120, freq="ME")
        rng = np.random.default_rng(3)
        rets = pd.DataFrame(
            {
                "a": 0.01 + 0.02 * rng.standard_normal(120),
                "b": [np.nan] * 80 + list(0.01 * rng.standard_normal(40)),
            },
            index=idx,
        )
        stats = factor_map.window_stats(rets)
        a = rets["a"]
        assert stats.loc["a", "sharpe"] == pytest.approx(a.mean() / a.std() * np.sqrt(12))
        assert np.isnan(stats.loc["b", "sharpe"])
        assert stats.loc["b", "n_months"] == 40

    def test_window_excludes_track_a_period(self):
        idx = pd.date_range("2005-01-31", periods=120, freq="ME")
        stats = factor_map.window_stats(
            pd.DataFrame({"a": np.arange(120.0)}, index=idx), min_months=1
        )
        assert stats.loc["a", "n_months"] == 60  # 2005-01 to 2009-12

    def test_target_keeps_unmapped_prior(self):
        prior = np.array([0.5, 0.3, 0.2])
        target = factor_map.track_b_target(np.array([1.0, 3.0, np.nan]), prior)
        assert target[2] == pytest.approx(0.2)
        assert target[:2] == pytest.approx([0.8 * 0.25, 0.8 * 0.75])
        assert factor_map.track_b_target(np.array([-1.0, np.nan, np.nan]), prior) is None

    def test_candidate_returns_prior_when_data_weight_is_zero(self):
        prior = np.array([0.5, 0.3, 0.2])
        # Identical IC columns: no spread across factors, so the empirical-Bayes weight is 0.
        ic = np.tile(np.linspace(-0.1, 0.1, 40)[:, None], (1, 3))
        ctx = CandidateContext(ic=ic, prior=prior, haircut=np.ones(3), nw_lags=1)
        w = factor_map.make_track_b_candidate(np.array([2.0, 0.1, np.nan]))(ctx)
        assert w == pytest.approx(prior)

    def test_candidate_rejects_misaligned_sharpes(self):
        ctx = CandidateContext(
            ic=np.zeros((10, 3)), prior=np.ones(3) / 3, haircut=np.ones(3), nw_lags=1
        )
        with pytest.raises(ValueError, match="align"):
            factor_map.make_track_b_candidate(np.array([1.0, 2.0]))(ctx)

    def test_sharpe_vector_order(self):
        stats = pd.DataFrame({"sharpe": {"quality": 0.5, "sentiment": 0.8}})
        vec = factor_map.sharpe_vector(stats, ["sentiment", "crowding", "quality"])
        assert vec[0] == 0.8 and np.isnan(vec[1]) and vec[2] == 0.5

    def test_candidate_e_runs_in_the_horse_race(self):
        rng = np.random.default_rng(0)
        names = ["signal", "noise_a", "noise_b"]
        dates = list(pd.date_range("2010-01-31", periods=72, freq="ME"))
        scores, rets = {}, {}
        for d in dates:
            x = rng.standard_normal((40, 3))
            scores[d], rets[d] = x, 0.4 * x[:, 0] + rng.standard_normal(40)
        prior = {"signal": 0.1, "noise_a": 0.5, "noise_b": 0.4}
        cands = {
            **ws.CANDIDATES,
            factor_map.CANDIDATE_E: factor_map.make_track_b_candidate(np.array([1.0, 0.1, 0.1])),
        }

        res = run_horse_race(dates, scores, rets, names, prior, candidates=cands, spa_n_boot=200)

        assert res.status == "success"
        w = res.full_sample_weights[factor_map.CANDIDATE_E]
        assert sum(w) == pytest.approx(1.0)
        assert w[0] > prior["signal"]
