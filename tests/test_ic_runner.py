from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from iam.backtest.ic_runner import ICBacktest, ICBacktestConfig
from iam.data.security import Fundamentals, MarketData, Security
from iam.engine.composite import DEFAULT_WEIGHTS, ScoreResult
from iam.factors import FactorContribution


def _make_test_securities(n=20):
    return [
        Security(
            ticker=f"T{i:03d}",
            sector=f"Sector{i % 3}",
            fundamentals=Fundamentals(shares_outstanding=1e9),
            market=MarketData(price=100.0 + i, market_cap=1e11 + i * 1e9),
        )
        for i in range(n)
    ]


def _make_test_price_block(tickers, dates):
    rows = []
    for d_idx, date in enumerate(dates):
        for i, ticker in enumerate(tickers):
            rows.append(
                {
                    "date": date,
                    "ticker": ticker,
                    "close": 100.0 + i + d_idx * i * 0.1,
                    "fwd_ret": 0.01 * (i / len(tickers)),
                }
            )
    return pd.DataFrame(rows)


def _make_mock_score_result(ticker, as_of):
    rng = np.random.RandomState(hash(ticker) % 10000)
    breakdown = {}
    for name in DEFAULT_WEIGHTS.keys():
        breakdown[name] = FactorContribution(
            name=name, value=rng.uniform(-0.5, 0.5), confidence=1.0
        )
    # create positive correlation for one factor just to ensure IC is non-zero
    breakdown["quality"] = FactorContribution(
        name="quality", value=float(ticker[1:]), confidence=1.0
    )

    comp = sum(fc.effective() * DEFAULT_WEIGHTS.get(name, 0.1) for name, fc in breakdown.items())
    return ScoreResult(
        ticker=ticker, composite=comp, factor_breakdown=breakdown, weights=dict(DEFAULT_WEIGHTS)
    )


@patch("iam.backtest.ic_runner.ProcessPoolExecutor", new=ThreadPoolExecutor)
@patch("iam.backtest.ic_runner.build_snapshot")
@patch("iam.backtest.ic_runner.score")
def test_ic_runner(mock_score, mock_build_snapshot):
    dates = [
        "2020-01-31",
        "2020-02-28",
        "2020-03-31",
        "2020-04-30",
        "2020-05-31",
        "2020-06-30",
        "2020-07-31",
        "2020-08-31",
        "2020-09-30",
        "2020-10-31",
        "2020-11-30",
        "2020-12-31",
        "2021-01-31",
    ]
    securities = _make_test_securities(35)
    tickers = [s.ticker for s in securities]
    price_block = _make_test_price_block(tickers, dates)

    def mock_build(base, as_of, **kwargs):
        return base

    mock_build_snapshot.side_effect = mock_build

    def m_score(snapshot, **kwargs):
        return _make_mock_score_result(snapshot.ticker, as_of="dummy")

    mock_score.side_effect = m_score

    config = ICBacktestConfig(
        start_date="2020-01-31",
        end_date="2020-12-31",
        horizons=[1, 3],
        min_stocks_per_date=10,
    )

    runner = ICBacktest(securities, price_block, config)
    res = runner.run()

    assert 1 in res
    assert 3 in res

    df1 = res[1]
    assert len(df1) > 0
    assert "ic" in df1.columns
    assert "ic_weighted" in df1.columns
    assert "ic_quality" in df1.columns

    stats = runner.compute_statistics()
    assert 1 in stats
    assert "mean_ic" in stats[1]

    f_stats = runner.compute_factor_statistics()
    assert not f_stats.empty
    assert "quality" in f_stats.index
