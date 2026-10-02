# Fix Plan

**Status:** DRAFT. Waiting for owner approval. No source code changes until this plan is approved.
**Branch for this plan:** `claude/adoring-fermat-rvbidx`
**Baseline (2026-10-02):** `pytest --benchmark-disable`: 1165 passed, 2 skipped, 2 failed.
Both failures are `tests/performance/test_benchmarks.py` tests that need the benchmark fixture
enabled. With benchmarks on, `tests/test_data_fetcher.py::TestPerformance::test_serial_fetches_speed`
fails because it makes live network fetches (~18 s). None of these are caused by the issues below.

> Note: the takeover prompt this plan was meant to come from (`docs/ops/fix-plan-prompt.md`)
> was never committed to the repo. This plan was rebuilt from the summary of that prompt and the
> AGY review, and every finding below was checked against the code on this branch.

---

## Ground rules (apply to every workstream)

1. **No made-up numbers.** If an input is missing, the UI says "n/a / insufficient data". It never
   shows a plausible-looking default. Every `or 0.20`-style fallback that reaches a displayed
   number is a bug.
2. **Every fix ships with a test** that fails before the fix and passes after it.
3. **One branch per workstream** (`fix/ws1-battlefield`, `fix/ws2-ti89`, ...), each its own PR.
4. **Nothing is pushed without the owner's OK** (this plan doc excepted).
5. **AGY reviews, it does not build.** AGY critiques this plan and each finished PR diff. It never
   edits the same files Claude Code is editing. Where AGY and Claude disagree, both positions are
   written into this doc and the owner decides.
6. **Model tiering.** The top tier plans, reviews and resolves disagreements. The mid tier
   implements workstreams in parallel. The fast tier does searches, grep-sweeps and mechanical
   cleanup. Check which models are actually available before assigning any of them.

---

## Verified findings

| # | Finding | Verdict | Evidence |
|---|---------|---------|----------|
| F1 | Valuation Battlefield runs on hardcoded scenario weights; the real calculation exists but is never connected | **Confirmed** | `src/iam/pipeline/orchestrator.py:555-588` |
| F2 | TUI "3D graph" is a fixed ASCII picture with three numbers pasted in | **Confirmed** (GUI version is also synthetic) | `src/iam/ui/ti89_graph.py:15-31`, `:39-45` |
| F3 | Thesis drift applies Apple's settings to every stock | **Partly wrong.** It falls back to the *same ticker's* `.example.yml`, which is still a problem | `src/iam/pipeline/orchestrator.py:596-598` |
| F4 | Missing `hypothesis` crashes the tests | **Not a bug.** It is declared in `[project.optional-dependencies].test` (`pyproject.toml:61`) and installs with `pip install -e ".[test]"` | — |

### F1 detail: Battlefield
- Stage 4b builds both scenario distributions by hand:
  - Probabilities are fixed: 0.20/0.60/0.20 intrinsic and 0.20/0.50/0.30 market.
  - Bear/bull cases are fixed multipliers of the base case (×0.6/×1.3 growth, ×0.9/×1.1 margin, and so on).
- It also invents inputs when they are missing:
  - `high_growth` defaults to 0.08, `roe` to 0.15, and operating margin to 0.20.
  - Market margin is copied from intrinsic margin (`mkt_m = int_m`), so the margin gap is always
    zero by construction, and "Margin" can never be the primary disagreement.
- These invented numbers feed the CLI (`ui/cli.py:274-294`), TUI (`ui/research_panels.py:33-111`)
  and GUI (`ui/gui.py:328-383`) panels.
- The honest replacement already exists and is tested, but nothing in `src/` calls it:
  - `src/iam/pipeline/battlefield.py` runs a ceteris-paribus swap attribution through `build_battlefield(...)`
    and `rows_from_scenario_matrix(...)`.
  - It is covered by `tests/test_battlefield.py` and `tests/test_phase2.py`.
  - It skips missing parameters instead of faking them.
  - It takes real scenario probabilities from `ScenarioMatrix`.

### F2 detail: TI-89 projection
- The TUI mode returns a hardcoded ASCII drawing; only three `%` labels change.
- The GUI mode draws `z = a·u² + b·v² + c·uv` from the same three numbers. That shape has no
  valuation meaning.
