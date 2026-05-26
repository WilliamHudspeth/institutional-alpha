# Roadmap

This document describes where the project is going. It's organized by **confidence level**, not by chronological version — the further down you read, the less committed any specific item is. Near-term sections describe work that has a clear design and a defined "done." Long-term sections describe directions we find compelling but haven't fully scoped.

If you're looking for what to contribute to, **start with the Near Term section**. If you want to understand the project's broader thesis, read the Long Term and Open Questions sections.

> **Versioning convention.** Major.minor.patch with pre-release suffixes (`a` = alpha, `b` = beta). Pre-release versions are shipped releases — they're not "in development." The version reflects API stability, not feature completeness.

---

## Design principles

These don't change, regardless of what gets built on top of them.

1. **Orthogonality.** Each factor or engine measures one thing. Quality, valuation, and sentiment are separate inputs, never blended into a single score before the user can see them.
2. **Auditability.** Every output decomposes back into its inputs. If a verdict is "buy with 70% confidence," the user can trace exactly which assumptions, signals, and weights produced that number.
3. **Disagreement as signal.** When methods disagree, we surface the disagreement rather than averaging it away. Conflict between valuation methods is often more actionable than consensus.
4. **Calibration over cleverness.** A simple model with backtested weights beats a sophisticated model with vibes-based weights. New components must justify themselves with evidence, not aesthetics.
5. **No black boxes for the user.** Even if internal math is complex, the user-facing output is a structured argument they can interrogate.

---

## Near term — committed work

These items have defined scope and concrete acceptance criteria. They're what to expect in the next few months.

### v0.2.0-beta — Macro overlay with threshold gating

**Scope.** Implement Stages 5–6 of the pipeline. Every security gets a macro adjustment computed, but the cluster center (from Stage 4) only updates if the macro impact exceeds a threshold. Below threshold, the original verdict stands.

**Why it matters.** Macro adjustments applied to every name produce a lot of noise — most names aren't materially sensitive to most macro variables. Threshold gating preserves the discipline of "only meaningful changes propagate."

**Done when:** macro sensitivities (`dV_dRates`, `dV_dCredit`, `dV_dFX`) computed per security; threshold-gated cluster update wired into the pipeline; tests cover the gating logic; example shows a name that triggers macro re-run vs one that doesn't.

### v0.2.0 — Verdict and peer-relative ranking

**Scope.** Stage 7. Translate the triangulation cluster center into a directional call (buy / hold / sell) with a confidence band. Rank the name within its Damodaran industry bucket — *cheap on absolute basis* is less useful than *cheap relative to its actual peer set*.

**Why it matters.** This is what closes the loop. Without Stage 7, the pipeline produces structured arguments but no actionable verdict.

**Done when:** Damodaran industry classifications embedded (Jan 2026 snapshot); within-industry ranking implemented; confidence band derived from Stage 4 spread; v0.2.0 tagged as a real (non-pre-release) GitHub release.

### v0.2.1 — Confidence layer

**Scope.** Three additions that the current model lacks and that meaningfully improve realism:

- **Forecastability score** (`src/iam/confidence/forecastability.py`). Some businesses are simply easier to model than others. Microsoft has higher forecastability than Tesla. Inputs: revenue volatility, margin stability, cyclicality, estimate dispersion. Use it to dynamically reduce DCF confidence when forecastability is low.
- **Valuation dispersion** (`src/iam/confidence/dispersion.py`). The spread across the three pipeline methods *is* a measure of uncertainty. Convert that spread into a `confidence = 1 - normalized_dispersion` penalty applied to the final verdict.
- **Method confidence weighting**. Replace equal-weighted triangulation with contextual trust scores. DCF deserves more trust for mature compounders; relative valuation deserves more for banks; reverse DCF deserves more for high-growth names where DCF assumptions are too speculative.

**Why it matters.** Right now confidence is determined by data availability. After v0.2.1, it's also determined by *how hard the business is to value* and *how much the methods agree*. That's much closer to how a real analyst thinks.

**Done when:** all three components implemented with tests; pipeline output includes a `forecastability_score` and `method_dispersion` in addition to the existing breakdown.

---

## Medium term — directions we're exploring

These items have a clear motivation but the scope and design aren't fully locked. They'll likely happen but the exact form and order may change.

### Regime-aware weight engine (v0.3.x)

Static factor weights are a known weakness. A factor that's predictive in tightening regimes may be noise in liquidity expansions. The plan: a lightweight `RegimeWeightEngine` that adjusts weights based on a small number of macro variables (real rates, credit spreads, PMI direction).

What we want to avoid: hand-labeling six regimes (`GOLDILOCKS`, `STAGFLATION`, etc.) and switching between them. That's a clean abstraction that doesn't survive contact with real macro data, which rarely fits cleanly into named buckets. The version we'd actually build uses continuous macro inputs and produces smooth weight adjustments.

### Historical and regime-normalized multiples

Current relative valuation compares to current peer medians. Two improvements:

