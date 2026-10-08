# Getting Started

## Requirements

Python 3.10 or newer.

## Install

```bash
git clone https://github.com/WilliamHudspeth/institutional-alpha
cd institutional-alpha
pip install -e ".[dev,test,data]"
```

Optional extras are declared in `pyproject.toml`:

| Extra | Adds |
|---|---|
| `data` | pandas, numpy, scipy |
| `gui` | Streamlit and Plotly for the browser GUI |
| `live` | Live-data providers |
| `backtest` | Polars, diskcache, statsmodels, typer and the other backtest dependencies |
| `test`, `dev` | pytest tooling and build tools |

## Run it

| Interface | Command |
|---|---|
| Browser GUI (Streamlit) | `python launch_gui.py` |
| Full-screen terminal UI | `python launch_tui.py` |
| Terminal UI with demo data (visible banner) | `python launch_tui.py --demo` |
| Interactive launcher | `institutional-alpha` |
| Text menu | `iam-menu` |
| Single ticker from the command line | `python scripts/analyze.py <TICKER>` |

Live tickers need network access. Demo data is available only behind `--demo`.

## Run the pipeline from Python

```python
from iam import Fundamentals, MarketData, Security, ValuationPipeline

security = Security(
    ticker="HYPCO",
    name="Hypothetical Co.",
    sector="Software",
    fundamentals=Fundamentals(
        revenue_ttm=10_000.0,
        fcf_ttm=2_800.0,
        shares_outstanding=1_000.0,
        net_income_ttm=2_400.0,
        ebitda_ttm=3_500.0,
    ),
    market=MarketData(price=180.0, market_cap=180_000.0, pe_ttm=75.0),
    qualitative={
        "forecast_growth": 0.18,
        "forecast_discount_rate": 0.10,
        "forecast_terminal_growth": 0.025,
    },
)

report = ValuationPipeline().run(security)
print(report.explain())
```

Fields left unset stay `None`. Stages that need them report insufficient data instead of
substituting a value. See `examples/pipeline_one.py` for a complete input and
`examples/live_pipeline.py` for live data through the Yahoo adapter.

## Examples

| Script | Shows |
|---|---|
| `examples/pipeline_one.py` | The seven-stage pipeline on a hand-built security |
| `examples/live_pipeline.py` | The pipeline on live data |
| `examples/score_one.py` | Composite factor scoring |
| `examples/thesis_example.py`, `examples/bayesian_thesis_example.py` | Scenario thesis and Bayesian updating |
| `examples/portfolio_example.py`, `examples/portfolio_integration_example.py` | Portfolio analytics |
| `examples/complete_workflow_example.py` | Security to portfolio workflow |
| `examples/modern_terminal_example.py`, `examples/sparklines_example.py` | Terminal panels and ANSI charts |

Run any of them from the repository root, for example `python examples/pipeline_one.py`.

## Configuration

Copy `config.example.yml` to `~/.iam/settings.yml` or `./config.yml`, or point `IAM_CONFIG` at a
file. It sets the watchlist, theme, market-data refresh intervals and factor weights. The
settings panel in the terminal UI reads and writes the same file. Data-provider keys are set
separately; see [data sources](data-sources.md).

## Verify the install

```bash
python -m pytest -q -o addopts="" -p no:cacheprovider --benchmark-disable --ignore=tests/performance
```

Tests do not use the network. To run the pipeline offline in your own scripts, patch
`iam.data.markets.fetch_live_quote` to return `None` and
`iam.data.providers.yfinance_adapter.build_regression_inputs` to raise.

## Where to go next

- [Architecture](architecture.md): modules, contracts and design principles.
- [Valuation pipeline](methodology/valuation-pipeline.md) and
  [cost of capital](methodology/cost-of-capital.md): what the model does.
- [Integration guide](guides/integration.md) and [portfolio](methodology/portfolio.md): using the
  outputs in a workflow.
