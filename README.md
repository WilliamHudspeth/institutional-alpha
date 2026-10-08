# Institutional Alpha

A Python research engine for equity valuation and multi-factor scoring, built on Aswath Damodaran's methods.

[![CI](https://github.com/WilliamHudspeth/institutional-alpha/actions/workflows/ci.yml/badge.svg)](https://github.com/WilliamHudspeth/institutional-alpha/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/WilliamHudspeth/institutional-alpha/branch/main/graph/badge.svg)](https://codecov.io/gh/WilliamHudspeth/institutional-alpha)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
[![License: research use](https://img.shields.io/badge/license-research%20use-lightgrey)](LICENSE)

## Summary

Institutional Alpha splits a stock's price into what the market implies and what the fundamentals support.
A reverse DCF recovers the growth the current price requires. A bottom-up FCFE DCF, relative valuation and
sum-of-the-parts give independent fair-value estimates. The engine then tests these against one another and
against Damodaran's consistency rules, and reports where they disagree and which assumption explains the gap.
A 13-factor composite score sits alongside the valuation work.

## Features

- Reverse DCF (Stage 1) using a consensus cost of equity: Rf + regression beta x US equity risk premium.
- FCFE intrinsic DCF using a bottom-up cost of equity: Damodaran industry beta relevered at the current D/E.
- Revenue-weighted country ERP and marginal tax rate from Damodaran reference data (April 2026 and January 2026 vintages).
- Relative valuation, sum-of-the-parts (SOTP), and triangulation across methods.
- Damodaran-law consistency checks on the assumptions the intrinsic stage used.
- Seven-stage pipeline that ends in a verdict with a confidence band.
- 13-factor composite: 10 additive factors and 3 penalties (fragility, leverage, execution risk).
- Bayesian thesis tracking with scenario probabilities and drift detection.
- Portfolio analytics, position sizing and macro-regime detection.
- Backtest and information-coefficient (IC) harness with pluggable sources: yfinance, Stooq, SEC EDGAR, FMP.
- Streamlit GUI and an ANSI terminal UI.

## Project status

Version 0.4.0-rc1. This is research software, not a finished product. The pipeline, factors and
tests are implemented (CI gates on 85% coverage), but the signal has not been validated empirically.
Known limitations, from [ROADMAP.md](ROADMAP.md#known-limitations):

- The ML lens is never fitted.
- There is no valid IC backtest result yet (`n_obs: 0`). The frozen S&P 100 universe introduces
  survivorship and look-ahead bias.
- Several terminal front-ends coexist and are not yet consolidated.

Outputs are estimates, not investment advice. See [Terms of Service](docs/legal/TERMS_OF_SERVICE.md).

## Installation

Requires Python 3.10 or newer.

```bash
git clone https://github.com/WilliamHudspeth/institutional-alpha.git
cd institutional-alpha
pip install -e ".[data]"
```

Optional extras: `gui` (Streamlit, Plotly), `live` (yfinance), `backtest` (polars, statsmodels and related).
The development setup is described in [CONTRIBUTING.md](CONTRIBUTING.md).

## Quick start

Graphical interface (install the `gui` extra first; the launcher also tries to pip-install Streamlit if it is missing):

```bash
python launch_gui.py
```

Terminal interface with built-in demo data (displays a demo banner):

```bash
python launch_tui.py --demo
```

Python API. This is `examples/pipeline_one.py` in condensed form; the full example supplies a
24-month P/E history and peer FCF yields. Without network access the live macro lookups fail and
the run falls back with warnings.

```python
from iam import Fundamentals, MarketData, Security, ValuationPipeline

sec = Security(
    ticker="HYPCO",
    name="Hypothetical Co.",
    sector="Software",
    fundamentals=Fundamentals(
        revenue_ttm=10_000.0,
        revenue_history=[10_000, 8_500, 7_200, 6_100, 5_200],  # most recent first
        fcf_ttm=2_800.0,
        shares_outstanding=1_000.0,
        net_income_ttm=2_400.0,
        ebitda_ttm=3_500.0,
    ),
    market=MarketData(price=180.0, market_cap=180_000.0, pe_ttm=75.0, ev_ebitda=50.7,
                      sector_ev_ebitda_median=22.0, fcf_yield=0.0156),
    qualitative={
        "forecast_growth": 0.18,
        "forecast_discount_rate": 0.10,
        "forecast_terminal_growth": 0.025,
    },
)

report = ValuationPipeline().run(sec)
print(report.explain())
```

More examples are in [examples/](examples/); `examples/score_one.py` runs the factor composite.

## How it works

Each stage challenges the one before it. Disagreement between stages is reported, not averaged away.

1. Reverse DCF: the FCFE growth rate implied by the current price.
2. Relative: whether peers and the stock's own history support those expectations.
3. Intrinsic: FCFE DCF and SOTP built bottom-up, independent of price.
4. Triangulation: whether the three results cluster or diverge.
5. Macro outlier: which conclusions move materially under macro stress.
6. Macro re-overlay: re-runs only the names whose verdict changes under that stress.
7. Verdict: buy, hold or sell, with a confidence band and peer-relative ranking.

Stage 1 discounts at the consensus cost of equity (Rf + regression beta x US ERP). The intrinsic stage
and the reference WACC use a bottom-up cost of equity: Rf + Damodaran industry beta relevered at the
current D/E, times a revenue-weighted ERP, with marginal tax weighted by revenue mix. Terminal growth is
capped at the risk-free rate in every DCF engine. See [cost of capital](docs/methodology/cost-of-capital.md).

## Documentation

| Topic | Document |
| --- | --- |
| Install and run | [Getting started](docs/getting-started.md) |
| Modules and design principles | [Architecture](docs/architecture.md) |
| Providers, keys, reference data | [Data sources](docs/data-sources.md) |
| Valuation stages | [Valuation pipeline](docs/methodology/valuation-pipeline.md) |
| Rf, Ke, ERP, tax | [Cost of capital](docs/methodology/cost-of-capital.md) |
| Factors and weights | [Factors](docs/methodology/factors.md) |
| Consistency checks | [Damodaran laws](docs/methodology/damodaran-laws.md) |
| Portfolio layer | [Portfolio](docs/methodology/portfolio.md) |
| Backtest status and plan | [Backtest](docs/research/backtest.md) |
| CI, releases, conventions | [Development docs](docs/development/ci-cd.md) |

The full index is [docs/README.md](docs/README.md).

## Repository layout

```
src/iam/
  pipeline/    orchestrator, verdict, arbitration, valuation battlefield
  valuation/   reverse DCF, FCFE DCF, relative, SOTP, triangulation, country ERP and tax
  factors/     the 13 scoring factors
  lenses/      alternative scoring lenses
  laws/        Damodaran consistency checks
  thesis/      Bayesian thesis engine and drift detection
  portfolio/   analytics, sizing, optimizer, verdicts
  backtest/    snapshots, IC runner, data sources
  data/        providers, Damodaran reference data, EDGAR
  ui/          Streamlit GUI and terminal interfaces
examples/      runnable scripts
tests/         test suite
docs/          documentation
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Release history is in [CHANGELOG.md](CHANGELOG.md).

## License

Distributed under the Institutional Alpha Research Platform License ([LICENSE](LICENSE)): use is
limited to research and educational purposes, and modification, redistribution and commercial use are
not permitted.

## Acknowledgements

The valuation methodology follows the published work and data of Aswath Damodaran (NYU Stern),
including his country risk premium, industry beta and tax-rate datasets.
