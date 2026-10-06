# Recorded SEC EDGAR responses

Real responses, recorded once on **2026-10-06** with the User-Agent
`institutional-alpha research contact@example.com` (about 5 requests per second, well under
SEC's 10/second limit), then trimmed so the files stay small. Tests replay them through an
injected transport and never use the network.

| File | Source URL | Trimmed to |
|---|---|---|
| `companyfacts_AAPL.json` | `data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json` | facts filed 2009-06-01 or later (includes the FY2009 restatement) |
| `companyfacts_MSFT.json` | `.../CIK0000789019.json` | facts filed 2016-01-01 or later |
| `companyfacts_BLK_old.json` | `.../CIK0001364742.json` (now "BlackRock Finance, Inc.") | facts filed 2016-01-01 or later |
| `companyfacts_BLK_new.json` | `.../CIK0002012383.json` ("BlackRock, Inc.", ticker BLK) | facts filed 2024-01-01 or later |
| `submissions_*.json` | `data.sec.gov/submissions/CIK##########.json` | `cik, name, sic, sicDescription, tickers, exchanges, formerNames, fiscalYearEnd` (filing list dropped) |
| `company_tickers.json` | `www.sec.gov/files/company_tickers.json` | the entries for AAPL, MSFT, BLK, BLKB |

Trimming (values and metadata are untouched, rows are only removed):

* companyfacts keeps only the concepts the Phase A parser reads: `Revenues`,
  `RevenueFromContractWithCustomerExcludingAssessedTax`, `SalesRevenueNet`, `NetIncomeLoss`,
  `OperatingIncomeLoss`, `NetCashProvidedByUsedInOperatingActivities`,
  `PaymentsToAcquirePropertyPlantAndEquipment`, `LongTermDebt`, `LongTermDebtNoncurrent`,
  `LongTermDebtCurrent`, `DebtCurrent`, `CashAndCashEquivalentsAtCarryingValue`, `InterestExpense`,
  `IncomeTaxExpenseBenefit`, the two pretax-income tags, `StockholdersEquity`,
  `WeightedAverageNumberOfDilutedSharesOutstanding`, `dei:EntityCommonStockSharesOutstanding`, and
  `Liabilities` (kept so a test can prove it is never used as debt).
* Rows are limited to forms 10-K, 10-K/A, 10-KT, 10-Q and 10-Q/A filed on or after the date above.

Facts later than the recording date do not exist, so tests that need "as of" dates use dates up to
2026-06-30 (and older). Re-recording changes the latest facts, so expected values in
`tests/edgar/test_facts.py` are pinned to these files, not to live EDGAR.
