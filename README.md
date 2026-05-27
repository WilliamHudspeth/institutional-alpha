# Institutional Alpha Model (IAM)

> A multi-factor equity scoring framework that prices what elite funds actually price.

Most public valuation models stop at DCF or relative multiples. Institutional discretionary and systematic funds implicitly price a much wider surface: **expectations difficulty, quality, reflexivity, crowding, regime fit, fragility, and capital allocation quality.** This repo is an open-source attempt to encode that surface as an orthogonal, weighted, auditable factor model — written in plain Python so it's easy to read, fork, and extend.

## Status

**v0.4.0-rc1** — release candidate. The factor scoring engine, seven-stage valuation pipeline, Bayesian thesis engine, and a hardened backtest stack are all implemented and tested. Awaiting one empirical IC run on real market data before the v0.4.0 promotion.

- 355 tests passing
- 13 orthogonal factors (10 additive + 3 penalty)
- 7-stage valuation pipeline
- Pluggable data sources (yfinance primary, Stooq fallback)
- Bayesian shrinkage calibration with sector-neutral IC

## How it actually works

The framework is dense, so here is the method in three layers, simple to complex. Read as far as you need.

### Layer 1 — plain English

When you point IAM at a stock, three things happen.

1. **It scores the stock.** Ten different "reasons to buy or sell" are evaluated separately — is it cheap, is it high quality, is the price already pricing in heroic growth, is the macro regime helpful, and so on. Each reason gets its own score. They are combined with explicit weights, and three penalty terms (fragility, leverage, execution risk) are subtracted. The final number is a single score between −1 and +1, but you can always see what each piece contributed.

2. **It valuates the stock.** A seven-stage pipeline asks the same question from four directions: what does today's price *imply*, what do *peers* and history say, what's the *intrinsic* DCF, and do those three agree? Disagreement is the most useful output — it tells you where the controversy is, not just an averaged number. Macro stress tests then re-run the pipeline only for names whose verdict actually flips.

3. **It tests itself.** A backtest harness runs the model month-by-month on historical data and asks: "Did high scores actually predict high returns?" The answer (the Information Coefficient) becomes the empirical weight the model places on its own opinions. If a signal didn't work historically, the model trusts it less.

That's the whole product. No black boxes — every number decomposes back to inputs.

### Layer 2 — how the pieces fit

**Factor scoring.** Composite = `Σ wᵢ · factorᵢ − Σ penaltyⱼ`. Ten factors with fixed, documented weights (see table below); each factor is implemented independently in `src/iam/factors/` and is orthogonal by design — valuation never blends with quality, sentiment never blends with reflexivity.

**Valuation pipeline.** Seven stages run in sequence, not in parallel. Stage 1 inverts the current price into an implied growth rate (reverse DCF). Stage 2 checks peer multiples. Stage 3 builds an intrinsic DCF bottom-up. Stage 4 triangulates: AGREE / TWO_OF_THREE / DISAGREE. Stages 5–6 detect when a macro shock would move the verdict and re-run only those names. Stage 7 emits Buy/Hold/Sell with a conviction band derived from triangulation spread.

**Thesis engine.** A Bayesian layer for scenario reasoning. You define Bull/Bear/Base scenarios with fair-value ranges. New evidence (earnings beat, guidance cut, macro shock) updates the posterior probability of each scenario — not the fair values themselves. Lets the model say "the Bull case is now 65% likely" instead of "the price target is X."

**Backtest harness.** Every month, build a point-in-time snapshot of each security, score it, then look at the realized 63-day forward return. The Spearman rank correlation between score and return is the **Information Coefficient (IC)**. Over 84 months, you get a distribution; the mean IC tells you if the signal works, the IC standard deviation tells you how consistent it is. The Information Ratio (IR = mean(IC) / std(IC)) is what institutional shops actually care about — 0.3–0.5 is realistic for equity factors.

### Layer 3 — the math and the audit trail

**IC calibration.** Empirical IC is converted to a reliability weight `r ∈ [0.5, 0.95]` that gates how much the arbitrator listens to each signal. We use **Bayesian shrinkage** to avoid overfitting on short backtests:

