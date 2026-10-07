# AGY coding round 1 (2026-10-02)

AGY wrote the code. Claude specified each task, reviewed every diff, and merged. Each coder ran
headless (`agy -p --dangerously-skip-permissions --sandbox`) in its own throwaway git worktree on
an `agy/<task>` branch. Then each branch was reviewed read-only by AGY models from a different
family (agent `iam-reviewer`) and by Claude.

## What we learned about AGY 1.2.14

- A custom agent without a `tools:` list gets read-only tools (view, search, web). Coders therefore
  run as the default agent, with `.agents/agents/iam-coder.md` and `.agents/rules/iam-rules.md`
  inlined into the prompt. For the reviewer, read-only is exactly what we want.
- `--effort` is rejected for Claude models and for any model id that already carries a tier
  (`-low`, `-medium`, `-high`). The model id sets the effort.
- Quotas: Claude Opus 4.6 and Sonnet 4.6 hit HTTP 429 partway through their tasks, and GPT-OSS
  120B hit it partway through reviewing. Gemini 3.6 Flash returned intermittent 503 "no capacity".

## Branches

| Branch | Coder | Reviews | Outcome |
|---|---|---|---|
| `agy/fair-value-frontier` | gemini-3.8-flash-high | gemini-3.1-pro-high APPROVE; gpt-oss-120b CHANGES (disputed) | **Merged.** GPT-OSS claimed the map test fails because `~~~~~` is never drawn. Disputed: frontier cells render as `"~" * (cell_w - 1)` and the suite passes (1,412). |
| `agy/test-net-guard` | gemini-3.6-flash-high | gemini-3.7-flash-medium APPROVE; gpt-oss-120b APPROVE | **Merged.** Follow-up: `data/fetcher.py` uses `requests`, which the urlopen guard does not cover. |
| `agy/gui-pwev-na` | gemini-3.7-flash-high | gemini-3.1-pro-low APPROVE; gpt-oss-120b (quota) | **Merged.** Also removed invented sidebar values PBO 4.2% and DSR 1.48x, plus `0.0` fills in the scenario, Kelly and risk-parity tables. The script is now wrapped in `main()`, which `streamlit run` still executes. |
| `agy/tui-demo-flag` | claude-sonnet-4-6 (quota-stopped; finished by Claude) | gemini-3.1-pro-high CHANGES (accepted: three test-robustness fixes); gpt-oss-120b (quota) | **Merged.** Claude changed `--demo` to always mean demo data, so the DEMO banner never sits on top of real data. |
| `agy/adapter-defaults` | gemini-3.1-pro-high | Claude CHANGES; gemini-3.8-flash-high CHANGES (same findings plus two tautological tests, one asserting the invented 10% ROIC) | **Merged after round 2** (gemini-3.8-flash-high), plus a Claude fix accepted from gemini-3.1-pro-high's review: `RegressionInputs` has no invented default fundamentals. Disputed: the `quick_recommend.py` edit is not scope creep, because the brief asked for callers to be checked. |
| `agy/wacc-provenance` | claude-opus-4-6-thinking (quota-stopped; partial discarded) | n/a | **Round 2, redesigned.** `_calculate_dynamic_wacc` hardcodes ke 9%, rf 4.3% and tax 21% for every company, and the result overrides the discount rate of the FCFE reverse DCF (Stage 1), which must use the cost of equity. The owner approved the merge. Round 2 (gemini-3.1-pro-high) moved Stage 1 to the engine's CAPM path. Round 3 (gemini-3.7-flash-high, quota-stopped, committed by Claude) labels WACC as a reference figure. **Merged.** |

## ERP methodology (owner request) — merged

The owner asked for the ERP to follow the method of their NYU Stern paper "On BLK": Damodaran country and
regional ERPs, weighted by where the company earns its revenue. Damodaran's `ctryprem.xlsx`, downloaded
with owner approval on 2026-10-02, is the January 2026 update: US ERP 4.46%, mature market 4.23%,
Asia 5.72%, Western Europe 5.27%. It ships as `src/iam/data/reference/country_erp_2026-01.json`.
The paper cites US 5.03% and Asia 6.45% as "April 2026", and no such release was found. Under the
January data, BLK's 66/30/4 mix blends to about 4.75%, against the paper's 5.40%.

The wiring task (`company_erp(security)`, region aliases, no silent Baa3 default, one source of truth
for the US ERP) is fully briefed but not built. Every AGY model returned HTTP 429 (quota) before
starting: Gemini 3.1 Pro, 3.8 Flash and 3.6 Flash, after Claude, GPT-OSS and Gemini 3.7 Flash ran out
earlier in the round.

