# Roadmap

## Current status

Version **0.4.0-rc1**, a release candidate. The valuation engine, factor framework, thesis engine
and backtest harness are implemented and tested. The signal has **not** yet been validated
empirically: the IC backtest has produced no usable result (see
[backtest status](docs/research/backtest.md)).

| Area | State |
|---|---|
| Seven-stage valuation pipeline (reverse DCF, relative, intrinsic, triangulation, macro overlay, verdict) | Implemented |
| Cost of capital: consensus and bottom-up cost of equity, revenue-weighted ERP and marginal tax, terminal growth capped at Rf | Implemented, see [cost of capital](docs/methodology/cost-of-capital.md) |
| Ten factors and three penalties, with decomposable composite | Implemented |
| Damodaran-law consistency checks, business-reality engine, thesis drift detection | Implemented |
| Bayesian thesis engine | Implemented |
| Portfolio analytics, sizing and verdicts | Implemented |
| Backtest harness with pluggable sources and research-integrity statistics | Implemented, no valid result yet |
| Point-in-time SEC EDGAR fundamentals and 10-K geographic revenue mix | Implemented for live tickers |
| Tests | About 1,850 tests; CI enforces 85% line coverage |

Static checks (ruff, mypy, bandit) pass on the 0.4.0-rc1 code.

## Known limitations

- **ML lens is never fitted.** `src/iam/ml/ml_lens.py` does not call `AnomalyDetector.fit`, so the
  lens has no trained model.
- **No empirical IC result.** `data/results/ic/ic_summary.txt` shows `n_obs: 0`. The backtest
  suffers from look-ahead and survivorship bias because `data/universe/sp100.json` is frozen at
  2024-12-31, and snapshots do not yet carry fundamentals.
- **Backtest does not use the 10-K revenue mix.** Live tickers take `revenue_mix` from the latest
  10-K; backtest snapshots do not.
- **Revenue-mix coverage.** Members the country tables cannot resolve (for example "Other
  countries") stay in the mix and lower coverage. Without a 10-K mix the US ERP and tax rate apply.
- **Historical financials.** SEC EDGAR is the chosen point-in-time source (see
  [data source options](docs/research/data-source-options.md)); wiring it into the backtest is
  the main 0.4.0 task.
- **Text front-ends not consolidated.** Several terminal interfaces coexist in `src/iam/ui/`.
- **Data scope.** Yahoo Finance is the default live source and has gaps and delays. Coverage is
  US-listed equities. There is no real-time data.
- **Model limits.** DCF values are sensitive to terminal growth and discount rate. Relative
  valuation depends on the peer set. Regime definitions are rule-based.

## Next milestones

### 0.4.0: empirical IC on point-in-time data

- Wire the backtest to point-in-time EDGAR fundamentals, sector and revenue mix; remove invented
  sector and share counts from the universe loader.
- Decide how to build a survivorship-free universe and measure price coverage for delisted names.
- Run the IC backtest and report `n_obs`, coverage per date, IC, information ratio and
  Newey-West t-statistic against the validation gates.
- Replace the synthetic reliability weights with empirical ones, or publish the null result.

### 0.5.0: reasoning engines

- Extend the intrinsic engine with operating leverage and ROIC decay curves at segment level.
- Multi-scenario macro stress with transmission to intrinsic value.
- Synthesis of market, intrinsic, peer and business views into a disagreement map.
- Confidence intervals and "what must stay true" alerts from thesis drift.
- Multi-horizon IC (21, 63, 126 and 252 days) and factor attribution, including a pairwise
  correlation check for redundant factors.

## Later

- Additional data adapters (FMP, Tiingo, live Damodaran datasets) behind the `DataSource` contract.
- Multi-currency and international coverage beyond the current country-risk handling.
- Machine-learning overlay for signal reliability, once the ML lens is fitted and validated.
- Regime-dependent calibration of factor reliability.
- Out-of-sample IC tracking with drift alerts.
- Portfolio optimisation beyond the current sizing methods.

## Principles

1. Factors are orthogonal and every score is decomposable.
2. Data providers are pluggable.
3. No fabricated numbers: missing data is `None` or an explicit "insufficient data" state.
4. Dependencies stay minimal.

See [architecture](docs/architecture.md) for details.

## Related

- [Changelog](CHANGELOG.md)
- [Contributing](CONTRIBUTING.md)
- [Releasing](docs/development/releasing.md)
