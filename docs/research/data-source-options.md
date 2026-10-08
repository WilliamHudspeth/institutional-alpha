# Data Source Options: FMP-first or EDGAR-first

This memo compares Financial Modeling Prep (FMP) and SEC EDGAR as the primary source of
historical financials. Code references are to the repository at 0.4.0-rc1.

## Decision

**EDGAR-first for historical financials.** The point-in-time EDGAR layer (`src/iam/data/edgar/`)
is the basis for the backtest and for the geographic revenue mix; see
[backtest](backtest.md). FMP remains an optional premium tier in the router and can supply
fields EDGAR does not map cleanly. Prices still come from the tiered chain
([data sources](../data-sources.md)).

The alternative analysed below, FMP-first, was recommended by an earlier draft of this memo. It is
kept here with the reasons it was not chosen as the sole basis.

## What each source returns today

| | FMP (`backtest/sources/fmp_source.py`) | SEC EDGAR (`backtest/sources/sec_edgar_source.py`, `data/edgar/`) |
|---|---|---|
| Implemented | Daily closing prices, quarterly total debt, bulk price history | Total debt (current plus noncurrent, with fallbacks), revenue, net income and other core concepts via `companyfacts` |
| Declared but not implemented | `Capability.FUNDAMENTALS` is declared; no fundamentals fetch exists | Prices (never provided) |
| Point-in-time | Depends on the endpoint; not verified | Yes. Every fact has a filing date |
| Cost | Paid API; key required (`FMP_API_KEY`). Pricing and rate limits not verified here: check the provider's current documentation | Free, no key. Declared User-Agent required. Client throttles below 10 requests/s |

## Which `Fundamentals` fields each can fill

- FMP: `total_debt` and price today. Its standardised statements could fill most of the rest once
  mapped.
- EDGAR: `total_debt`, `revenue_ttm` and `revenue_history`, `net_income_ttm`, and with the newer
  layer operating cash flow, capex, tax, interest expense, equity and shares, each with
  provenance.
- Gaps on both sides: `sbc_ttm`, `change_in_working_capital`, `roic_history`, and a reliable
  `shares_outstanding` history.

## XBRL mapping risks on the EDGAR side

- There is no single debt tag. Total debt needs a fallback order (`DebtCurrent` plus
  `LongTermDebtNoncurrent`, or `LongTermDebt`).
- Revenue maps to `RevenueFromContractWithCustomerExcludingAssessedTax` for most filers but is
  absent or different for some industries, such as financials.
- Free cash flow, stock-based compensation and EBITDA have no universal tag. They must be
  rebuilt from components with sector-aware rules.
- Restatements and ticker-to-CIK changes require date-aware handling.

## Trade-offs

| | FMP-first | EDGAR-first |
|---|---|---|
| Coverage of derived fields | Broad once mapped | Needs more mapping work |
| Point-in-time guarantee | Unverified | Built in |
| Cost and access | Full path depends on a paid key | Free, no key |
| Fit with the zero-configuration goal | Weak | Strong |

## Routing the live pipeline through the tiered router

The smallest change to give the live adapter provenance:

1. In `YFinanceAdapter.fetch`, build the router with `build_tiered_source(...)`.
2. Replace the direct lookups of price and total debt with `fetch_price` and `fetch_debt` on the
   router.
3. Attach `audit_summary()` to the resulting `Security`, for example in
   `qualitative["data_provenance"]`.
4. Leave any field the router cannot fill as `None`. Do not reintroduce estimated defaults.

## Open items

- Confirm the current FMP API version and pricing before relying on it.
- Decide how far to extend EDGAR concept mapping before using FMP to fill the remainder.
