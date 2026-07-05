---
name: Factor proposal
about: Propose a new scoring factor or penalty
title: "feat(factors): add "
labels: research
---

<!-- See docs/COMMUNITY_CONTRIBUTIONS.md#1-factor-proposals before filing -->

## What does this factor measure?

<!-- One sentence. What signal, and why do you believe it predicts return or risk? -->

## Normalization

- Range: [-1, 1] additive factor / [0, 1] penalty (delete one)
- Sub-components and default weights:

## Backtest evidence

- IC with the factor included:
- IC without it (baseline):
- Correlation with existing factors (flag anything > 0.80):

<!-- If you haven't run the backtest yet, that's fine — open the issue to discuss the
     idea first, then attach evidence once you have a draft implementation. -->

## Data requirements

<!-- What fields does this need on Security that aren't already populated? -->
