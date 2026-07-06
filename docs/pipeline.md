# The Valuation Pipeline (v0.4.0-rc1)

> **Status:** v0.4.0-rc1 implements all 7 stages.

## Motivation

The v0.1.0 factor model treats every signal as a parallel vote: ten factors fire simultaneously and get weighted-averaged into one composite score. This works for cross-sectional ranking, but it has a structural weakness — **averaging signals together obscures whether they agree**.

A stock can look attractive on the composite because four mediocre factors voted yes and one strong factor voted no. Or because relative value says "cheap" while reverse DCF says "the market needs growth that has never been delivered" — both contradictory signals, but a weighted average smooths the conflict away.

The pipeline rebuilds the model as a **sequence**, where each stage challenges the previous one. Disagreement is no longer a problem to average away — it's the most important signal in the system.

## The seven stages

```
Stage 1: Reverse DCF       → What does the market expect?
Stage 2: Relative          → Do peers/history support those expectations?
Stage 3: Intrinsic         → What's fair value built bottom-up, independently?
Stage 4: Triangulation     → Do the three answers cluster, or disagree?
Stage 5: Macro Outlier     → Which conclusions move materially under macro stress?
Stage 6: Macro Re-overlay  → Re-run only the names whose verdict actually changes.
Stage 7: Verdict           → Buy/hold/sell + confidence + peer-relative ranking.
```

All seven stages are the valuation core and ship in v0.4.0-rc1.

## Stage 1 — Reverse DCF

The anchor. Instead of forecasting cash flows and discounting them, take the **current price as given** and solve for the operating performance that justifies it.

Mechanically: a two-stage Gordon-growth FCFE model. Discount rate, terminal growth, and explicit-forecast years are assumptions (defaults: 9%, 2.5%, 10y). Bisection solves for the high-growth-period CAGR that makes the discounted stream equal to the market price.

The output is not a verdict — it's a *thesis statement* the rest of the pipeline tests. "The market is implicitly assuming this company grows FCFE at 21% for ten years." Now we can ask whether that's plausible.

**Why it goes first:** every other stage benefits from knowing what we're trying to confirm or deny. Without the reverse DCF, relative valuation just tells you "the stock looks expensive vs peers" — but expensive *implying what*? With the reverse DCF, the question becomes: "expensive vs peers, *and* the market needs above-peak growth to justify it." That's a much sharper signal.

## Stage 2 — Relative Valuation

The confirm/deny on Stage 1. Three independent signals:

- **Sector multiple comparison.** Where does the stock's EV/EBITDA sit vs the sector median?
- **Own-history percentile.** Where does the current P/E sit within the stock's own 10-year range?
- **Peer FCF yield.** Higher or lower than the median of its peer set?

Each signal produces an implied move (e.g. "+25% to reach peer median"). The signals are weighted-averaged, but **within Stage 2 only** — the average never leaves this stage.

If reverse DCF says the market needs aggressive growth *and* relative says the stock is expensive vs peers, that's confirmation. If reverse DCF says the market is demanding aggressive growth *but* relative says the stock is cheap vs peers, that's interesting — peers may be even more aggressively priced, or our peer set is wrong.

## Stage 3 — Intrinsic (FCFE DCF + SOTP)

The independent build-up. Same two-stage Gordon structure as the reverse DCF, but instead of solving for growth, the user (or analyst consensus) **provides** the growth, margin, and discount-rate assumptions. The model just computes the resulting fair value.

For multi-segment businesses, SOTP runs instead: each segment is valued separately with the appropriate method (DCF for mature cash cows, EV/Sales for high-growth, scenarios for optionality), then summed and bridged to equity.

This stage is independent of market price by design. It's what *should* the stock be worth, given your view of the business — completely separate from what the market thinks.

## Stage 4 — Triangulation

The three stages produce three fair-value-to-price ratios. Stage 4 asks: do they cluster?

**Decision rule: equal-weighted, closest cluster wins.**

- All three within ±10% → **AGREE.** High-conviction setup. The summary calls out the move and the confidence is full.
- Best pair within ±20%, third outside → **TWO_OF_THREE.** The pair forms the cluster, the third is flagged as an outlier. The summary says "two methods cluster at X, but Y disagrees — worth investigating what Y sees."
- All three disagreeing → **DISAGREE.** The system reports the disagreement rather than producing a synthetic verdict.

This is the part that breaks with v0.1.0's averaging instinct. When methods disagree, we don't compute a mean — we surface the disagreement and let the user investigate. The disagreement is itself the most actionable output.

### Note on reverse DCF in the triangulation

Reverse DCF doesn't produce a fair value per share directly. It produces an *implied expectations* vector. To put it on a comparable axis with the other two stages, we convert: how does the market's implied growth compare to the company's historical peak?

If the market is implying peak growth, the conversion produces ~0% (the price requires the company to hit its best-ever performance — no margin of safety, no implied upside). If implying below peak, the conversion produces positive "upside." If implying above peak, negative.

The conversion is an approximation, but a defensible one — it lets reverse DCF participate in the cluster math without inventing a phony fair-value number.

## Stages 5–7 — Macro Overlay & Verdict (v0.4.0-rc1)

**Stage 5 — Macro Outlier:** Macro conditions applied to every name, but with a materiality gate. If the macro adjustment moves the cluster center by less than the threshold (default 5–10%), the original verdict stands. Only names where macro materially changes the conclusion get re-run.

**Stage 6 — Macro Re-overlay:** Re-run only the names whose verdict actually changed under macro stress. This is the "no meaningless averaging" principle applied at the macro level.

**Stage 7 — Verdict:** Each name gets a buy/hold/sell, a confidence band derived from Stage 4 spread, and a within-segment ranking using Damodaran's industry classifications as the peer-group source of truth.

---

## Relationship to v0.1.0 factors

The v0.1.0 factors aren't going away — they become *inputs* to specific pipeline stages:

| v0.1.0 factor | Where it feeds in v0.4.0-rc1 |
|---|---|
| Quality | Modulates Stage 3 confidence (durable businesses = more trustworthy FCFE forecast) |
| Earnings quality | Same — adjusts Stage 3 confidence downward when reported FCF is suspect |
| Reflexivity, Runway | Inputs to Stage 3's growth assumption when no explicit forecast is provided |
| Sentiment, Crowding | Modulators of Stage 7's confidence band (not the directional call itself) |
| Macro regime | Inputs to Stages 5 and 6 |
| Fragility, Leverage, Execution | Penalty modifiers in Stage 7 |

A stock's v0.1.0 composite score is still a valid cross-sectional ranking input. The pipeline is for deep dives on specific names.