- **Own-history percentile.** Where does the stock trade vs its own 10-year range? Cheap-vs-peers is different from cheap-vs-history.
- **Rate-normalized multiples.** 30× P/E at 0% rates is not 30× P/E at 5% rates. Adjusting multiples for the rate regime they were observed in makes historical comparisons more honest.

### Signal half-life decay

Not all factors persist equally. Sentiment decays in days, quality in years. Adding a `half_life_days` field to each factor and exponentially decaying stale signals would prevent the model from over-weighting last quarter's narrative.

### Backtest harness

The single most important missing piece. Without a way to measure ex-post performance of each factor and the composite, we can't calibrate weights or validate the triangulation thresholds. The harness needs to:

- Run the pipeline on historical data point-in-time (no lookahead bias)
- Measure information coefficient (IC) by factor across time
- Validate the triangulation cluster thresholds (10% / 20%) against ex-post returns
- Test that the macro overlay's threshold gating actually improves vs always applying it

This is foundational work that should arguably come before more new factors. It's listed here rather than near-term because building it well is a significant project.

### Probabilistic valuation

Replace point estimates with distributions via Monte Carlo. Sample over the input ranges (growth, margins, discount rates) instead of using single values; produce a distribution of fair values rather than one number. The 5th/95th percentile becomes the confidence band, derived from the simulation rather than from method spread.

### Catalyst engine

Cheap stocks without catalysts often stay cheap. A separate factor that tracks earnings revisions, insider buying, buybacks, product launches, and activist involvement would separate "actionable cheap" from "value trap cheap."

### Optionality factor

DCF systematically underprices asymmetric upside — Amazon's AWS in 2010, Meta's mobile pivot, NVIDIA's CUDA moat. A factor that captures TAM-expansion optionality (platform leverage, adjacency potential, hidden assets) would address this. Hard to do without becoming arbitrary; that's why it's medium-term rather than near.

---

## Long term — open questions

These are problems we find genuinely interesting but for which we don't yet have credible approaches. They may or may not happen. Listing them here is partly aspiration and partly an invitation — if a contributor has done serious work in any of these areas, we'd love to hear about it.

### Bayesian thesis updating

Each earnings release should update the posterior probability of the original thesis. Mechanically straightforward (`posterior = prior × likelihood`); the hard part is defining likelihood functions for fuzzy fundamental events ("margin compression was 200bps worse than guided"). Done well, this turns a one-shot valuation into a continuous monitoring system.

### Forecast error attribution

When a thesis is wrong, *which assumption* was wrong? Was it growth, margins, terminal multiple, or macro? Building this requires storing every valuation run with its inputs and reconciling against realized fundamentals over multi-year windows. The infrastructure is real work; the value is meta-learning — the system would know which of its assumptions tend to fail.

### Factor efficacy tracking across regimes

Related to the above. Track the information coefficient of each factor over rolling windows and across regimes. Discover empirically which factors work where. Currently this is asserted in our documentation ("quality is strongest in tightening regimes") without evidence; the long-term version would measure it.

### Management quality

Capital allocation discipline, guidance credibility, dilution behavior, acquisition track record. Massively important and almost impossible to quantify without subjective inputs. Probably the area where qualitative human judgment continues to dominate any model we could write.

### Earnings call NLP

Tone shifts, linguistic uncertainty markers, guidance changes. Real value exists in this analysis, but building it well requires either licensed NLP infrastructure or the patience to fine-tune open models on financial language. Not currently scoped.

### Reinforcement learning for sizing and timing

If the framework eventually produces durable alpha signals, the question becomes how to size and time positions optimally. RL is the natural tool. Calling this "near-term" would be dishonest — applying RL to financial decision-making well is an active research area, and most attempts fail because of reward function specification.

---

## What we are explicitly not building

These appear in some adjacent projects and roadmaps. They're not on ours, and probably won't be.

- **A "score every stock in the universe" cross-sectional ranker.** The v0.1.0 factor engine can be used this way, but the pipeline is deliberately designed for deep dives on individual names. Universe-wide scoring is a different problem; other tools do it better.
- **A trading execution layer.** This is a research framework. Order routing, broker integration, slippage modeling are out of scope. The framework's outputs are inputs to a portfolio process, not a trading system.
- **Real-time market data infrastructure.** We're not building data feeds. The framework accepts whatever data you provide via the `Security` dataclass; integrating with vendors (FMP, yfinance, etc.) is the job of adapter modules, and even those are user-supplied for now.
- **A user interface.** Outputs are Python objects and printable reports. If someone wants a web UI on top, that's a separate project.
- **Generative research reports written by LLMs.** The framework produces structured arguments. Translating those into prose is something a user can do; the framework itself shouldn't be in the business of generating prose that *looks* analytical.

---

## How to contribute to the roadmap

The roadmap itself is a working document. If you have a strong opinion on:

- An item that should be promoted from medium-term to near-term
- An open question you've made progress on
- Something that should be removed from "not building" because we missed something
- An entirely new direction we should be considering

Open an issue or a discussion on GitHub. The bar for changing the roadmap is "concrete proposal with rationale and rough scope" — not "this would be cool to have."

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to contribute code to specific roadmap items.
