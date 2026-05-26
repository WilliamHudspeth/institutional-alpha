# Contributing

Thanks for your interest. This project is in early scaffold stage — most factor implementations are stubs that return neutral scores with reduced confidence when data is missing. There's a lot to do, and contributions of any size are welcome.

## Good first issues

The highest-value contributions right now:

1. **Implement a single factor's stub** — Pick a factor in `src/iam/factors/` and replace the placeholder calculations with real ones. Each file documents what it's supposed to do.
2. **Add a data provider adapter** — Wire `Security` to a real data source (yfinance, FMP, Alpha Vantage, IB, etc.) in a new module under `src/iam/data/providers/`.
3. **Write tests** — Especially edge cases (missing data, extreme values) for any factor.
4. **Calibrate default weights** — Right now defaults come from the original framework writeup. Backtest-derived weights would be more defensible.

## Stretch goals

- **Bayesian updating engine** — Currently on the roadmap. Each earnings release should update a posterior over scenarios.
- **Cross-sectional ranking helpers** — Score a universe and rank/Z-score across it.
- **Backtest harness** — Run the scoring framework over historical data and measure information coefficient by factor.

## How to add a new factor

1. Subclass `Factor` (or `PenaltyFactor`) from `iam.factors.base`.
2. Set `name`.
3. Implement `compute(security) -> FactorContribution`. Return `value` in `[-1, 1]` (or `[0, 1]` for penalties), set `confidence` < 1.0 when data is missing, and populate `components` for auditability.
4. Register it in `src/iam/factors/__init__.py`.
5. Add it to the default factor list in `src/iam/engine/composite.py` if it's a core factor, and add a default weight to `DEFAULT_WEIGHTS`.
6. Document it in `docs/factors.md`.
7. Add a unit test in `tests/`.

## Style

- No heavy dependencies in the core package. `numpy` and `pandas` are OK in data adapters and the backtest harness, but the factor layer should stay light.
- Docstrings on every public class and function.
- Type hints everywhere.

## Running tests

```bash
pip install -e ".[dev]"
pytest
```

## Disclaimer

By contributing you agree your contribution is released under the MIT license. This is research software — please don't contribute code that fetches data you don't have rights to, and don't use the framework as a substitute for licensed financial advice.
