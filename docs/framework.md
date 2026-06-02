# The Framework

## Why most valuation models fail

A typical public valuation model — DCF, multiples, maybe a comparables overlay — is essentially answering one question:

> Is this asset cheap or expensive?

That's a useful question, but it's not the question elite discretionary and systematic funds are actually asking. They're asking at least six more:

- **Cheap for what reason?** A statistically cheap stock with collapsing margins is not the same opportunity as a statistically cheap stock with stable cash flows.
- **Cheap relative to what regime?** A 15× P/E is generous in one rate environment and punitive in another.
- **How fragile is the earnings stream?** How much does the multiple compress if growth slips by 200bps?
- **How reflexive is the multiple?** Does the share price *itself* feed back into the business (M&A currency, talent attraction, narrative)?
- **How crowded is the trade?** Crowded longs collapse nonlinearly; crowded shorts squeeze violently.
- **How reliable are management's reinvestment decisions?** A great business compounded by poor capital allocators is a mediocre investment.

A model that doesn't separately price each of these dimensions ends up systematically overweight one thing: statistically cheap, deteriorating, value-trap businesses. That's the failure mode this framework is designed around.

## Orthogonality

The core design principle is that factors should be **orthogonal** — they should each measure one and only one thing. Bundling quality into valuation, or sentiment into expectations, destroys the information.

Concretely:

- **Valuation** asks what the asset is worth on its cash flows.
- **Expectations** asks what growth and returns the *current price* implies, and how difficult those are to deliver.
- **Quality** asks how durable and capital-efficient the underlying business is.

A name can be cheap on valuation, demanding on expectations, and high on quality all at once — and the model should preserve that texture, not blend it into a single number.

## The composite

```
composite_score =
    0.22 * expectations_factor   +
    0.20 * intrinsic_value       +
    0.12 * quality               +
    0.10 * relative_value        +
    0.08 * sentiment             +
    0.08 * reflexivity           +
    0.07 * runway                +
    0.05 * macro_regime          +
    0.04 * crowding              +
    0.04 * earnings_quality

composite_score -= (
    fragility_penalty +
    leverage_penalty  +
    execution_risk_penalty
)
```

Each factor is normalized to roughly `[-1, 1]` so the weights are interpretable as actual relative importance. Penalties are subtractive — they can take a name out of contention regardless of how attractive it looks on the additive factors.

Default weights are calibrated for a generalist long-biased equity book. For sector specialists or different mandates, weights should be re-derived. The point of orthogonality is that you can re-weight without re-engineering.

## What changes by factor

A few of these deserve specific framing because they're less commonly built into public models.

### Expectations difficulty

The market price encodes an implied growth rate and ROIC. The right question is not "is the current multiple high?" but "what does this multiple require the business to deliver, and how does that compare to history and peers?"

```
expectation_difficulty = implied_growth / historical_max_growth
```

If the price requires the company to grow faster than it ever has, that's a penalty regardless of how "reasonable" the multiple looks in isolation.

### Reflexivity

Some businesses have a feedback loop between share price and fundamentals. High share prices:

- give them currency for acquisitions,
- attract better talent via equity comp,
- reinforce the narrative that pulls in capital,
- strengthen network effects via reinvestment.

NVIDIA, Tesla, Palantir, Coinbase — these all benefit from reflexivity in ways that don't show up in a normal DCF. Ignoring this factor systematically underprices them.

### Crowding

The same fundamental setup is worth less if everyone owns it. Crowded longs:

- compress faster on bad news,
- exhibit nonlinear downside,
- are sensitive to forced de-grossing in equity long/short books.

Crowded shorts squeeze. This factor is a timing and drawdown filter more than an alpha source.

### Multiple fragility

The single best penalty factor for high-duration growth. Ask: if growth slows by 10%, how much does the multiple compress?

```
fragility = pe_multiple / normalized_growth
```

High fragility names get crushed by minor disappointments. This is what catches the late-stage momentum trades a pure value model would miss.

## Beyond static scoring

The framework is designed to be extended into a **Bayesian updating engine**. Instead of a static bull/base/bear, every earnings release updates the posterior probability of each scenario:

```
posterior = prior * likelihood_ratio
```

This is what separates frameworks that get re-derived quarterly from frameworks that learn. The current scaffold stops short of this — it's on the roadmap and would be a great contribution.

## What this framework is not

- **Not a black box.** Every composite score decomposes back into its factor contributions.
- **Not a complete trading system.** No position sizing, no execution model, no risk overlay at the portfolio level. That's downstream.
- **Not asset-class-general.** The factor definitions assume listed equities. Credit, rates, FX would need different definitions.
- **Not a substitute for judgment.** It surfaces what to look at; it doesn't decide what to buy.
