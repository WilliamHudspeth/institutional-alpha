# Institutional Alpha Model (IAM)

> A multi-factor equity scoring framework that prices what elite funds actually price.

Most public valuation models stop at DCF or relative multiples. Institutional discretionary and systematic funds implicitly price a much wider surface: **expectations difficulty, quality, reflexivity, crowding, regime fit, fragility, and capital allocation quality.** This repo is an open-source attempt to encode that surface as an orthogonal, weighted, auditable factor model — written in plain Python so it's easy to read, fork, and extend.

## Status

**v0.2.0** — the framework is complete. The factor scoring engine, seven-stage valuation pipeline, thesis engine with Bayesian updating, and Damodaran-anchored peer ranking are all implemented and tested.

## What's in the box

The framework has three complementary entry points.

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

**Valuation pipeline** (`iam.ValuationPipeline`) — a seven-stage sequential deep-dive on a single name. Instead of averaging signals, each stage challenges the previous one. Disagreement between stages is the most important output, not a problem to smooth away.

```
Stage 1: Reverse DCF       → What does the market expect?
Stage 2: Relative          → Do peers/history support those expectations?
Stage 3: Intrinsic         → What's fair value built bottom-up, independently?
Stage 4: Triangulation     → Do the three answers cluster, or disagree?
Stage 5: Macro Outlier     → Which conclusions move materially under macro stress?
Stage 6: Macro Re-overlay  → Re-run only the names whose verdict actually changes.
Stage 7: Verdict           → Buy/Hold/Sell + conviction band + peer-relative ranking.
```

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

Requires Python 3.10+. Core dependencies are `numpy` and `pandas` only.

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

# Static evaluation
evaluation = engine.evaluate(sec)
print(f"Range: {evaluation.worst_case} – {evaluation.best_case}")

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
print(updated.posteriors)   # posterior probabilities after the beat
print(updated.expected_value)
```

### Backtest harness

```python
from tests.harness import BacktestHarness
from iam.data.security import Security

# Point-in-time historical data: (Security, forward_return) pairs
data = [
    (Security(ticker="AAPL", fundamentals=..., market=...), 0.12),  # 12% 1M return
    (Security(ticker="MSFT", fundamentals=..., market=...), -0.05),  # -5% return
    # ... 50+ more securities
]

harness = BacktestHarness(data)
results = harness.run()  # Score all securities, returns DataFrame

# Factor performance metrics
ics = harness.calculate_ic()           # Information Coefficient vs forward returns
print(ics.head())  # Spearman correlation of each factor with out-of-sample returns

# Quantile analysis
spread = harness.quantile_spread(factor="composite", q=5)
print(f"Top vs Bottom quintile spread: {spread:+.1%}")
```

See [`examples/`](examples/) for runnable end-to-end demos.

## Architecture

```
src/iam/
├── factors/          # 10 orthogonal factors + 3 penalty factors
├── engine/           # composite scoring (factor weighting + penalties)
├── valuation/        # ReverseDCF, RelativeValuation, FCFEDCF, SOTP, Triangulator
├── pipeline/         # 7-stage orchestrator, macro overlay, verdict generator
├── thesis/           # ThesisEngine + Bayesian updater (priors, evidence, updater)
├── lenses/           # alternative valuation lenses (rate-sensitive, platform, Damodaran)
└── data/             # Security, Fundamentals, MarketData, MacroContext, Yahoo adapter

tests/
├── harness.py        # BacktestHarness: historical factor performance evaluation
└── test_backtest.py  # BacktestHarness unit tests
```

Full conceptual documentation:

- [`docs/framework.md`](docs/framework.md) — why orthogonality matters, the composite formula, and factor design rationale
- [`docs/factors.md`](docs/factors.md) — every factor's definition, sub-components, and default weights
- [`docs/pipeline.md`](docs/pipeline.md) — the seven pipeline stages in depth

## Design principles

1. **Orthogonal factors.** Each factor measures one thing. Valuation and quality are separate inputs, not one blended score.
2. **Auditable.** Every composite score decomposes back into its factor contributions and penalty terms. No black-box aggregations.
3. **Pluggable data.** The model never assumes a specific data provider. Wire in your own fundamentals; use the Yahoo adapter for live data.
4. **No magic.** Default factor weights are explicit, documented, and easy to override. No hidden constants, no silent defaults.
5. **Regime-aware.** The macro overlay can re-weight factors or trigger a pipeline re-run, not just add noise to the composite.

## Roadmap

- [x] Factor scoring engine: 10 factors + 3 penalties (v0.1.0)
- [x] Valuation pipeline: Reverse DCF → Relative → Intrinsic → Triangulation (v0.2.0-alpha)
- [x] Core data layer + Yahoo Finance adapter (v0.2.0-alpha)
- [x] Multi-lens valuation engine (v0.2.0-beta)
- [x] Threshold-gated macro overlay (v0.2.0-beta)
- [x] Thesis Engine: scenario modeling, simulation, sensitivity analysis (v0.2.0-beta)
- [x] Verdict generator + peer-relative ranking via Damodaran industries (v0.2.0)
- [x] Bayesian updating engine (v0.2.0)
- [x] Backtest harness: Information Coefficient and quantile spread analysis (v0.2.0)

## License

MIT — see [LICENSE](LICENSE).

## Disclaimer

This is a research framework, not investment advice. Nothing here is a recommendation to buy or sell any security. Past performance of any factor model does not guarantee future results.
