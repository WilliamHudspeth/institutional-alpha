# Backtest Strategy for Calibrating Weights and Thresholds

This document sets out how to use the backtest to replace the hand-set constants in the engine
(factor weights, penalty weights, sub-component weights, reliabilities, verdict thresholds and
the arbitration blend) with values that are estimated, validated out of sample, and recorded with
their evidence. It builds on [backtest status](backtest.md), which describes the harness and the
validation gates, and on [data source options](data-source-options.md).

It is a plan. No empirical result exists yet; nothing here changes a default.

## Summary

1. **Do not fit weights freely.** With 60 to 120 monthly cross-sections and 13 factors, estimated
   weights are mostly noise. Run a small, pre-registered horse race between the current priors,
   equal weight, and two shrinkage estimators. Promote a challenger only if it beats the priors out
   of sample after purging, multiple-testing correction and a publication-decay haircut.
2. **Calibrate only what the data can see.** Five of the ten additive factors and two of the three
   penalties can be rebuilt point-in-time from SEC EDGAR and prices. The rest (crowding, reflexivity,
   most of sentiment) cannot be backtested from free data and keep their priors, or are shrunk
   toward zero, until a source exists.
3. **Evaluate each tool with the test that fits it.** Cross-sectional rank IC for factors;
   time-series tests for the macro regime factor, which is identical for every stock on a date;
   value-to-price convergence for the valuation engines; Brier score and reliability diagrams for
   BUY/HOLD/SELL verdicts and confidence bands.
4. **Lock a holdout.** Develop on 2010-2019, then evaluate once on 2020-2026. Record every
   specification tried in a trial ledger so the deflated Sharpe ratio counts trials honestly.
5. **Use free data only, in two tracks.** No free source has complete prices for delisted US
   stocks, so the stock-level backtest of the engine's own code (Track A) carries some
   survivorship bias. It is bounded, not ignored, and checked against free factor returns built by
   academics from CRSP, which include delisted stocks (Track B). Damodaran's archived annual
   datasets supply point-in-time industry inputs for the valuation engines. See Section 3.
6. **Fix the estimator defects first.** This change fixes four defects in the optimizer and the IC
   runner (listed below). The remaining ones are listed with the phase that resolves them.

## 1. Audit of the current calibration code

### Fixed in this change

| Defect | Location | Effect | Fix |
|---|---|---|---|
| Objective used Pearson correlation on raw returns, although the module and the reporting use Spearman rank IC | `backtest/weight_optimizer.py` (`_objective`, OOS evaluation, PBO matrix) | A few extreme returns decided the weights | Fit against per-date ranked returns, a smooth surrogate (the composite itself is not ranked, because that would make the objective piecewise constant); evaluate OOS and PBO with true rank IC, dropping missing names pairwise |
| Walk-forward did not purge overlapping labels | `WalkForwardOptimizer.run` | With h-month forward returns, the last h-1 training labels overlap the test period, so test outcomes leak into training | New `horizon_months` config; the last `horizon_months - 1` training dates are purged. Default 1 keeps the old behaviour |
| Bootstrap was IID over dates and unseeded | `BootstrapStability.run` | Ignored autocorrelation from overlapping returns, so weight stability looked better than it is; results not reproducible | Moving-block bootstrap (`block_length`) with `random_state` |
| Newey-West lag fixed at 3 for every horizon | `ICBacktest.compute_statistics` | Monthly IC on 12-month returns is MA(11). Three lags understate the standard error and inflate t-stats | Lags are `max(nw_lags, h - 1)` per horizon. When the IC series is too short for that window, the t-stat and p-value are reported as undefined (NaN) with a warning, not as p = 1.0 |

### Still open

