# Backtest and Empirical Validation

## Status

**There is no valid empirical IC result yet.** `data/results/ic/ic_summary.txt` reports
`n_obs: 0`. The harness runs, but two problems stop it from measuring anything:

1. **Empty inputs.** The universe loader (`src/iam/backtest/universe.py`) builds each ticker
   without sector or fundamentals, and snapshots (`src/iam/backtest/snapshots.py`) freeze only
   price and debt. Composite scores come out as NaN and every date is skipped.
2. **Bias.** The universe file `data/universe/sp100.json` is frozen at 2024-12-31. Using it for
   earlier dates introduces look-ahead and survivorship bias. Price-only snapshots avoid
   look-ahead in prices but not in the universe.

The synthetic run from v0.3.5 (IC +0.033, IR 1.93) exercised the harness mechanics. It is not
evidence of a signal. Real IC series are noisier and typical information ratios are 0.3 to 0.5.
The stored calibration files are labelled accordingly: `calibrated_reliabilities.json` is marked
`data_source: synthetic` and `calibrated_reliabilities_empirical.json` is marked
`insufficient_data` because the measured IC was not finite. The reliability loader
(`src/iam/arbitration/reliability_loader.py`) refuses to use either as if it were empirical.

## What exists

| Component | Location |
|---|---|
| Pluggable data sources (yfinance, Stooq, SEC EDGAR, FMP, Tiingo, tiered router) | `src/iam/backtest/sources/` |
| Point-in-time snapshots (disk-cached) | `src/iam/backtest/snapshots.py` |
| Price block with forward returns (Polars, parquet) | `src/iam/backtest/prices.py`, `data_loader.py` |
| IC, hit rate, decile spread, sector-neutral IC, HAC standard errors | `src/iam/backtest/metrics.py`, `quantiles.py` |
| Bayesian-shrinkage reliability calibration | `src/iam/backtest/calibration.py` |
| IC runner and CLI | `src/iam/backtest/ic_runner.py`, `cli.py` |
| Research-integrity statistics (CPCV, PBO, SPA, deflated Sharpe, multiple testing) | `src/iam/backtest/cpcv.py`, `overfitting.py`, `spa.py`, `multiple_testing.py` |
| Run manifest (git SHA, file hashes, config) | `src/iam/backtest/manifest.py` |

## Approach: point-in-time data from SEC EDGAR

The historical-financials source is SEC EDGAR. It is free, official, and every fact carries a
filing date, so a snapshot as of date T can use only facts that were public by T.

What EDGAR provides:

- `companyfacts`: one JSON per filer with the core concepts (revenue, net income, operating cash
  flow, capex, tax, pretax income, debt, equity, interest expense, operating income, shares).
  Each fact has `filed`, `accn`, `form`, `fy`, `fp`, `start` and `end`. It has no dimensional
  facts, so no segments or geography.
- `submissions`: SIC code (for sector), former names and the filing list.
- The 10-K XBRL instance: carries `StatementGeographicalAxis` members, which is the source of the
  geographic revenue mix.

Known pitfall: ticker-to-CIK mappings change after reorganisations. CIK resolution must be
date-aware or overridable. `src/iam/data/edgar/cik.py` handles this.

### Phases

| Phase | Scope | Status |
|---|---|---|
| A | Point-in-time fundamentals layer: client with declared User-Agent, rate limit under 10 requests/s, on-disk cache, offline fixtures, CIK resolution, `fundamentals_as_of(cik, date)`, SIC to sector. Code in `src/iam/data/edgar/`. | Implemented |
| B | Geographic revenue mix from the latest 10-K (`src/iam/data/edgar/geography.py`). Feeds `Security.revenue_mix` for live tickers. | Implemented for live tickers |
| C | Backtest wiring: snapshots take point-in-time fundamentals and revenue mix from A and B; the universe loader stops inventing sector and shares; run the IC backtest and report `n_obs`, coverage per date and the result. | Not started |
| D | Survivorship: build a point-in-time "largest N by revenue" universe from EDGAR `frames`, including companies that later delisted. Price coverage of delisted tickers is the constraint (yfinance lacks most, Stooq covers some). Coverage is to be measured and reported. | Decision pending |

Rules for all phases: missing values are `None` with a reason, every EDGAR-derived value records
its provenance, and tests run without network access.

## Validation gates

A real run counts as valid only if it passes these gates.

| Gate | Criteria |
|---|---|
| Data integrity | At least 75 of 100 tickers have prices; the price file hash matches the manifest; no gaps in the price series; forward returns computed as `price[t+h] / price[t] - 1`; debt values plausible. |
| Statistical validity | Mean IC above 0.01; IC mean over IC standard deviation above 0.3; t-statistic above 1.5 using Newey-West errors for overlapping returns; rolling 12-month IC does not collapse to zero; hit rate above 50%. |
| Soundness | Prices frozen at the evaluation date; sector-neutral IC at least half the unadjusted IC; monthly turnover below 40%. Any remaining survivorship bias is stated in the result. |
| Out-of-sample | Training period and held-out period are labelled in the manifest, and the held-out period is not used for fitting. |

## Interpreting the result

| Mean IC | Reading | Action |
|---|---|---|
| 0.00 to 0.01 | No measurable signal | Publish the null result. Examine individual factors, longer horizons (252 days) and regime dependence. |
| 0.02 to 0.04 | Economically meaningful if it survives the gates | Write empirical reliabilities (`data_source: empirical`), then validate out of sample. |

## Next steps

1. Complete Phase C and re-run the IC backtest with real fundamentals.
2. Decide on Phase D and report price coverage for delisted names.
3. Measure IC at 21, 63, 126 and 252 days.
4. Run factor attribution one factor at a time and check pairwise correlation (above 0.80 means
   redundancy).
5. Replace the synthetic reliability file with an empirical one.

## References

- Grinold and Kahn, *Active Portfolio Management* (information coefficient).
- Newey and West (1987), heteroskedasticity- and autocorrelation-consistent covariance.
- Damodaran, *Investment Valuation*.
