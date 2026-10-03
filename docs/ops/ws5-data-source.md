# WS5 data-source memo: FMP-first vs EDGAR-first

## What each source actually returns today
- **FMP (`backtest/sources/fmp_source.py`)**: Returns point-in-time daily closing prices, quarterly total debt (from balance sheets), and bulk daily price history. While it declares a `FUNDAMENTALS` capability, it currently only implements HTTP fetches for prices and debt.
- **SEC EDGAR (`backtest/sources/sec_edgar_source.py` & `data/fetcher.py`)**: Returns point-in-time data, strictly filtered by filing date to prevent look-ahead bias. It provides total debt (by combining current and noncurrent tags). The redundant fetcher (`data/fetcher.py`) also extracts a few fundamental concepts: Revenue, Net Income, Assets, Liabilities, and Equity. It never returns price data.

## Which pipeline fields (`Fundamentals`) each can fill
- **FMP**: Out of the box, the existing code explicitly fetches data to fill `total_debt` and market `price`. Given its standardized API format, it is fully capable of filling the rest of the `Fundamentals` model (e.g., `revenue_ttm`, `fcf_ttm`, `sbc_ttm`, margins) once mapped.
- **SEC EDGAR**: Currently fills `total_debt`, `revenue_ttm` / `revenue_history`, and `net_income_ttm`. 
- **Gaps**: Both sources currently lack code to populate complex `Fundamentals` fields such as `capex_ttm`, `sbc_ttm`, `change_in_working_capital`, `fcf_ttm`, `roic_history`, and `shares_outstanding` (which `fetcher.py` notes is tricky to derive accurately from the SEC API).

## The XBRL-mapping gaps on the EDGAR side
- Standardizing US-GAAP tags across thousands of filers is brittle. As shown in `sec_edgar_source.py`, there is no single, unified tag for debt; it requires a fallback hierarchy (`DebtCurrent` + `LongTermDebtNoncurrent`, or `LongTermDebt`). 
- In `fetcher.py`, Revenue maps to `RevenueFromContractWithCustomerExcludingAssessedTax`, which may be missing entirely for certain industries (e.g., financials).
- Crucial cash-flow and profitability metrics like Free Cash Flow, Stock-Based Compensation, and EBITDA lack universal, clean XBRL tags and would require highly complex, sector-aware reconciliation logic to reconstruct reliably from EDGAR statements.

## Cost and rate limits
- **FMP**: The code assumes this is a paid API, gating access behind the presence of an `FMP_API_KEY` (`PREMIUM` tier). Cost and rate limits: unverified — check provider docs.
- **SEC EDGAR**: The code assumes it is free (`OFFICIAL` tier) and requires no API key. It enforces an SEC-mandated descriptive `User-Agent`. `data/fetcher.py` assumes and enforces a rate limit of 5 requests per second (`rate_limit_per_sec=5`). Cost: Free.

## The smallest change routing the live pipeline through `tiers.py`
To route the live `data/providers/yfinance_adapter.py` pipeline through the tiered router with provenance:
1. Inside `YFinanceAdapter.fetch`, initialize `tiered_source = build_tiered_source(include_premium=True)`.
2. Replace the direct `info`-based lookups for `price` and `total_debt` with calls to `tiered_source.fetch_price(ticker, now)` and `tiered_source.fetch_debt(ticker, now)`.
3. Capture `tiered_source.audit_summary()` and attach it to the final `Security` object via the qualitative dictionary (e.g., `qualitative["data_provenance"] = tiered_source.audit_summary()`).
4. Fall back to the existing yfinance payload and math heuristics for the remainder of the unmapped `Fundamentals`.

## Recommendation
**FMP-first.** Building a complete historical financials pipeline strictly on SEC EDGAR is a massive time sink due to the fragility and inconsistencies of XBRL tag mapping (restatements, absent tags, varying GAAP definitions). Because `tiers.py` was purposely built to route requests elegantly, we should configure FMP as the primary `PREMIUM` source to fill the pipeline robustly, seamlessly degrading to SEC EDGAR or yfinance (`OFFICIAL`/`COMMUNITY` tiers) when a user does not configure an API key. This approach maintains zero-config usability while avoiding an unwieldy maintenance burden.

---

## Claude review of this memo (2026-10-02)

Written by AGY (A3). Claims spot-checked against the code:

- **Confirmed:** FMP implements only `fetch_price` and `fetch_debt` (`fmp_source.py:68,95`), although
  it declares `Capability.FUNDAMENTALS` (`:45`). EDGAR maps Revenue and NetIncome (`fetcher.py:201-202`)
  at 5 req/s (`fetcher.py:58`). `tiers.py` exposes `fetch_price`, `fetch_debt`, `audit_summary` and
  `build_tiered_source` (`:157,172,211,236`).
- **Correction to step 4 of "smallest change":** "fall back to the existing yfinance payload and
  math heuristics" must not reintroduce invented defaults. Unmapped fields stay `None` and show n/a
  (CLAUDE.md rule 1). The heuristics in `yfinance_adapter.py` are the defaults listed in HANDOFF item 3.
- **To verify before committing to FMP:** the client calls `financialmodelingprep.com/api/v3`
  (`fmp_source.py:27`). Check FMP's current docs for whether new keys still get v3 endpoints, and
  check pricing and rate limits (AGY marked these unverified).
- **Recommendation stands as AGY's.** FMP-first is reasonable for coverage. Note that it makes the
  full-fidelity path depend on a paid key, which cuts against the roadmap's "zero-configuration data
  layer" goal. The owner decides (FIX_PLAN Q1).