| Defect | Location | Effect | Resolved in |
|---|---|---|---|
| The macro regime factor has the same value for every stock on a date | `factors/macro_regime.py` | Its cross-sectional IC is undefined, and its 5% weight shifts every composite equally. It changes no ranking, only the absolute level that verdict thresholds read | Phase 3 (time-series test) |
| Regime weight multipliers target a `momentum` key that is not a factor, and the adjusted weights are not renormalised | `engine/composite.py` (`_REGIME_WEIGHT_MAP`) | Half of each regime adjustment does nothing; the other half changes the composite's scale by regime | Phase 3 |
| DSR counts SLSQP function evaluations as trials | `WalkForwardOptimizer.run` | Function evaluations are not independent strategies. The deflation is arbitrary, not merely conservative | Superseded for weight selection: `backtest/weight_selection.py` takes the trial count from the ledger. `WalkForwardOptimizer` still uses evaluations and should not be used to select weights |
| PBO candidates are window-fitted weights scored on periods that include their own training data | `WalkForwardOptimizer.run` | PBO measures something closer to weight drift than selection overfitting | Superseded for weight selection: the horse race computes PBO over the candidate set on out-of-sample ICs only |
| Shrinkage toward the prior is fixed at 0.7 | `WeightOptimizerConfig.shrinkage_lambda` | Shrinkage should depend on how noisy the IC estimates are | Superseded for weight selection: candidates C and D use per-factor empirical-Bayes data weights (`empirical_bayes_data_weight`) |
| `effective()` multiplies a factor's value by its confidence | `factors/base.py` | Missing data pulls a factor toward zero, so its IC partly measures data coverage | Phase 1 (report IC on value and on effective value) |
| Sector-neutral IC needs more than 5 names per sector | `metrics.ic_sector_neutral` | In a 100-name universe several sectors drop out | Phase 1 (use a 300 to 500 name universe) |
| The reliability map `0.5 + 5 x IC` is arbitrary | `backtest/calibration.py` | Reliabilities are not tied to forecast accuracy | Phase 4 |

## 2. What can be calibrated

Each factor's inputs were traced to `Security` fields. The table shows whether a point-in-time
history can be built from free sources.

| Factor or penalty | Prior weight | Inputs | Point-in-time source | Backtestable |
|---|---|---|---|---|
| expectations_difficulty | 0.22 | Price, revenue, margins, ROIC (reverse DCF) | EDGAR + prices | Yes |
| intrinsic_value | 0.20 | FCF, market cap, FCF yield, DCF residual | EDGAR + prices | Yes; `forecast_growth` must be derived, not analyst-supplied |
| quality | 0.12 | Margin and ROIC history, debt, cash, dilution | EDGAR | Yes |
| relative_value | 0.10 | P/E, EV/EBITDA, EV/sales, peer medians | EDGAR + prices; peer medians computed from the universe at each date | Yes |
| sentiment | 0.08 | Revisions, surprises, news, 6-month momentum | Only momentum from prices | Partly (momentum only) |
| reflexivity | 0.08 | Analyst-supplied qualitative scores | None | No |
| reinvestment_runway | 0.07 | Incremental ROIC plus qualitative inputs | EDGAR for the quantitative part | Partly |
| macro_regime | 0.05 | Rates, curve, credit, PMI, dollar | FRED/ALFRED (with the caveats below) | Time series only |
| crowding | 0.04 | Short interest, ownership, options skew | FINRA short interest; 13F from 2013 Q2 | Partly, from 2013 |
| earnings_quality | 0.04 | Accruals, SBC, working capital | EDGAR (SBC mapping is a known gap) | Mostly |
| fragility_penalty | 0.30 | Valuation, history | EDGAR + prices | Yes |
| leverage_penalty | 0.20 | Debt, EBITDA, interest, current ratio | EDGAR | Yes |
| execution_risk_penalty | 0.15 | Mostly qualitative | None | No |

Factors that are not backtestable keep their prior weight but are reported as **uncalibrated**
next to the score. Phase 2 also tests a variant that sets them to zero: if removing them does not
hurt the out-of-sample IC of the measurable part, there is no evidence they add value.

## 3. Data plan

The plan uses free sources only. Paid survivorship-free price feeds (Sharadar, EODHD, Norgate)
were considered and set aside; if one is added later, it slots into Track A as a `PREMIUM` tier
in `backtest/sources/tiers.py` and the bias bounds below can be dropped.

### Two tracks

- **Track A: the engine's own factors, stock by stock.** Rebuild each backtestable factor from
  EDGAR and free prices and measure its rank IC. This is the only way to test the code as written,
  but free prices miss many delisted names, so its results carry survivorship bias.
