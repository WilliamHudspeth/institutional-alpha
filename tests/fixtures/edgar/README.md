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

* companyfacts keeps only the concepts the facts parser reads: `Revenues`,
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

## Geographic revenue mix (10-K XBRL instances)

Recorded on **2026-10-06** with the same User-Agent and rate (about 5 requests per second).
Real SEC responses, trimmed; values are untouched.

| File | Source | Trimmed to |
|---|---|---|
| `submissions_filings_{AAPL,MSFT,BLK_new,BLK_old}.json` | `data.sec.gov/submissions/CIK##########.json` | `cik`, `name`, `filings.recent` reduced to forms 10-K and 10-K/A with the columns `accessionNumber, filingDate, reportDate, form, primaryDocument`, `filings.files` (`name, filingFrom, filingTo, filingCount`) and a `recent_window` note (the date span and count of the untrimmed `recent` arrays, for reference only; the code does not read it) |
| `submissions_page_BLK_old_{006,007}.json`, `submissions_page_BLK_new_{001,002}.json` | `data.sec.gov/submissions/CIK##########-submissions-NNN.json` (older-filings pages) | the same five columns, forms 10-K and 10-K/A only. These hold BlackRock's FY2019, FY2020 (old CIK) and FY2024 (new CIK) 10-Ks, which are outside `filings.recent` |
| `index_<tag>.json` | `www.sec.gov/Archives/edgar/data/<cik>/<accn>/index.json` | `.xml` and `.xsd` entries (name, type, size) |
| `instance_<tag>.xml` | the inline-XBRL extracted instance named in that index (`<doc>_htm.xml`, 1.4 to 10.8 MB untrimmed) | see below |

Tags and filings: `AAPL_2025` (CIK 320193, 0000320193-25-000079, FY ended 2025-09-27),
`MSFT_2025` (789019, 0000950170-25-100235, FY ended 2025-06-30), `BLK_new_2025`
(2012383, 0001193125-26-071966, FY2025) and `BLK_new_2024` (2012383, 0000950170-25-026584, FY2024),
`BLK_old_2019` (1364742, 0001564590-20-007807, FY2019) and `BLK_old_2020`
(1364742, 0001564590-21-008796, FY2020).

Instance trimming: the document keeps its XML declaration and root element (so every namespace
prefix still resolves), then only (a) the revenue facts the parser reads (`us-gaap:Revenues`,
`RevenueFromContractWithCustomerExcludingAssessedTax`, `SalesRevenueNet`,
`RevenuesExcludingInterestAndDividends`) that are dimensionless or sit on
`StatementGeographicalAxis` (all periods, so prior-year and quarterly comparatives stay as test
inputs), (b) `dei:DocumentType`, `DocumentPeriodEndDate` and `AmendmentFlag`, and (c) the contexts
and units those facts reference. Each file is 10 to 16 KB. Facts on product or segment axes are
dropped; the second-dimension, overlap, elimination, duplicate and 10-K/A cases are covered by
the synthetic instance builder in `tests/edgar/geo_helpers.py` (numbers hand-written in the tests,
no filing behind them).

What the recordings show (used by `tests/edgar/test_geography.py`): AAPL reports `country:US`,
`country:CN` and the company member `aapl:OtherCountriesMember`; MSFT reports `country:US` and
`us-gaap:NonUsMember`; BlackRock reports `srt:AmericasMember`, `srt:EuropeMember` and
`srt:AsiaPacificMember`, tagged on `RevenueFromContractWithCustomerExcludingAssessedTax` in
FY2024 and later and on `RevenuesExcludingInterestAndDividends` in FY2019 and FY2020. No recorded
filer reports both countries and the region containing them, so the overlap tests are synthetic.
