# Factor Definitions

Each factor is normalized to `[-1, 1]` where positive is bullish for the composite. Sub-components are listed with their default weights inside the factor.

## Additive factors

### 1. Intrinsic Value (weight: 0.20)

Cash-flow-based fair value vs. current price.

| Sub-component | Default weight |
|---|---|
| DCF residual (fair value / price − 1) | 0.50 |
| Reverse DCF implied growth gap | 0.30 |
| Owner earnings yield | 0.20 |

### 2. Expectations Difficulty (weight: 0.22)

How hard does the current price require the business to work?

| Sub-component | Default weight |
|---|---|
| Implied growth / historical max growth | 0.40 |
| Implied ROIC / industry peak ROIC | 0.35 |
| Implied margin / historical peak margin | 0.25 |

Inverted so that *easier* expectations score higher.

### 3. Quality (weight: 0.12)

Durability and capital efficiency.

| Sub-component | Default weight |
|---|---|
| ROIC persistence (rolling 5y) | 0.25 |
| Gross margin stability | 0.15 |
| FCF conversion | 0.20 |
| Balance sheet strength | 0.10 |
| Operating margin stability | 0.10 |
| Dilution control | 0.05 |
| Reinvestment efficiency | 0.15 |

### 4. Relative Value (weight: 0.10)

Vs. peers and own history.

| Sub-component | Default weight |
|---|---|
| EV/EBITDA vs. sector median | 0.30 |
| P/E vs. own 10y range (percentile) | 0.30 |
| FCF yield vs. peers | 0.25 |
| EV/Sales vs. growth-adjusted peers | 0.15 |

### 5. Sentiment (weight: 0.08)

Mood and momentum.

| Sub-component | Default weight |
|---|---|
| Analyst revision breadth (30d) | 0.30 |
| Price momentum (6m, vol-adjusted) | 0.30 |
| Earnings surprise persistence | 0.20 |
| News/social sentiment delta | 0.20 |

### 6. Reflexivity (weight: 0.08)

Does the stock price improve the fundamentals?

| Sub-component | Default weight |
|---|---|
| Equity-currency strength (M&A capacity) | 0.25 |
| Network effect strength | 0.25 |
| Talent attraction (equity comp leverage) | 0.20 |
| Acquisition optionality | 0.15 |
| Narrative reinforcement | 0.15 |

### 7. Reinvestment Runway (weight: 0.07)

Can capital still scale?

| Sub-component | Default weight |
|---|---|
| TAM remaining | 0.30 |
| Incremental ROIC | 0.30 |
| Geographic expansion potential | 0.15 |
| Adjacency potential | 0.15 |
| Recurring revenue mix | 0.10 |

### 8. Macro Regime (weight: 0.05)

Does the current regime reward this style? Note that this factor can also be implemented as a *re-weighter* of other factors rather than an additive term — see `engine/composite.py`.

| Sub-component | Default weight |
|---|---|
| Real rate regime | 0.25 |
| Liquidity conditions | 0.20 |
| Credit spreads | 0.15 |
| Yield curve slope | 0.15 |
| PMI direction | 0.15 |
| Dollar strength | 0.10 |

### 9. Crowding (weight: 0.04)

How positioned is the trade?

| Sub-component | Default weight |
|---|---|
| Hedge fund ownership concentration | 0.30 |
| Retail positioning | 0.20 |
| Short interest (% float) | 0.20 |
| Options call skew | 0.15 |
| Passive index concentration | 0.15 |

Inverted: *less* crowded scores higher.

### 10. Earnings Quality (weight: 0.04)

Is the reported FCF real?

| Sub-component | Default weight |
|---|---|
| Accruals ratio | 0.20 |
| SBC as % of revenue | 0.20 |
| Cash conversion | 0.20 |
| Working capital quality | 0.15 |
| Capex authenticity | 0.15 |
| One-time adjustments frequency | 0.10 |

## Penalty factors

Subtracted from the composite. Each is normalized to `[0, 1]`.

### Fragility Penalty

How much does the multiple compress on a small earnings disappointment?

```
fragility = pe_multiple / normalized_growth
```

Scaled and capped. Particularly important for high-duration AI/growth names.

### Leverage Penalty

Balance sheet stress.

| Sub-component | Default weight |
|---|---|
| Net debt / EBITDA | 0.30 |
| Interest coverage | 0.25 |
| Refinancing risk (maturity wall in 24m) | 0.20 |
| Liquidity ratio | 0.15 |
| Debt maturity profile | 0.10 |

### Execution Risk Penalty

Not all growth is equally executable.

| Sub-component | Default weight |
|---|---|
| Operational complexity | 0.25 |
| Supply chain dependency | 0.20 |
| Regulatory risk | 0.20 |
| Geographic risk | 0.20 |
| Integration risk (active M&A) | 0.15 |