- **Track B: published factor returns, survivorship-free.** Jensen, Kelly and Pedersen (JKP),
  Chen and Zimmermann (Open Source Asset Pricing) and Kenneth French publish long-short factor
  returns built from CRSP and Compustat, including delisted stocks and delisting returns. They do
  not test the engine's code, but they give an unbiased, decades-long estimate of how each
  factor family behaves. Track B sets the priors and the sanity checks for Track A.

A Track A result is trusted only where it agrees in sign with the matching Track B factor over the
same period. A disagreement is reported as a likely implementation or survivorship problem, not as
a discovery.

### Sources

| Need | Free source | Notes |
|---|---|---|
| Universe | EDGAR companyfacts (filed dates) or the SEC Financial Statement Data Sets: the top 500 filers by trailing revenue at each month-end, including filers that later delisted | Do **not** use the XBRL `frames` API: it returns the latest-filed value per period, so restatements leak backwards. XBRL coverage starts with 2009 filings, so begin in 2010 |
| Cross-check universe | `fja05680/sp500` historical S&P 500 membership (1996 onward) | Post-2019 updates are manual from Wikipedia; map tickers to CIK because tickers are reused |
| Delisting dates and reasons | EDGAR Form 25 and Form 15 filings by CIK; Alpha Vantage `LISTING_STATUS` (free key) as a cross-check | Tells Track A which universe names left and when, even when no price exists |
| Prices (Track A) | Stooq bulk US daily file (`stooq_source.py` exists), then yfinance | Neither is survivorship-free. Before any IC is computed, measure the share of each month's universe with a price, split by names that later delisted and names that survived |
| Delisting returns (Track A) | No free source. Use the last free price when one exists; otherwise bound the bias (below) | Shumway (1997) estimates about -30% for NYSE/AMEX performance delistings, and Shumway and Warther (1999) about -55% on Nasdaq; check both against the papers before use |
| Factor returns (Track B) | JKP Global Factor Data (`jkpfactors.com`): US, 153 factors and 13 themes, monthly, capped value weighted | Free download of factor returns; stock-level data needs WRDS and is not used |
| Factor returns (Track B) | Open Source Asset Pricing portfolio returns (`pip install openassetpricing`) | Firm-level signals are keyed by CRSP PERMNO, which cannot be mapped to tickers without CRSP, so use the portfolio files only |
| Market and controls | Kenneth French Data Library: market, SMB, HML, RMW, CMA, momentum, 49 industry portfolios | Survivorship-free market return for Rung 4; controls for Rung 6 |
| Fundamentals | Existing `fundamentals_as_of(cik, date)` in `src/iam/data/edgar/` | Use the filing date, not the period end. Add a lag of one trading day after `filed` |
| Macro | ALFRED vintages (`realtime_start`/`realtime_end`) for DFII10, T10Y2Y | FRED's ICE BofA HY OAS series (BAMLH0A0HYM2) only carries three years of history since April 2026. Use Moody's BAA10Y as a credit proxy. ISM PMI left FRED in 2016 and is licensed |
| Equity risk premium | Damodaran `histimpl.xls`: implied ERP, annual from 1960 and monthly from September 2008 | A free, forward-looking valuation signal for Rung 4 |
| Industry inputs | Damodaran archived annual datasets, 1999 onward, at `pc/archives/<name><YY>.xls` (for example `margin10.xls`, `wacc12.xls`, `vebitda15.xls`, `betas05.xls`, `fundgr10.xls`) | See "Damodaran vintages" below |

### Bounding survivorship bias in Track A

Run every Track A statistic three ways and report all three:

1. **Drop:** names without a price are excluded (the biased, optimistic case).
2. **Last price:** delisted names with a free price history keep it up to the last trade, with a
   delisting return of zero after it.
3. **Penalised:** names that delisted for performance reasons (per Form 25 or the listing-status
   reason) get the Shumway delisting return for the month they left, even with no price.

A factor is accepted only if its sign and significance hold in all three. The coverage gate in
Section 6 applies to case 1; if fewer than 75% of a month's names that later delisted have
prices, the result is labelled "survivorship-biased" wherever it is shown.

### Damodaran vintages

Damodaran updates most datasets once a year, in early January, with market data as of
31 December and accounting data from the trailing twelve months available then. His usage rules
state there are "no strings attached", and `src/iam/data/damodaran.py` already loads the current
files. For backtesting:

