# Cost of Capital

This page documents how the pipeline sets discount rates. The method follows Damodaran's
cost-of-capital framework. Every input carries a source string, and a missing input produces
`None` or an explicit "insufficient data" state, never a silent default.

## Two costs of equity

The pipeline uses two different costs of equity on purpose. They answer different questions.

| Used by | Formula | Question answered |
|---|---|---|
| Stage 1, reverse DCF | Rf + regression beta x US ERP | What return does the market's consensus model require? |
| Stage 3 intrinsic DCF and the reference WACC | Rf + relevered industry beta x revenue-weighted ERP | What should this business earn, built bottom-up? |

The first is the "consensus" Ke. It mirrors how most market participants discount, so the
implied-expectations output is comparable with the market's own view. The second is the
"bottom-up" Ke and is the house view of fair value. The gap between the two valuations is
part of what Stage 4 triangulates.

## Components

### Risk-free rate

`DamodaranProvider.get_risk_free_rate_with_source()` (`src/iam/data/damodaran.py`) returns the
live 10-year US Treasury yield (`^TNX`). If no live quote is available it returns the documented
baseline constant `CURRENT_RISK_FREE_RATE` and labels the source as offline. Law 3 and every cost
of equity read Rf from this one place.

### Equity risk premium

- The consensus Ke uses the US ERP from the Damodaran dataset (April 2026: 5.03%).
- The bottom-up Ke uses a revenue-weighted ERP (`company_erp` in
  `src/iam/valuation/country_risk.py`).
  - Each country ERP is the average of the rating-based and CDS-based figures. When no CDS figure
    exists, the rating-based figure is used and the source string says so.
  - Regions (for example "Asia" or "Latin America") are GDP-weighted averages of their member
    countries.
  - The revenue mix is renormalised to sum to one before weighting.
  - Mix members the table cannot resolve stay in the mix and lower its reported coverage. ERP is
    weighted over the resolved part only.
  - With no revenue mix the function uses the country of domicile when the dataset knows it,
    otherwise the US ERP. The fallback is named in the returned source string.

### Beta

`GroundTruthProvider.get_equity_risk_profile` (`src/iam/data/ground_truth.py`) builds the
bottom-up profile:

1. Take Rf and its source.
2. Take the revenue-weighted ERP and its source.
3. Look up the Damodaran unlevered beta for the company's industry.
4. Relever at the current market D/E (total debt over market capitalisation):
   `levered = unlevered x (1 + (1 - t) x D/E)`, with `t` the marginal tax rate.
5. Ke = Rf + levered beta x ERP.

If the industry beta or the capital structure is unavailable, the method returns no profile and
a reason string rather than substituting a number.

### Tax

| Rate | Source | Used for |
|---|---|---|
| Marginal | Damodaran country statutory rates, weighted by revenue mix (`company_marginal_tax` in `src/iam/valuation/country_tax.py`). The US rate is 25%. | Relevering beta; after-tax cost of debt |
| Effective | `Fundamentals.effective_tax_rate` | Multiples regression |

Marginal-tax regions are GDP-weighted in the same way as ERP.

### Terminal growth

Terminal growth is capped at Rf in every DCF engine (`cap_terminal_growth` in
`src/iam/valuation/reverse_dcf.py`). The cap never raises a lower configured rate. When it binds,
a note is attached to the result.

## Revenue mix

For live tickers, `Security.revenue_mix` comes from the geographic revenue disclosed in the latest
10-K (`src/iam/data/edgar/geography.py`). The origin is recorded in
`qualitative["revenue_mix_source"]`. Company-specific members that cannot be resolved to a country
or region (for example "Other countries") are kept and reduce coverage. Without a 10-K mix the
pipeline falls back to the US ERP and US tax rate. Backtest snapshots do not yet use the 10-K mix;
see [the backtest status](../research/backtest.md).

## Reference data

Damodaran's country tables live in `src/iam/data/reference/`:

| File | Content |
|---|---|
| `country_erp_2026-04.json` | Country and regional ERP, April 2026 update (default) |
| `country_tax_2026-04.json` | Country marginal tax rates |
| `country_erp_2026-01.json` | January 2026 ERP table, kept so older valuations can be reproduced |

The newest dated file is the default. Override with `IAM_COUNTRY_ERP_FILE` and
`IAM_COUNTRY_TAX_FILE`. Refresh the files after Damodaran's January and July updates. See
[data sources](../data-sources.md).

## Reference check

Worked example for a BlackRock-like profile (April 2026 reference data):

| Quantity | Value |
|---|---|
| Consensus Ke | 10.84% |
| Revenue-weighted ERP | 5.44% |
| Relevered beta | 0.691 |
| Bottom-up Ke | 8.06% |

Related tests: `tests/test_country_erp_2026_04.py` (ERP), `tests/test_country_tax.py` and
`tests/test_gui_ke_card.py` (relevered beta).
