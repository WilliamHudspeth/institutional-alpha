"""scripts/build_price_parquet.py runs end to end offline (no network, temp directory).

Regression: the evaluation-window filter compared the polars Date column with the
``--end`` string, which polars >= 1.x rejects ("cannot compare 'date/datetime/time'
to a string value"), so every build crashed after downloading all prices.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib

import pandas as pd
import polars as pl
from typer.testing import CliRunner

SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "build_price_parquet.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("build_price_parquet", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeChain:
    """Stands in for the tiered source: a fixed, known price path per ticker."""

    last_used = "fake"

    def download_history(self, ticker: str, start: str, end: str) -> pd.DataFrame:
        dates = pd.bdate_range("2024-12-23", "2025-01-10")
        return pd.DataFrame({"Date": dates, "Close": [100.0 + i for i in range(len(dates))]})


def test_build_prices_filters_the_evaluation_window(tmp_path, monkeypatch):
    script = _load_script()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(script, "build_tiered_source", lambda: _FakeChain())
    monkeypatch.setattr(script, "load_universe_tickers", lambda path: ["AAA"])

    result = CliRunner().invoke(
        script.app, ["--start", "2024-12-23", "--end", "2024-12-31", "--horizon", "2"]
    )
    assert result.exit_code == 0, result.output + repr(result.exception)

    df = pl.read_parquet(tmp_path / "data" / "prices" / "sp100.parquet")
    dates = df["date"].to_list()
    # 2024-12-23 .. 2024-12-31 business days; later dates only feed forward returns.
    assert [d.isoformat() for d in dates] == [
        "2024-12-23",
        "2024-12-24",
        "2024-12-25",
        "2024-12-26",
        "2024-12-27",
        "2024-12-30",
        "2024-12-31",
    ]
    # Close on 2024-12-23 is 100, two business days later 102: 102/100 - 1.
    assert df["fwd_ret_2d"][0] == 102.0 / 100.0 - 1.0
    manifest = json.loads((tmp_path / "data" / "prices" / "manifest.json").read_text())
    assert manifest["data"]["date_range"] == ["2024-12-23", "2024-12-31"]