- A date T in calendar year Y uses the vintage for year Y (published early January Y). Treat it as
  available from 15 January Y; dates from 1 to 14 January use the year Y-1 vintage.
- Industry inputs (unlevered beta, cost of capital, operating margin, sales-to-capital,
  reinvestment rate, fundamental growth, EV/EBITDA, EV/sales, P/E) come from that vintage. This
  gives `intrinsic_value` a `forecast_growth` derived without analysts, and gives
  `relative_value` a second peer benchmark next to medians computed from the universe.
- Damodaran's industry groups are his own. Reuse the sector-to-industry mapping already in
  `find_industry_unlevered_beta`, and record unmapped names as missing rather than defaulting.
- File layouts change across years. The parser must locate columns by header text and fail
  loudly when a header is missing, rather than read by position.
- Cache each vintage under `data/reference/damodaran/<year>/` with its download date and SHA-256 in
  the manifest, so a run can be reproduced if a file is later revised.

## 4. Experimental design

- **Dates:** month-ends from 2010-01 to the latest month with a complete 12-month forward return.
- **Horizons:** 1, 3, 6 and 12 months. The 12-month horizon matters most for valuation factors
  (Frankel and Lee 1998 find value-to-price predicts returns over one to three years).
- **Split:** development period 2010-01 to 2019-12; holdout 2020-01 onward. The holdout is
  opened **once**, after the specification is frozen and recorded in the manifest. `manifest.py`
  already records git SHA and config; add the frozen weight vector and the trial-ledger hash.
- **Cross-validation inside the development period:** CPCV (`cpcv.py`) with 6 groups and 2 test
  groups. Purge at least h months before each test block and embargo h months after it. The
  current `CPCVOptimizer` defaults (15 days each) are too short for 3 to 12-month labels.
- **Unit of evidence:** the monthly IC series. With overlapping h-month labels, only about T/h
  observations are independent (about 8 per decade at h = 12). Report a non-overlapping
  subsample IC as a robustness check, and use a stationary bootstrap with block length at least h
  for confidence intervals (`spa.stationary_bootstrap`).
- **Preprocessing:** rank-normalise each factor within each date before combining. Report IC on
  `value` and on `effective()` separately, and coverage per factor per date.

## 5. Calibration ladder

Each rung is estimated only after the one below it is fixed, so later rungs cannot absorb
errors from earlier ones.

### Rung 1: factor signs and sub-components

For each factor and each sub-component (for example the four leverage-penalty weights 0.35, 0.30,
0.20 and 0.15), compute the rank IC term structure (`term_structure.py`).

- A component whose IC has the wrong sign with a Newey-West t below -2 over the development
  period is a candidate for removal, not for a negative weight. The economic rationale must be
  re-examined first.
- Sub-component weights stay at their priors unless the equal-weighted alternative is better out
  of sample. There is not enough data to estimate them individually.
- Check pairwise correlation of factor scores. Above 0.8 means redundancy: merge them or keep one.

### Rung 2: composite factor weights

A pre-registered set of four candidates (five if the Track B check below adds E), all non-negative
and summing to one:

| Candidate | Definition |
|---|---|
| A. Prior | `DEFAULT_WEIGHTS` as it is |
| B. Equal weight | 1/N over the backtestable factors whose development-period IC is positive |
| C. Shrunk ICIR | w proportional to (1 - λ) · max(ICIR, 0) + λ · prior, with λ set by empirical Bayes (below) |
| D. Shrunk IC covariance | w proportional to Σ_IC⁻¹ E[IC] with Ledoit-Wolf shrinkage of Σ_IC (`ledoit_wolf_shrinkage`), projected to the simplex, then shrunk to the prior with the same λ |

**Shrinkage strength.** Treat each factor's true IC as drawn around its prior with spread τ².
The sampling variance of a factor's mean IC is σ² = HAC variance / T. The weight on the data is
τ² / (τ² + σ²), with τ² estimated by method of moments across factors (a James-Stein estimator;
Efron and Morris 1975). This replaces the fixed `shrinkage_lambda = 0.7`. Cap the data weight at
0.7 so that no factor's weight is driven entirely by one sample.

