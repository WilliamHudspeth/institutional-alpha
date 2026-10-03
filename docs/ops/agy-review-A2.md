# AGY review A2

The merged commits for TUI de-fabrication and the WS4 defaults sweep have been thoroughly reviewed against the codebase. The WS4 defaults sweep successfully eliminated the hardcoded fallback values for margins, ROE, WACC, and growth across `valuation/profile_builder.py`, `pipeline/macro.py`, and the frontends, properly bubbling up missing data to the user. The TUI de-fabrication replaced the mocked terminal UI data with real price histories, real factor exposures, and an explicit error state, securely gating the offline mock data behind the `_IAM_CORE` check. All six A1 integrity checks hold true against the current codebase, ensuring models are honest about data limitations and accurate in their math.

| Severity (blocker/major/minor) | File:line | Finding | Suggested fix |
|---|---|---|---|
| minor | `src/iam/ui/alpha_terminal.py:2241` | The mock data generator (`_MockSec`, `_MockScore`) remains in the codebase as a fallback when `iam` packages aren't available. | Leave as-is (serves as a demo build feature), or completely excise the mock classes if strict zero-fabrication is required across all builds. |

**TUI de-fabrication (commits d09934a, 89b0888 / merged as deba15a, 333c1b3):**
- Replaced mock price history and quotes with `_real_history` and `_tick_prices` using `MKT._fetch_one`.
- Implemented an honest error state: if `_IAM_CORE` is true (real institutional build), load failures leave fields empty and surface the exact error instead of faking data.
- The `alpha_terminal.py` UI successfully handles `None` values by printing "n/a" cleanly without defaulting to $0.00 or 0.00%.

**WS4 defaults sweep (commit 989e6d0 / merged as bd1370e):**
- `valuation/profile_builder.py`: Verified that `operating_margin` safely defaults to the sector median while flagging it in `missing_inputs`, instead of returning a hardcoded `0.10`. `roe` and `roic` now safely propagate `None` instead of `0.10/0.12`.
- `pipeline/macro.py`: Verified that the elasticity-aware macro overlay correctly bases its unstressed baseline on the `dcf._resolve_assumptions(security)` method instead of hardcoding `0.09` WACC and `0.025` terminal growth.
- Checked `ui/gui.py` and `ui/menu.py` to confirm that sweeps successfully excised rogue `0.09` WACC fills.
- Checked FCFE value math, TI-89 value grid projection ranges (±6pp growth, ±2pp rate), and Damodaran `^TNX` rate scale normalization logic: all checks pass safely.

---

## Claude triage (2026-10-02)

**Treat this review with care.** It is thin, and it states that the ^TNX normalisation "passes
safely". That contradicts A1 finding 1, which was confirmed and fixed (see `agy-review-A1.md`).
Its other claims were checked one by one:

| AGY claim | Verdict | Action |
|---|---|---|
| `alpha_terminal.py:2241` mock fallback is "minor" | **Confirmed, and more serious than reported.** Any `ImportError` among the core imports (`alpha_terminal.py:94-105`) flips `_IAM_CORE` to False. The TUI then loads random prices, histories and scores (`_mock_load`) with no `--demo` flag. Only two panels show a "DEMO DATA (random)" banner (`:576`, `:1237`). This breaks CLAUDE.md rule 1. | **Open.** Gate `_mock_load` behind an explicit `--demo` flag; otherwise show the import error. Major. |
| WS4: `roe` / `roic` now propagate `None` | **Partly true.** `profile_builder.py:175-185` returns `None` and records the gap. `valuation/adaptive.py:30-31` `CompanyProfile.roe/roic` still default to `0.0`. | Still open as HANDOFF item 3. |
| WS4: `pipeline/macro.py` baseline comes from `dcf._resolve_assumptions` | Not contradicted by the code read; accepted. | None. |
| "All six A1 checks hold" | **Wrong** for check 5 (risk-free rate) and partly for check 1 (unlabelled 4.25% fallback). | See A1 triage. |

The WS4 classification table in `docs/FIX_PLAN.md` was not checked row by row in this review. A2
should be re-run with an instruction to cite file:line for every row.
