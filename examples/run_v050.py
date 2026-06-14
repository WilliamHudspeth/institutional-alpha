import sys
from pathlib import Path

import pandas as pd

# Fix path to import iam
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from iam.api import Security
from iam.backtest.config import BacktestConfig
from iam.backtest.ic_runner import ICBacktest, ICBacktestConfig
from iam.backtest.prices import load_price_block
from iam.backtest.universe import load_universe_tickers


def main():
    print("Starting v0.5.0 IC Backtest...")

    config = BacktestConfig(
        start="2018-01-31",
        end="2024-12-31",
        horizon_days=21,
        horizons_days=[21, 63, 126, 252],
    )

    print("Loading price block...")
    price_pl = load_price_block(config)
    try:
        price_df = price_pl.to_pandas()
    except Exception:
        price_df = pd.DataFrame(price_pl.to_dicts())

    tickers = load_universe_tickers(config.universe_file)
    securities = [Security(ticker=t, sector="", industry="", country_iso="US") for t in tickers]

    print(f"Loaded {len(securities)} securities")

    ic_config = ICBacktestConfig(
        horizons=[1, 3, 6, 12],
        min_stocks_per_date=30,
        rebalance_freq="ME",
        start_date="2018-01-31",
        end_date="2024-12-31",
        n_jobs_cpu=4,
    )

    runner = ICBacktest(securities=securities, price_block=price_df, config=ic_config)

    print("Running backtest...")
    runner.run()

    print("Generating report...")
    runner.generate_report()

    stats = runner.compute_statistics()
    factor_stats = runner.compute_factor_statistics()

    with open(
        "C:/Users/wshb/.gemini/antigravity/brain/ea6a265f-ffd3-4097-a02a-f8d8b1b0ed3d/ic_backtest_report.md",
        "w",
    ) as f:
        f.write("# Empirical IC Backtest Report (v0.5.0)\n\n")
        f.write("## Overview\n")
        f.write("- **Universe**: S&P 100\n")
        f.write("- **Period**: 2018-01 to 2024-12\n")
        f.write("- **Frequency**: Monthly\n")

        f.write("\n## Composite Statistics by Horizon\n")
        for h, s in stats.items():
            f.write(f"### {h} Month(s)\n")
            f.write(f"- Mean IC: {s.get('mean_ic'):.4f}\n")
            f.write(f"- ICIR: {s.get('icir'):.4f}\n")
            f.write(f"- t-stat: {s.get('t_stat'):.4f}\n")
            f.write(f"- p-value: {s.get('p_value'):.6f}\n")
            f.write(f"- Observations: {s.get('n_obs')}\n")

        f.write("\n## 1-Month Factor Statistics\n")
        if not factor_stats.empty:
            f.write(factor_stats.to_markdown())
        else:
            f.write("No factor stats available.")

    print("Done!")


if __name__ == "__main__":
    main()