**Track B prior check.** Map each backtestable factor to its nearest JKP factors (for example
intrinsic_value to "Intrinsic value-to-market" and "Free cash flow-to-price", quality to the
"Quality minus Junk" and profitability factors, earnings_quality to the accruals theme,
sentiment's momentum part to "Price momentum t-12 to t-1"). Over 1963 to 2009, before the
Track A sample starts, compute each mapped factor's Sharpe ratio and the correlations between
them. If the hand-set priors rank factors very differently from this evidence, add a fifth
candidate, **E. Track B weights**: weights proportional to the 1963-2009 Sharpe ratios of the
mapped factors, shrunk to the prior with the same λ. Because it is fitted on data that ends before
Track A begins, it adds one trial to the ledger, not a search.

**Haircut.** Before comparing with the prior, multiply in-sample ICs of factors taken from the
literature (value, quality, momentum, accruals) by 0.5. McLean and Pontiff (2016) find portfolio
returns are 26% lower out of sample and 58% lower after publication across 97 predictors.

**Expectation.** DeMiguel, Garlappi and Uppal (2009) show estimated mean-variance weights rarely
beat 1/N out of sample when samples are short. With about 120 months, the realistic gain is
removing factors with a persistently wrong sign and small tilts, not a new weight vector. A null
result (all candidates statistically tied) is a valid outcome and should be published as such.

**Implementation.** `run_horse_race` in `backtest/weight_selection.py` implements candidates
A to D, the haircut, the empirical-Bayes data weight (capped at 0.7) and the selection rule below.
Every candidate is refitted inside each CPCV training fold, with purge and embargo of h months,
and scored on the test fold. PBO and SPA are computed from the out-of-sample IC of each candidate
on each date. On synthetic panels it replaces a deliberately wrong prior in every seed tried and
never promotes a challenger when no factor carries signal. Candidate E plugs in through the
`candidates` argument once the Track B loaders exist.

**Selection rule.** Promote a challenger over A only if, in the development period, its CPCV
out-of-sample mean IC beats A on at least 70% of paths, PBO over the candidate set is below 0.5,
and SPA rejects "no candidate beats A" at 10%. Then confirm once on the holdout.

### Rung 3: penalties

Penalties subtract from the composite, so they change ranks only where they vary across stocks.
Test each penalty as an additional factor with a negative sign: estimate its marginal IC
conditional on the Rung 2 composite (regress forward-return ranks on composite rank and penalty
rank by Fama-MacBeth). Keep the prior weights unless the marginal coefficient is significant and
of the wrong sign. Leverage and fragility are testable; execution risk is not.

### Rung 4: macro regime

The regime factor has no cross-sectional variation, so it cannot be judged by IC.

- **As a level shift:** test whether the regime score predicts the forward excess return of the
  market, using the French market factor rather than the Track A universe so the test is
  survivorship-free. Damodaran's implied ERP is a second free predictor and a benchmark the regime
  score should beat (time-series regression with Hodrick or Newey-West errors and out-of-sample R² per
  Campbell and Thompson 2008). If it does not, set its additive weight to zero; it only distorts
  verdict thresholds.
- **As a weight modifier:** test one split only (for example stress versus normal credit) and
  compare factor ICs across states with a block-bootstrap difference test. Regime-specific weights
  are shrunk toward unconditional weights with λ at least 0.7. Most macro predictors fail out of
  sample (Welch and Goyal 2008), and 2010-2019 contains few regime changes.
- Fix the `momentum` key and renormalise the adjusted weights before running this test.

### Rung 5: reliabilities and lens weights

Replace `0.5 + 5 x IC` with a mapping estimated from data: regress each lens's realised forecast
error on its stated upside (or rank its upside against forward returns) and set reliability from
the measured rank IC with its posterior uncertainty (the existing Bayesian code in
`calibration.py`, with the HAC standard error from Section 4). Keep the existing rule that a
reliability needs at least 36 monthly observations, and keep reliability weighting off by default
until it improves out-of-sample IC, as `lenses/synthesis.py` already requires.

### Rung 6: valuation engines

For FCFE DCF, reverse DCF, relative valuation and SOTP, compute (V - P) / P at each date and test:

1. Rank IC of (V - P) / P against 12, 24 and 36-month forward returns.
2. Convergence: regress the change in log price on log(V / P). A coefficient between 0 and 1
   means the gap closes partially; its size gives the half-life of mispricing.
3. Fama-MacBeth of forward returns on log(V/P) with controls for book-to-market, size and momentum,
   to see whether the engine adds information beyond simple value.

Engine inputs at each date come from the Damodaran vintage for that year (Section 3), never the
current files. Also run each engine once with the current-year Damodaran inputs applied to every
date: the gap between the two runs measures how much look-ahead the live defaults would have
added.

The triangulator currently weights methods equally (`valuation/triangulator.py`). Use these
results to decide whether a method should be down-weighted, with the same horse race as Rung 2
(equal weight versus shrunk inverse-error weights).

### Rung 7: verdicts, confidence bands and the arbitration blend

- **Verdicts.** Define the outcome before looking: BUY is correct if the 12-month return beats the
  universe median, SELL if it trails. Score the ordered verdicts with the ranked probability score
  and a reliability diagram. Tune `buy_threshold` and the SELL threshold to maximise rank
  correlation between verdict and forward return in the development period, on a coarse grid of
  no more than 10 points (each grid point goes in the trial ledger).
- **Confidence bands.** HIGH, MEDIUM and LOW are set by triangulation confidence at 0.8 and 0.5
  (`pipeline/verdict.py`). A band is calibrated if verdict accuracy rises monotonically from LOW to
  HIGH. If it does not, the bands carry no information and the thresholds should be revisited.
- **Arbitration blend.** The pipeline weight steps through 0.30, 0.40 and 0.60 by confidence
  (`pipeline/arbitration.py`). Test the three-step rule against a constant 0.5 blend and against
  a continuous rule. Keep the step rule only if it wins out of sample.
- Bootstrap all of these by month, because cross-sectional correlation inflates the apparent
  sample size.

## 6. Acceptance gates

These extend the gates in [backtest](backtest.md#validation-gates).

| Gate | Criterion |
|---|---|
| Coverage | At least 75% of universe names have prices and the core EDGAR fields at each date; coverage per date is published, separately for names that later delisted |
| Survivorship | Sign and significance hold in the drop, last-price and penalised cases (Section 3), and agree in sign with the matching Track B factor |
| Significance | Newey-West t with at least h-1 lags above 2.0 for a factor with a prior economic rationale, above 3.0 for anything selected by search (Harvey, Liu and Zhu 2016) |
| Multiple testing | Holm or BH across factors with the effective number of tests (`multiple_testing.py`) |
| Overfitting | PBO below 0.5 across the candidate set; DSR above 0.95 using the trial count from the ledger, reported at nominal and clustered trial counts |
| Robustness | Sign holds in the non-overlapping subsample and in both halves of the development period; sector-neutral IC at least half of raw IC |
| Holdout | Holdout mean IC is positive and within the development-period 90% bootstrap interval |

## 7. Trial ledger

Every specification evaluated (each candidate weight vector, threshold grid point, factor
removal, horizon and universe variant) is appended to a ledger file with timestamp, git SHA,
configuration hash and development-period result. The ledger feeds the trial count for the DSR
and the candidate matrix for PBO. Hand edits to `DEFAULT_WEIGHTS` count as trials. Without the
ledger, no reported significance can be trusted.

`TrialLedger` in `backtest/weight_selection.py` implements this as an append-only JSONL file.
`n_trials()` counts distinct configuration hashes, so re-running an identical specification is
not a new trial, and `file_hash()` gives the hash to record in the run manifest.

## 8. Phases

| Phase | Scope | Depends on |
|---|---|---|
| 0 | Estimator fixes listed in Section 1 (this change) | None |
| 1a | Track B loaders: JKP US factor returns, OSAP portfolios, French factors, Damodaran `histimpl.xls`; map engine factors to JKP factors | None |
| 1b | Damodaran vintage loader (1999 onward, header-based parsing, cached with hashes) | None |
| 1c | Universe from EDGAR, delisting dates from Form 25/15, free prices (Stooq, yfinance), PIT snapshots carrying EDGAR fundamentals (Phase C/D in [backtest](backtest.md)); coverage report split by later-delisted versus surviving names | None |
| 2 | Rung 1 and Rung 2: factor term structures, candidate horse race including the Track B candidate, empirical-Bayes shrinkage, trial ledger, PBO over candidates, DSR from the ledger, three survivorship cases. The statistical machinery (candidates A to D, shrinkage, ledger, PBO, SPA, DSR, selection rule) is implemented in `backtest/weight_selection.py`; running it needs the Phase 1 data | Phases 1a and 1c |
| 3 | Rungs 3 and 4: penalties and macro regime; fix the regime map | Phase 2 |
| 4 | Rungs 5 to 7: reliabilities, valuation-engine tests, verdict and band calibration | Phases 1b and 2 |
| 5 | Open the holdout once; write `calibrated_reliabilities_empirical.json` and any new weights with `data_source: empirical`, or publish the null result | Phases 2 to 4 |
| Ongoing | Live out-of-sample IC tracking with drift alerts against the frozen weights | Phase 5 |

## References

Figures marked (v) were checked against the published abstract for this document.

- Bailey, D., Borwein, J., López de Prado, M. and Zhu, Q. (2017). The probability of backtest
  overfitting. *Journal of Computational Finance*.
- Bailey, D. and López de Prado, M. (2014). The deflated Sharpe ratio. *Journal of Portfolio
  Management*.
- Britten-Jones, M., Neuberger, A. and Nolte, I. (2011). Improved inference in regression with
  overlapping observations. *Journal of Business Finance and Accounting* 38, 657-683.
- Campbell, J. and Thompson, S. (2008). Predicting excess stock returns out of sample. *Review of
  Financial Studies*.
- Chen, A. and Zimmermann, T. (2022). Open source cross-sectional asset pricing. *Critical Finance
  Review* 27(2), 207-264. Data: openassetpricing.com (October 2025 release, v2.0.0).
- Damodaran, A. Data archive, pages.stern.nyu.edu/~adamodar. Annual update, latest 9 January 2026;
  sources Bloomberg, Morningstar, Capital IQ and Compustat (v).
- DeMiguel, V., Garlappi, L. and Uppal, R. (2009). Optimal versus naive diversification. *Review of
  Financial Studies*.
- Efron, B. and Morris, C. (1975). Data analysis using Stein's estimator and its generalizations.
  *Journal of the American Statistical Association*.
- Frankel, R. and Lee, C. (1998). Accounting valuation, market expectation, and cross-sectional
  stock returns. *Journal of Accounting and Economics* 25, 283-319.
- Grinold, R. and Kahn, R. (2000). *Active Portfolio Management*.
- Hansen, P. (2005). A test for superior predictive ability. *Journal of Business and Economic
  Statistics*.
- Harvey, C., Liu, Y. and Zhu, H. (2016). ... and the cross-section of expected returns. *Review of
  Financial Studies* 29(1), 5-68. A new factor needs t above 3.0 (v).
- Hou, K., Xue, C. and Zhang, L. (2020). Replicating anomalies. *Review of Financial Studies*
  33(5), 2019-2133. 65% of 452 anomalies fail |t| > 1.96; 82% fail t > 2.78 (v).
- Jensen, T., Kelly, B. and Pedersen, L. (2023). Is there a replication crisis in finance?
  *Journal of Finance* 78(5), 2465-2518.
- Ledoit, O. and Wolf, M. (2004). Honey, I shrunk the sample covariance matrix. *Journal of
  Portfolio Management*.
- López de Prado, M. (2018). *Advances in Financial Machine Learning*. Wiley.
- McLean, R. D. and Pontiff, J. (2016). Does academic research destroy stock return
  predictability? *Journal of Finance* 71(1), 5-32. Returns 26% lower out of sample, 58% lower
  post-publication, across 97 predictors (v).
- Newey, W. and West, K. (1987). A simple, positive semi-definite, heteroskedasticity and
  autocorrelation consistent covariance matrix. *Econometrica*.
- Shumway, T. (1997). The delisting bias in CRSP data. *Journal of Finance*.
- Shumway, T. and Warther, V. (1999). The delisting bias in CRSP's Nasdaq data and its
  implications for the size effect. *Journal of Finance*.
- Welch, I. and Goyal, A. (2008). A comprehensive look at the empirical performance of equity
  premium prediction. *Review of Financial Studies*.
- White, H. (2000). A reality check for data snooping. *Econometrica*.
- FRED series note for BAMLH0A0HYM2: limited to three years of observations from April 2026 (v).