- Both callers (`ui/alpha_terminal.py:1657-1666`, `ui/gui.py:433-442`) substitute `0` for missing
  inputs, so a missing lens shows as a real-looking "0.00%".
- A real surface already exists: `valuation/sensitivity.py` produces a growth × discount-rate value
  grid (with topology stats already used in `research_panels.py:194-198`), and `ui/terrain.py` /
  `ui/surface.py` render it.

### F3 detail: Thesis drift
- Only `data/constraints/MSFT.example.yml` exists. For MSFT, the *illustrative* example thresholds
  (ROIC ≥ 15%, op-margin ≥ 35%, ...) are used as if they were the owner's real thesis, with no label
  saying so. Every other ticker silently gets no drift report.
- The path is relative to the current working directory (`Path("data/constraints")`), so drift
  silently disappears when the app is launched from another folder (desktop shortcut,
  PyInstaller build).

---

## Workstreams

### WS1: Connect the real Battlefield (F1). Priority: P0
**Tier:** mid-tier implementer, top-tier review.
1. In `orchestrator.py` Stage 4b, replace the hand-built `ScenarioDistribution`s with
   `build_battlefield(market_implied=..., intrinsic=..., value_fn=..., triangulation=triangulation_res)`.
   `value_fn` is a closure over the production FCFE engine. Fall back to `two_stage_fcfe_value` only if the FCFE engine
   can't be called with a `ParamVector`, and label it in `notes` when it does.
2. When the thesis has a `ScenarioMatrix`, attach `rows_from_scenario_matrix(...)` output. Those
   probabilities replace the fixed 20/60/20.
3. Change `PipelineReport.battlefield` to the new `BattlefieldAttribution` type. Update the three
   renderers (CLI, TUI panel, GUI) and `PipelineReport.summary()/explain()`.
4. Decide what happens to the old `valuation/expectations_battlefield.py`: delete it, or keep only
   the overlap/alignment maths if the owner wants those scores. **Open question Q3.**

**Tests:**
- An orchestrator test where `high_growth` is missing: the battlefield excludes growth and does
  not show 8%.
- A regression test that a `verdict == "agree"` triangulation yields `key_disagreement` "NONE".
  The module docstring asks for this test, but it does not exist yet.
- A renderer smoke test for each of the three UIs using the new type.

### WS2: Replace the fake TI-89 projection (F2). Priority: P1
**Tier:** mid tier.
1. Drive both TUI and GUI from the existing sensitivity grid (`valuation/sensitivity.py`), plotting
   value vs growth × discount rate with the current point marked. Keep the TI-89 monochrome
   look in both.
2. Missing inputs render "n/a", never 0.
3. If the owner prefers to drop the panel instead of rebuilding it, delete `ti89_graph.py` and the two
   call sites. **Open question Q4.**

**Tests:** the same inputs give a surface whose values match `sensitivity.py`. A missing lens gives "n/a".

### WS3: Make thesis drift honest (F3). Priority: P1
**Tier:** mid tier.
1. Resolve `data/constraints` from the project/config root, not the CWD.
2. When only `<TICKER>.example.yml` exists, still run drift but mark the report
   `source="example"` and show "EXAMPLE THRESHOLDS — not your thesis" in all three UIs.
   **Alternative:** never use example files at runtime. **Open question Q5.**
3. When no file exists, the UIs say "No thesis constraints defined for X". They don't just leave
   the panel empty.

**Tests:** drift works from a different CWD. Example-file reports carry the flag. A missing file
gives an explicit message.

### WS4: Remove invented defaults that reach the screen. Priority: P1
**Tier:** a fast-tier sweep, then a mid-tier fix.
Candidates found so far (sweep for more):
- `valuation/profile_builder.py:140,148-149` (`or 0.10`, `or 0.12`)
- `pipeline/macro.py:158-167` (0.09 / 0.08 / 0.025)
- `ui/menu.py:158-159`
- `ui/gui.py:263`

For each one, decide whether it is a *documented model assumption*, which stays but must be shown
as an assumption with its source, or a *silent fill*, which is removed and shown as missing.
Write the classification table into this doc before changing code.

**Tests:** for each removed silent fill, the missing value surfaces as missing.

## WS4 classification

