# Institutional Alpha Model (IAM)

> A multi-factor equity scoring framework that goes beyond "cheap vs. expensive."

Most public valuation models stop at DCF or relative multiples. Institutional discretionary and systematic funds implicitly price a much wider surface: **expectations difficulty, quality, reflexivity, crowding, regime fit, fragility, and capital allocation quality.**

This repo is an open-source attempt to encode that surface as an orthogonal, weighted, auditable factor model — written in plain Python so it's easy to read, fork, and extend.

## Status


 **v0.2.0.** The framework is now fully realized with a Bayesian updating engine for adaptive inference, a threshold-gated Macro Overlay that dynamically recalculates intrinsic value during rate shocks, and a robust Valuation Pipeline that outputs actionable verdicts.

## Core idea

Instead of one number ("fair value"), the framework asks ten questions in parallel and combines them into a single composite score in `[-1, 1]`:

| Factor | Question it answers |
|---|---|
| Intrinsic Value | What's the asset worth on cash flows? |
| Expectations | What growth/ROIC does the price imply, and how hard is that? |
| Quality | How durable and capital-efficient is the business? |
| Relative Value | Cheap or expensive vs. peers and history? |
| Sentiment | What does the market mood say? |
| Reflexivity | Does the stock price *itself* improve the fundamentals? |
| Runway | Can capital still be reinvested at attractive rates? |
| Macro Regime | Does the current regime reward this style? |
| Crowding | How positioned is the trade? |
| Earnings Quality | Is the reported FCF real? |

Then three **penalty factors** are subtracted:

- **Fragility** — how much does the multiple compress on a small disappointment?
- **Leverage** — balance sheet stress and refinancing risk
- **Execution Risk** — operational, regulatory, geographic complexity

See [`docs/framework.md`](docs/framework.md) for the conceptual writeup and [`docs/factors.md`](docs/factors.md) for each factor's definition.

## Install

```bash
git clone https://github.com/YOUR_USERNAME/institutional-alpha.git
cd institutional-alpha
pip install -e .
```

Requires Python 3.10+. No heavy dependencies — just `numpy` and `pandas`.

## Quick start

Two entry points depending on what you want:

**Factor scoring (v0.1.0):** cross-sectional ranking across many names.

```python
from iam import Security, score

aapl = Security(ticker="AAPL")  # add fundamentals as you wire data sources
result = score(aapl)

print(result.composite)          # e.g. 0.34
print(result.factor_breakdown)   # per-factor contributions
print(result.penalties)          # fragility / leverage / execution
```

**Valuation pipeline (v0.2.0-alpha):** deep-dive on a single name.

```python
from iam import Security, ValuationPipeline

sec = Security(ticker="HYPCO", ...)  # populate fundamentals + market
report = ValuationPipeline().run(sec)
print(report.explain())
# Stage 1: market implies 21% FCFE growth — 117% of peak.
# Stage 2: expensive vs peers/history (-44%).
# Stage 3: intrinsic DCF says -34%.
# Stage 4: TWO_OF_THREE — relative + intrinsic cluster; reverse DCF disagrees.
```

**Thesis scenarios (v0.2.0-alpha):** attach competing bull/bear views to a security.

```python
from iam.data.security import Assumption, Security, Thesis
from iam.thesis.engine import ThesisEngine

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
evaluation = engine.evaluate(sec)
print(f"Consensus Range: {evaluation.worst_case} - {evaluation.best_case}")
# You can also dynamically calculate fair values via pipeline injection:
# engine.simulate(sec, valuation_fn=my_dcf_function)
```

See [`examples/`](examples/) for runnable end-to-end demos of both.

## Design principles

1. **Orthogonal factors.** Each factor measures one thing. Valuation and quality are separate inputs, not one blended score.
2. **Auditable.** Every composite score decomposes back into its factor contributions and penalty terms.
3. **Pluggable data.** The model doesn't care where fundamentals come from — wire in your own provider.
4. **Regime-aware.** The macro filter can re-weight other factors instead of just adding to them.
5. **No magic.** Default factor weights are explicit, documented, and easy to override.

## Roadmap

- [x] Valuation pipeline: Reverse DCF → Relative → Intrinsic → Triangulation (v0.2.0-alpha)
- [x] Core data layer + Yahoo Finance adapter (v0.2.0-alpha)
- [x] Thesis Engine + Sensitivity Analysis (v0.2.0-alpha)
- [x] Macro overlay with threshold-gated re-run (v0.2.0-beta)
- [x] Verdict + peer-relative ranking via Damodaran industries (v0.2.0)
- [x] Bayesian updating engine (priors → posterior on earnings releases)
- [ ] Backtest harness

## v0.2.0-beta Upgrade Notes

**Note:** As of v0.2.0-beta, the Thesis Engine has been moved to `src/iam/thesis/`. If you are importing `ThesisEngine` from the root directory, please update your import statement to `from iam.thesis.engine import ThesisEngine`.

## License

MIT — see [LICENSE](LICENSE).

## Disclaimer

This is a research framework, not investment advice. Nothing here is a recommendation to buy or sell any security. Past performance of any factor model does not guarantee future results.