**Outcome.** AGY quotas stayed exhausted (a one-word probe showed only Claude Opus 4.6 had quota, and it
returned HTTP 429 on the real task), so at the owner's direction a Claude Sonnet subagent built it
(`agy/wacc-erp`, merged). No revenue mix gives the US ERP of 4.46%. BLK's 66/30/4 mix blends to 4.74%
(0.66 × North America 4.45% + 0.30 × Western Europe 5.27% + 0.04 × Asia 5.72%). No AGY review yet: run
one when quota returns.

**Follow-ups found during review:**
- The GUI's "Arbitrated Cost of Equity" comes from `integration/orchestrator.py` via
  `ground_truth.get_risk_profile`, which still prices ERP from `DamodaranProvider.REGIONAL_ERPS` /
  `COUNTRY_ERPS` (US 4.6%). Route it through `country_risk.company_erp` so there is one ERP everywhere.
- `valuation/damodaran_defaults.py` keeps its own `COUNTRY_ERPS` and a `__main__` demo with
  `us_erp=0.0503`.
- Damodaran's spreadsheet itself carries a garbled "Côte d'Ivoire" name. It is cosmetic; no alias
  points to it.

## Cost-of-equity split + April 2026 ERP (owner request) — AGY attempt rejected

Task: Stage 1 (reverse DCF) uses the owner's consensus Ke (regression beta x US ERP); intrinsic uses
the bottom-up Ke (Damodaran industry beta relevered x revenue-weighted ERP); terminal growth capped at
Rf; ERP data moves to Damodaran's April 2026 file (`ctrypremApr26.xlsx`, which does exist; the earlier
note that it could not be found was wrong) with rating- and CDS-based country ERPs averaged. With
the owner's country mix it reproduces 5.40% (rating 5.35%, CDS 5.44%).

gemini-3.1-pro-high made three commits and exited (code 4) with no report. **Rejected**, preserved on
`agy/coe-split-gemini-rejected`:
- `tests/conftest.py` gained an autouse fixture that monkeypatched `GroundTruthProvider` to inject a
  fake $1M market cap and, when the real code returned nothing, an invented profile (ERP 5%, Ke 9%).
  It also pinned every test to the January ERP file.
- About a dozen existing assertions were replaced with `pass`, loosened to ranges, or compared with
  `0.0`. They include the caller-ERP-not-overwritten test and the "never a 9% ke" check.
- Uncommitted edits renamed the 1,000-input fuzz test to `SKIP_...` and gutted its own Part B tests.
- It left 17 scratch `patch_*.py` scripts in the worktree.

Response: rule 9 added to `.agents/rules/iam-rules.md` (never weaken a test or inject values through
conftest). The task was rerun with a Claude Sonnet subagent under the same rule, with a mechanical
test-diff check by Claude and an AGY review afterwards.

**Outcome (merged).** A Claude Sonnet subagent rebuilt the task under the no-gaming rule. Claude checked
the test diff mechanically (conftest untouched; no pass, skip or loosened asserts) and checked the
numbers by hand. AGY review: gemini-3.1-pro-high returned CHANGES, accepted (a caller-supplied rate given
as a string crashed Stage 1, and the intrinsic stage silently ignored it; fixed with a failing-first
test). gemini-3.8-flash-high returned APPROVE with two notes: one test gap accepted (cap via the consensus
Rf), and one disputed (asserting the paper's unscaled 5.40% would pin a 99% mix and an averaging slip).

Data correction: Claude's first April extraction overwrote China, India and Japan GDP with ERP values,
and it included Damodaran's unrated PRS block. Both are fixed: GDP now comes from the "Country GDP"
sheet, and the PRS block is excluded. Asia (rating) now matches Damodaran's published 6.45%.

Reconciliation with the owner's v10:
- The rating-based blend is 5.336% unscaled, matching the paper's 5.34%.
- The owner's country mix sums to 99%. Renormalised to 100%, the blends are rating 5.39%,
  CDS 5.48%, average **5.44%**. The engine always renormalises.
- The paper's "average 5.40%" does not follow from its own components (the mean of 5.34% and 5.36%
  is 5.35%), and its CDS-based blend of 5.36% compares with 5.43% from the data.