Line numbers are for the code before the WS4 fix. "Documented assumption" means the value stays
but must be shown with its source. "Silent fill" means a made-up number that looked like data.

| File:line | Value | What it feeds | Classification | Action |
|---|---|---|---|---|
| `valuation/profile_builder.py:140` | `operating_margin or 0.10` | `CompanyProfile.op_margin`, cyclical fade and confidence grade (a real 0% margin also became 10%) | Silent fill | Use the reported value (0 is kept). If missing, the sector baseline stands in and `BuiltCompanyProfile.missing_inputs` says so |
| `valuation/profile_builder.py:148` | `roe ... or 0.12` | `CompanyProfile.roe` | Silent fill | Now `None` when no ROIC history or incremental ROIC; listed in `missing_inputs` |
| `valuation/profile_builder.py:149` | `roic ... or 0.10` | `CompanyProfile.roic` | Silent fill | Same as above |
| `valuation/profile_builder.py:151` | `op_margin * 0.9` mid-cycle margin | cyclical fade | Documented heuristic | Kept; now listed in `missing_inputs` when used |
| `valuation/profile_builder.py:192-193` | `wacc=0.09`, `terminal_growth=0.025` | reverse-DCF growth estimate | Documented assumption (duplicate literal of `FCFEAssumptions`) | Reads `FCFEAssumptions` defaults instead of literals |
| `pipeline/macro.py:158-159,167` | 0.09 / 0.08 / 0.025 | base case for the macro stress DCF | Documented assumption, but shown nowhere and not equal to what the unstressed DCF used (`forecast_roe`, years ignored) | Base case now comes from `FCFEDCF._resolve_assumptions`; when any of the three keys is missing the result gets "model-default" note and confidence x0.7, as the unstressed DCF does |
| `ui/menu.py:158-159` | `wacc_override` default 0.09, terminal 0.025 | pre-run assumption table (and it went to `logger.info`, so it was not even on screen) | Silent fill for WACC (the real WACC is computed inside the run); documented assumption for terminal growth | Menu prints its own table: WACC "computed by the pipeline" unless supplied; every row labelled user input / supplied / model default |
| `ui/menu.py:143,153` | growth default 8% | menu growth prompt | Documented assumption | Reads `FCFEDCF().defaults.high_growth`; also resets to the default when validation rejects the input |
| `ui/gui.py:263` | `discount_rate` default 0.09 | "Discount Rate (WACC)" card | Silent fill | Shows the intrinsic stage's real rate (FCFE discount rate or SOTP cost of equity), else "n/a" |
| `pipeline/orchestrator.py` SOTP `assumptions` | `high_growth` 0.08, `roe` 0.15 | `PipelineReport.intrinsic.assumptions`, then Damodaran laws and the battlefield vector; SOTP never used them | Silent fill | Removed. Readers already treat missing keys as "not applicable" (`intrinsic_vector_from_assumptions`, laws, `build_value_grid`) |
| `pipeline/orchestrator.py` SOTP `tax_rate` | 0.21 | SOTP levered beta / cost of equity | Documented assumption (US statutory federal rate) | Uses `qualitative["tax_rate"]` if supplied; the SOTP notes now say "supplied" or "model default" |
| `valuation/beta.py:98` | tax 0.21 | unlever / relever beta, CAPM discount rate | Documented assumption | Named constant `DEFAULT_TAX_RATE`; use recorded in `qualitative["beta_assumptions"]` |
| `valuation/beta.py:107` | cost of debt 7.5% | market value of debt, relevered beta | Documented assumption (no debt quote is fetched) | Named constant; use recorded in `beta_assumptions` |
| `valuation/beta.py:108` | maturity 5y | market value of debt | Documented assumption | Named constant; recorded |
| `valuation/beta.py:~70` | beta 1.0 when no beta | stage 3 beta | Documented assumption (market-neutral) | Named constant; recorded |
| `valuation/beta.py:113` | `market_cap or 1.0` | current D/E (gave D/E in the hundreds when cap missing) | Silent fill | Removed. Without a market cap the regression beta is returned unrelevered and the note says so |
| `valuation/fcfe_dcf.py` `FCFEAssumptions` | 8% growth, 2.5% terminal, 9% rate, 15% ROE, 10y | FCFE DCF base case | Documented assumption | Left as is. It already notes "Using model defaults" and cuts confidence |

