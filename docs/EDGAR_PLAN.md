# EDGAR-first point-in-time data: plan

Owner decision (2026-10-06): **EDGAR-first** for historical financials (FIX_PLAN Q1). This plan
delivers two roadmap items together on one shared data layer:

1. An IC backtest that measures something (today `data/results/ic/ic_summary.txt` shows `n_obs: 0`).
2. A geographic revenue mix from EDGAR, so the revenue-weighted ERP and marginal tax work for live tickers.

## Why the backtest measures nothing today (verified)
- `backtest/universe.py:57-64` builds every ticker with sector "Unknown", no fundamentals, and an
  invented 1,000,000,000 shares.
- `backtest/snapshots.py` freezes only price and debt, so scoring runs on empty fundamentals. Every
  composite is NaN and every date is skipped.

## What EDGAR provides (verified with live calls, 2026-10-06)
- **`companyfacts`** (one JSON per filer) has the core concepts: Revenues, NetIncomeLoss, operating
  cash flow, capex, tax, pretax income, LongTermDebt, StockholdersEquity, InterestExpense,
  OperatingIncomeLoss and dei shares outstanding.
  - Each fact carries `filed`, `accn`, `form`, `fy`, `fp`, `start` and `end`, which is enough for
    point-in-time selection (use only facts filed on or before the date).
  - **No dimensional facts**, so no segments or geography here.
- **`submissions`** gives the SIC code (for sector), former names, and the filing list with accession
  numbers.
- **The 10-K XBRL instance** (`<doc>_htm.xml`) does carry `srt:StatementGeographicalAxis` members, e.g.
  AAPL: `country:US`, `country:CN`, `aapl:OtherCountriesMember`. Geography comes from here.
- **Pitfall:** ticker-to-CIK mappings change. `company_tickers.json` maps BLK to CIK 1364742, now
  "BLACKROCK FINANCE, INC." (the pre-2024 entity); the current holding company has a new CIK. CIK
  resolution must be date-aware or override-able.

## Phases
**A. EDGAR point-in-time fundamentals layer** (`src/iam/data/edgar/`)
- A client with a declared User-Agent, rate limiting under SEC's 10 requests/second, an on-disk
  cache, and no network in tests (recorded fixtures).
- CIK resolution with an override table for known reorganisations.
- `fundamentals_as_of(cik, date)`: TTM revenue, net income, FCF (operating cash flow minus capex),
  operating margin, debt, cash, shares, interest expense, effective tax and equity, plus ROIC history
  where derivable. Every field records its provenance (tag, accn, filed, period); missing values are
  None.
- SIC code mapped to sector.

**B. Geographic revenue mix**
- Fetch the latest 10-K instance filed on or before the date. Parse revenue facts on
  `StatementGeographicalAxis` and map members (ISO `country:XX`, plus company-specific members by
  label) to the keys `country_risk` resolves.
- Return the mix with coverage, unresolved members and provenance. Never guess a member.
- Feed `Security.revenue_mix` in the live adapter (`fetch_security`) and in backtest snapshots.

**C. Backtest wiring**
- Snapshots get point-in-time fundamentals and revenue mix from Phase A/B. The universe loader stops
  inventing sector and shares.
- Run the IC backtest end to end and report `n_obs`, data coverage per date, and the result.

**D. Survivorship (decision point)**
- A survivorship-free universe needs historical constituents. EDGAR's `frames` API returns one
  concept for all filers per period, so a point-in-time "largest N by revenue" universe can include
  companies that later delisted.
- Their prices are the constraint: yfinance lacks most delisted tickers, and Stooq covers some.
  Coverage will be measured and reported, not assumed.

## Rules
- No fabricated numbers: missing is None with a reason.
- Failing-first tests; no network in tests.
- Provenance on every EDGAR-derived value.
- Each phase is its own PR, reviewed line by line, with CI green before merge.
