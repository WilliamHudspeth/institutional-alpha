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