```
posterior_ic = (prior_strength · prior_ic + n · empirical_ic) / (prior_strength + n)
reliability  = clamp(0.5 + posterior_ic · 5,  0.5,  0.95)
```

With `prior_ic = 0.02` and `prior_strength = 36` months, 36 months of data give the prior and the empirical IC equal weight. Fewer months than that, and the model trusts the prior more than the noisy empirical estimate. This is the institutional default — a heuristic for "don't believe a backtest until you've seen three years of it."

**Newey-West HAC SE.** Forward-return windows overlap (a 63-day return at month *t* and month *t+1* share 62 days of price action), so naive standard errors understate IC volatility. We use `statsmodels` HAC covariance with maxlags=3 to correct. The corrected t-statistic is what gets quoted in reliability tests.

**Sector-neutral IC.** Global IC can be inflated by a sector tilt the model isn't actually skilled at. We stratify by sector, compute IC within each, and report a size-weighted average. If `IC_sector_neutral ≈ IC_global`, the signal is genuine. If it collapses, the signal was sector timing in disguise.

**Pluggable data sources.** Price and balance-sheet data flow through a `DataSource` contract (`src/iam/backtest/sources/base.py`). The default chain is yfinance → Stooq: yfinance is queried first (institutional-grade, includes quarterly debt); on any failure, Stooq is queried (free CSV export, sandbox-safe, price only). Every new source — FMP, Tiingo, custom CSV — implements three methods and slots in without touching `snapshots.py` or `runner.py`.

**Manifest.** Every backtest run writes a `manifest.json` capturing git SHA, file hashes for all backtest modules, and the full config dump. Two runs with the same manifest are guaranteed reproducible.

## What's in the box

**Factor scoring** (`iam.score`) — cross-sectional ranking across many names. Runs ten orthogonal factors plus three penalty terms to produce a composite score in `[-1, 1]`.

| Factor | Weight | Question |
|---|---|---|
| Expectations Difficulty | 0.22 | What does the price imply, and how hard is that to deliver? |
| Intrinsic Value | 0.20 | What is the asset worth on its cash flows? |
| Quality | 0.12 | How durable and capital-efficient is the business? |
| Relative Value | 0.10 | Cheap or expensive vs. peers and own history? |
| Sentiment | 0.08 | What does the market mood say? |
| Reflexivity | 0.08 | Does the stock price itself improve the fundamentals? |
| Reinvestment Runway | 0.07 | Can capital still be deployed at attractive rates? |
| Macro Regime | 0.05 | Does the current regime reward this style? |
| Crowding | 0.04 | How positioned is the trade? |
| Earnings Quality | 0.04 | Is the reported FCF real? |

Three **penalty factors** are then subtracted: **Fragility** (multiple compression on a small miss), **Leverage** (balance sheet stress and refinancing risk), and **Execution Risk** (operational, regulatory, and geographic complexity).

**Valuation pipeline** (`iam.ValuationPipeline`) — a seven-stage sequential deep-dive on a single name. Disagreement between stages is the most important output, not a problem to smooth away.

```
Stage 1: Reverse DCF       → What does the market expect?
Stage 2: Relative          → Do peers/history support those expectations?
Stage 3: Intrinsic         → What's fair value built bottom-up, independently?
Stage 4: Triangulation     → Do the three answers cluster, or disagree?
Stage 5: Macro Outlier     → Which conclusions move materially under macro stress?
Stage 6: Macro Re-overlay  → Re-run only the names whose verdict actually changes.
Stage 7: Verdict           → Buy/Hold/Sell + conviction band + peer-relative ranking.
```