Found but left alone (outside WS4 scope or owned elsewhere):
- `pipeline/orchestrator.py` `_calculate_dynamic_wacc`: `ke=0.09`, `rf=0.043`, `tax_rate=0.21` feed the dynamic WACC. Needs its own fix (use the live risk-free rate and CAPM cost of equity).
- `ui/gui.py` `pwev_target` falls back to `$0.00` when there is no intrinsic result. Should read "n/a".
- `data/providers/yfinance_adapter.py:340-358`: `or 0.15`, `or 0.12`, `or 0.10`, `or 0.21` fills for margin/ROE/ROIC/tax.
- `valuation/probabilistic_growth.py:656` (`reinvestment_rate or 0.60`), `lenses/*` and `valuation/sensitivity.py` / `expectations_surface.py` (`forecast_growth` default 0.08 / 0.12), `engine/damodaran.py:98` (tax 0.21), `portfolio/verdicts.py` (volatility 0.15, correlation 0.3), `validation/ground_truth.py:44` (IC 0.02).
- `ui/alpha_terminal.py`, `ui/state.py`, `ui/research_panels.py`, `pipeline/battlefield.py`: owned by other workstreams.

### WS5: Historical financials data source. Priority: P2. Needs a decision first
- Both sources already exist:
  - `backtest/sources/fmp_source.py` and `backtest/sources/sec_edgar_source.py`, routed by `backtest/sources/tiers.py`.
  - The live fetcher `data/fetcher.py` has its own `SecEdgarSource`.
- The work is **routing the live pipeline** through the tiered router, not building a new client.
- **Disagreement (Q1):**
  - **AGY:** building on SEC EDGAR is a time sink (XBRL tag mapping, restatements).
  - **Proposal:** use FMP as the primary source for the live pipeline, with EDGAR as the free fallback
    when no FMP key is configured. Both answers record provenance through `tiers.py`.
  - FMP is a paid key for full history, so this is the owner's call.

### WS6: Consolidate the text-mode front-ends. Priority: P3. Do last
Current text front-ends:
1. `launcher.py` (rich menu, the `institutional-alpha` entry point)
2. `ui/menu.py` (`iam-menu`)
3. `ia_shell.py` (cmd shell)
4. `ui/alpha_terminal.py` (full-screen TUI, `iam-terminal` / `launch_tui.py`)

Also present:
- `ui/modern_terminal.py` and `ui/institutional_terminal.py` are print-only renderers. Their
  `__main__` blocks hold hardcoded sample numbers (BLK $1070.34, +57%, and so on).
- `examples/modern_terminal_example.py` is their only caller.

**Disagreement (Q2), largely resolved:**
- **AGY:** keep the GUI (Streamlit) and TUI separate. Agreed.
- **Proposal:** merge only the four text-mode entry points into one (`launcher.py` as the shell, with
  the menu, shell and TUI as its modes), and retire the sample-data renderers.
- This touches many files that WS1–WS3 also touch, so it goes **after** them to avoid conflicts.

---

## Order and parallelism

```
WS1 ─┐
WS3 ─┼─(parallel, separate files except PipelineReport: WS1 owns orchestrator.py, WS3 rebases)
WS2 ─┘
WS4 sweep can start immediately (read-only); its fixes land after WS1.
WS5 waits on Q1. WS6 waits on WS1–WS4 merging.
```

Each PR goes through these review gates in order:
1. Repo checks (`make lint`, `make typecheck`, `pytest`)
2. Top-tier self-review
3. AGY review of the diff
4. Owner approval before push

## Open questions for the owner

- **Q1:** FMP-first (paid key) or EDGAR-first (free) for live historical financials?
- **Q2:** OK to merge the four text front-ends into `launcher.py` and delete the sample-data renderers?
- **Q3:** Keep the old battlefield's alignment/mismatch 0–100 scores, or drop them with the old engine?
- **Q4:** Rebuild the TI-89 panel on the real sensitivity surface, or remove it?
- **Q5:** Should `.example.yml` constraint files ever be used at runtime (clearly labelled), or never?

## AGY review

_To be filled in by AGY: a critique of this plan, plus any disagreements it raises, recorded
alongside Claude's position._