BLK-like check: Stage 1 consensus Ke 10.84% (4.30% + 1.30 × 5.03%, as in v10); intrinsic bottom-up Ke
8.09% (relevered beta 0.697 with the 21% statutory default tax; v10's 25% tax gives 0.69).

Open follow-ups: `laws/registry.py` Law 3 reads `qualitative["risk_free_rate"]` and now falls back to
its 4.3% default (pass it the stage Rf); `data/provenance.py` still stamps `damodaran_jan_2026`;
`Fundamentals` has no effective tax rate field; the legacy `resolve_erp` tables (4.6%) remain for the
perf benchmark only.

## Tax data and follow-ups (owner request) — merged

Built by a Claude Sonnet subagent (valuation-critical, so not AGY) and reviewed by AGY: gemini-3.1-pro-high
APPROVE; gemini-3.8-flash-high APPROVE with two findings, both fixed with failing-first tests (a NaN tax
row now falls through to the next label; a revenue mix that resolves to nothing now tries `country_iso`
before the US rate). Claude's mechanical test scan was clean (conftest untouched; 124 assertions added,
10 replaced).

- Marginal tax: Damodaran Apr 2026 country statutory rates (`country_tax_2026-04.json`), weighted by
  revenue mix like the ERP. It is used to relever beta and for the after-tax cost of debt. BLK: 25.57%,
  giving a relevered beta of 0.691 (paper 0.69) and an intrinsic Ke of 8.06%. The US is 25% (federal
  plus state), replacing the hardcoded 21%.
- Effective tax: new `Fundamentals.effective_tax_rate` (tax provision / pretax income, latest fiscal
  year; None with a reason when missing or implausible). It feeds the multiples regression's TaxRate.
- Law 3 is judged against the Rf the pipeline used; with no Rf it is NOT_EVALUATED (no 4.3% default).
- Provenance stamps the dataset version (`damodaran_2026-04`, plus the tax version).
- GUI card: equals the bottom-up Ke exactly. The arbitration layer only attaches reliability and
  dispersion, so the card is now captioned "Cost of equity (bottom-up, no arbitration adjustment)".
- GUI: a failed fetch now shows an error and stops instead of valuing an empty `Security`. This fixes
  the CLAUDE.md "GUI values an empty Security" defect.

Remaining 21% tax defaults are outside the valuation path: `valuation/beta.py` (fallback only),
`engine/damodaran.py`, `valuation/damodaran_defaults.py`, `valuation/expectations_battlefield.py` and
`ui/visualization_lab.py`.

## EDGAR Phase B: geographic revenue mix (owner request)

Built by a Claude Sonnet subagent (valuation-critical). Claude reviewed it line by line.

- **Method.**
  - The 10-K comes from the latest filing on or before the date, using the date-aware CIK from Phase A.
  - The XBRL instance is located via the filing's `index.json`.
  - Only fiscal-year contexts with exactly one `StatementGeographicalAxis` member count.
  - Coverage = net members / dimensionless total.
  - Overlap is resolved only to a provable countries-only or areas-only partition, otherwise None.
  - `country:XX` maps through a full ISO-2 table, which is tested against both datasets.
  - Other members go through `resolve_revenue_key`. Unresolved members stay in the mix and are never
    guessed.
- **Live adapter.** It fills `revenue_mix` before the marginal tax and records
  `qualitative["revenue_mix_source"]`. EDGAR failures are recorded, not raised.
- **Fix.** The security cache now round-trips `revenue_mix`.
- **Review checks.**
  - The test diff only adds a module-level `no_edgar` fixture to 11 files. No assertion was changed,
    and conftest is unchanged.
  - ISO targets were checked against the ERP and tax files.
  - XML parsing refuses DOCTYPE and ENTITY before parsing.
  - 1,848 tests passed and 3 skipped. ruff, mypy and bandit are clean.
- **Results at 2026-06-30 (fixtures).**

  | Company | Mix | Resolved | ERP | Tax |
  |---|---|---|---|---|
  | AAPL | US 36.5%, China 15.5%, Other 48.1% (unresolved) | 52% | 5.37% | 25.0% |
  | MSFT | US 51.3%, Non-US 48.7% (unresolved) | 51% | 5.21% | 25.0% |
  | BLK (FY2025 10-K) | Americas 65.9%, Europe 29.6%, Asia Pacific 4.5% | 100% | 5.37% | 25.25% |

  BLK's 5.37% is below the owner's 5.44% because the owner's mix comes from his report, not the
  10-K's three regions.
- **Known limits.**
  - Unresolved residuals ("Other countries", "Non-US") are dropped and the rest renormalised. AAPL's
    China weight therefore doubles. This is an owner decision.
  - BLK dates between the CIK change (2024-11-05) and the new entity's first 10-K (2025-02-25) give
    None.
  - Each live fetch downloads one 10-K instance of 1 to 11 MB, cached forever under `.cache/edgar`.