**Backtest harness** (`iam.backtest`) — production-grade evaluation infrastructure. Pluggable data sources (yfinance → Stooq fallback), Polars-based price block, diskcache PIT snapshots, ProcessPool scoring, statsmodels Newey-West, sector-neutral IC, Bayesian shrinkage calibration. See [`docs/pipeline.md`](docs/pipeline.md) and [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Install

```bash
git clone https://github.com/WilliamHudspeth/institutional-alpha.git
cd institutional-alpha
pip install -e .
```

For live market data:

```bash
pip install -e ".[live]"
```

For the full backtest stack:

```bash
pip install -e ".[backtest]"
```

Requires Python 3.10+. Core dependencies are `numpy` and `pandas` only. The backtest extras add `polars`, `diskcache`, `statsmodels`, `tenacity`, `typer`, and `pydantic`.

## Quick start

### Interactive welcome screen

```bash
python main.py
```

A guided menu that lets you:
- Value a single security (7-stage pipeline)
- Score a security (10 factors + 3 penalties)
- Analyze scenarios with the thesis engine
- Evaluate historical factor performance

### Factor scoring

```python
from iam import Security, score

aapl = Security(ticker="AAPL")  # populate fundamentals as you wire data sources
result = score(aapl)

print(result.composite)          # e.g. 0.34
print(result.factor_breakdown)   # per-factor contributions
print(result.penalties)          # fragility / leverage / execution
```

### Valuation pipeline

```python
from iam import Security, ValuationPipeline

sec = Security(ticker="HYPCO", ...)  # populate fundamentals + market data
report = ValuationPipeline().run(sec)
print(report.explain())
# Stage 1: market implies 21% FCFE growth — 117% of peak.
# Stage 2: expensive vs peers/history (-44%).
# Stage 3: intrinsic DCF says -34%.
# Stage 4: TWO_OF_THREE — relative + intrinsic cluster; reverse DCF disagrees.
# Stage 7: HOLD | conviction: 0.52
```

### Thesis engine with Bayesian updating

```python
from iam.data.security import Assumption, Security, Thesis
from iam.thesis.engine import ThesisEngine
from iam.thesis.bayesian.priors import ScenarioPrior
from iam.thesis.bayesian.evidence import Evidence, ScenarioLikelihood

sec = Security(
    ticker="HYPCO",
    theses=[
        Thesis(label="Bull", fair_value_low=160.0, fair_value_high=200.0,
               narrative="Margin expansion drives re-rating.",
               assumptions=[Assumption("terminal_margin", 0.30, source="user")]),
        Thesis(label="Bear", fair_value_low=80.0, fair_value_high=110.0,
               narrative="Competition compresses margins.",
               assumptions=[Assumption("terminal_margin", 0.15, source="user")]),
    ],
)

engine = ThesisEngine()

# Bayesian update on an earnings beat
priors = [ScenarioPrior("Bull", 0.40), ScenarioPrior("Bear", 0.60)]
evidence = Evidence(
    description="Q2 earnings beat — margins expanded 200bps",
    signal_strength=0.8,
    likelihoods={
        "Bull": ScenarioLikelihood(0.85),
        "Bear": ScenarioLikelihood(0.25),
    },
)
updated = engine.apply_evidence(sec, priors, evidence)
print(updated.posteriors)    # posterior probabilities after the beat
print(updated.expected_value)
```

### Backtest

Build the price parquet once, then run the backtest. The data source automatically falls back from yfinance to Stooq if yfinance is unavailable.

```bash
# One-time price build (yfinance → Stooq fallback, writes data/prices/sp100.parquet)
python scripts/build_price_parquet.py --start 2018-01-01 --end 2024-12-31 --horizon 63

# Run the backtest with parallel scoring
python -m iam.backtest.cli backtest
```

Or programmatically:

```python
from iam.backtest import (
    BacktestConfig, load_universe_from_json, load_price_block, run_backtest,
)

cfg = BacktestConfig()
cfg.validate_paths()
universe, _ = load_universe_from_json(cfg.universe_file)
prices = load_price_block(cfg)

results = run_backtest(
    universe=universe,
    dates=["2024-01-31", "2024-02-29", "2024-03-29"],
    price_block=prices,
    config=cfg,
    score_field="cost_of_equity",
)
# results has columns: ic, ic_sector_neutral, hit_rate, spread, top, bottom, ...
```

See [`examples/`](examples/) for runnable end-to-end demos.

## Architecture

```
src/iam/
├── api/             # Public facade (value_security)
├── factors/         # 10 orthogonal factors + 3 penalty factors
├── engine/          # Composite scoring (factor weighting + penalties)
├── valuation/       # ReverseDCF, RelativeValuation, FCFEDCF, SOTP, Triangulator
├── pipeline/        # 7-stage orchestrator, macro overlay, verdict generator
├── thesis/          # ThesisEngine + Bayesian updater (priors, evidence, updater)
├── lenses/          # Rate-sensitive, platform compounder, Damodaran base, synthesis
├── data/            # Security, Fundamentals, MarketData, MacroContext, Damodaran
├── arbitration/     # Signal blending and reliability calibration
├── integration/     # Adapters and orchestrator
├── validation/      # Input parser and financial guards
└── backtest/        # Production backtest harness (v0.4 hardened stack)
    ├── sources/     # Pluggable data sources (yfinance, stooq, composite)
    ├── config.py    # Pydantic frozen config
    ├── manifest.py  # Git SHA + file hash audit trail
    ├── metrics.py   # IC, sector-neutral IC, Newey-West, rolling stability
    ├── snapshots.py # Diskcache PIT snapshots
    ├── prices.py    # Polars parquet block loader
    ├── quantiles.py # Decile spreads + cost-adjusted turnover
    ├── runner.py    # ProcessPool scoring loop
    ├── calibration.py  # Bayesian shrinkage IC → reliability
    └── cli.py       # Typer entry point
```

Full conceptual documentation:

- [`docs/framework.md`](docs/framework.md) — why orthogonality matters, the composite formula, and factor design rationale
- [`docs/factors.md`](docs/factors.md) — every factor's definition, sub-components, and default weights
- [`docs/pipeline.md`](docs/pipeline.md) — the seven pipeline stages in depth
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — full module map, dependency rules, validation gates
- [`REAL_DATA_BACKTEST_STRATEGY.md`](REAL_DATA_BACKTEST_STRATEGY.md) — empirical validation plan and gates
- [`RELEASES.md`](RELEASES.md) — release-by-release notes
- [`CHANGELOG.md`](CHANGELOG.md) — Keep-a-Changelog format

## Design principles

1. **Orthogonal factors.** Each factor measures one thing. Valuation and quality are separate inputs, not one blended score.
2. **Auditable.** Every composite score decomposes back into its factor contributions and penalty terms. No black-box aggregations.
3. **Pluggable data.** The model never assumes a specific data provider. Backtest data flows through the `DataSource` contract; add new sources by implementing three methods.
4. **No magic.** Default factor weights are explicit, documented, and easy to override. No hidden constants, no silent defaults.
5. **Regime-aware.** The macro overlay can re-weight factors or trigger a pipeline re-run, not just add noise to the composite.
6. **Empirically grounded.** Bayesian reliability weights are calibrated from historical IC, not heuristically assigned. Until the empirical run completes, the model uses conservative defaults clearly marked as such.

## Roadmap

- [x] Factor scoring engine: 10 factors + 3 penalties (v0.1.0)
- [x] Valuation pipeline: Reverse DCF → Relative → Intrinsic → Triangulation (v0.2.0-alpha)
- [x] Core data layer + Yahoo Finance adapter (v0.2.0-alpha)
- [x] Multi-lens valuation engine (v0.2.0-beta)
- [x] Threshold-gated macro overlay (v0.2.0-beta)
- [x] Thesis Engine: scenario modeling, simulation, sensitivity (v0.2.0-beta)
- [x] Verdict generator + Damodaran peer ranking (v0.2.0)
- [x] Bayesian updating engine (v0.2.0)
- [x] Backtest harness v1: IC, quantile spread (v0.2.0)
- [x] Data layer caching + Damodaran ground truth (v0.3.0–v0.3.3)
- [x] Synthetic backtest validation (v0.3.5)
- [x] Real-data infrastructure: Stooq loader, Newey-West, safe reliability loader (v0.3.6)
- [x] Hardened backtest stack v2: pluggable sources, Polars, ProcessPool, sector-neutral IC, Bayesian shrinkage (v0.4.0-rc1)
- [ ] Empirical IC run on real S&P 100 data (v0.4.0)
- [ ] Multi-horizon IC measurement (21d / 63d / 126d / 252d)
- [ ] Additional data sources (FMP, Tiingo) via `DataSource` contract
- [ ] International expansion (country risk premium calculations)

## License

MIT — see [LICENSE](LICENSE).

## Disclaimer

This is a research framework, not investment advice. Nothing here is a recommendation to buy or sell any security. Past performance of any factor model does not guarantee future results.
