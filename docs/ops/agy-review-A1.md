# AGY review A1

This review examines commits 25203d6, fabec4a, f6b420e, and 6b745ce to verify the elimination of fabricated numbers, validate new valuation logic, and check test rigour. While the transition away from mocked logic is largely successful, several critical flaws remain. The new risk-free rate normalisation inadvertently inflates yields under 2.5%, the `mismatch_score` severely penalizes massive undervaluation by interpreting a large margin of safety as a penalty, and the TI-89 map stretches blindly to extreme market points, destroying resolution. Finally, `value_grid.py` and `damodaran.py` both still silently default missing parameters without labeling them as defaults.

| Severity (blocker/major/minor) | File:line | Finding | Suggested fix |
| --- | --- | --- | --- |
| major | `src/iam/valuation/value_grid.py:55` | Silently defaults `high_growth_years` to 10 if missing. | Return `None` if missing or label explicitly as a default in the UI. |
| major | `src/iam/data/damodaran.py:218` | Returns a hardcoded `0.0425` if the ^TNX quote fails, without labelling it as a default. | Raise an error, return `None` (shows "n/a"), or add an explicit "defaulted" label to the pipeline report. |
| major | `src/iam/pipeline/battlefield.py:124` | `mismatch_score` penalizes massive margin of safety (extreme undervaluation) by capping out at 100 and downgrading confidence. | Use parameter-space distance `abs(winner.value_market - winner.value_intrinsic) / abs(winner.value_intrinsic)` or only calculate penalty if overvalued (`target_value > base_value`). |
| minor | `src/iam/valuation/value_grid.py:36` | Stretching grid axes to include extreme `extra` points shifts the grid so `base_case` no longer sits perfectly on a grid intersection, and destroys local resolution. | Cap the widening (e.g., clamp `extra` to `center ± 15%`) or plot the market point out-of-bounds without shifting `lo` and `hi`. |
| blocker | `src/iam/data/damodaran.py:210` | `while v > 0.25: v /= 10.0` inflates legitimate small yields. A quote of `2.0` (2%) becomes `0.20` and loop terminates, returning 20%. | Check if `v > 10.0` or similar, or just check `v > 1.0` before scaling, or rely on an absolute threshold (e.g., `v /= 100` if `v > 1.0`). |
| major | `tests/test_risk_free_rate.py:45` | `test_rate_handles_every_tnx_scale` is cherry-picked; it uses `4.31` which steps perfectly down over 0.25. It would fail on `2.0`. | Use a more comprehensive set of parameters (e.g., `[43.1, 4.31, 2.0, 0.15]`) to ensure the normalisation covers all real-world edge cases. |

### 1. Is any number shown to the user still invented or defaulted without a label?
Yes. `value_grid.py` silently defaults `high_growth_years` to 10 if the assumption is missing, and `damodaran.py` silently falls back to a hardcoded `0.0425` (4.25%) risk-free rate if the live quote fetch fails. Neither is labelled as a defaulted assumption when surfaced to the user.

### 2. Battlefield
- **Does `fcfe_value_fn` match the FCFE engine's maths?** Yes. It wraps `_present_value_two_stage` which is exactly the mathematical core of the reverse DCF and FCFE engines.
- **Is `mismatch_score` sound?** No. It computes `abs(target - base) / base * 100`. If a stock is massively undervalued (price is far below intrinsic value), this formula treats the huge margin of safety as an extreme "mismatch" and downgrades the verdict to `SPECULATIVE_BUY`. 
- **Propose something better:** Instead of penalizing undervaluation, `mismatch_score` should measure the gap in the *parameter* space of the key disagreement. A concrete alternative: `abs(winner.value_market - winner.value_intrinsic) / abs(winner.value_intrinsic)`. Alternatively, only calculate the price mismatch penalty when the stock is overvalued (`if target_value > base_value`).

### 3. Drift
- **Is it right that example thresholds never move the verdict?** Yes. The code correctly sets `degrade_levels` to 0 when `is_example` is true. Example bounds are just placeholders and should never incorrectly downgrade the user's actual thesis verdict.

### 4. TI-89 map
- **Are the axis ranges sensible?** No, not entirely. While ±6pp for growth and ±2pp for discount rate around the base case are sensible local defaults, blindly widening the grid to include an extreme market point is flawed. A fixed 9-point grid stretched to cover an extreme outlier (like -50% implied growth) destroys the map's local resolution around the base case. Furthermore, widening the bounds shifts the grid intervals such that the `base_case` mathematically falls between grid cells, breaking the visual coordinate mapping.

### 5. Risk-free rate
- **Is the ^TNX scale normalisation safe?** Absolutely not. The logic `while v > 0.25: v /= 10.0` is broken for yields under 2.5% (like 2.0%). If the quote is `2.0`, `v > 0.25` evaluates to true once, making it `0.20`. The loop then terminates and returns `0.20`, interpreting a 2.0% yield as a massive 20% risk-free rate. 

### 6. Are any tests weak or tautological?
Yes. `test_rate_handles_every_tnx_scale` in `tests/test_risk_free_rate.py` uses `@pytest.mark.parametrize("quoted", [43.1, 4.31, 0.431, 0.0431])`. This is tautological and cherry-picked because `4.31` cleanly steps down over the `0.25` threshold at every division. If the test had included `2.0` (or `0.15`), it would have failed immediately. Additionally, in `test_value_grid.py`, `test_grid_base_matches_intrinsic_base_case` only tests the `grid.base[2]` tuple value, rather than verifying if the base point actually lies on the constructed axis grid.

---

## Claude triage (2026-10-02)

AGY ran headless (`agy -p --mode plan`) in a throwaway git worktree, because headless mode cannot
prompt for shell permission. It wrote this file into that worktree despite `--mode plan`; the copy
here is its stdout. Each finding was checked against the code before acting.

| # | AGY finding | Verdict | Action |
|---|---|---|---|
| 1 | `damodaran.py:210` ^TNX loop inflates small yields (blocker) | **Confirmed, and worse than reported.** A live check shows Yahoo quotes ^TNX in percent (5.24 = 5.24%; mid-2020 history reads 0.68). `markets.py` divided every rate by 10 on the stale assumption that Yahoo quotes x10, then the loop divided again only while > 0.25. Every 10-year yield under 2.5% (most of 2012–2021) came out 10x too high: 0.68% became 6.8%. The TUI rates tape also showed 0.52% for a 5.24% yield. | **Fixed.** `markets.py` keeps Yahoo rates in percent; `get_risk_free_rate` converts once (`pct / 100`) and falls back to the baseline outside (0, 20%]. Failing-first tests in `tests/test_risk_free_rate.py`. |
| 2 | `test_rate_handles_every_tnx_scale` is cherry-picked (major) | **Confirmed.** | **Replaced** with percent-scale cases including 2.0% and 0.68%, plus implausible-quote fallback cases. |
| 3 | `value_grid.py:55` silently defaults `high_growth_years` to 10 (major) | **Confirmed, but it doesn't reach users today.** `engine/damodaran.py:138` always sets the horizon. It was still a hidden second copy of the constant. Severity: minor. | **Fixed.** The horizon is now a required input (the grid returns `None` without it). Failing-first test `test_no_grid_without_high_growth_years`. |
| 4 | `damodaran.py:218` 4.25% fallback is unlabelled (major) | **Confirmed.** `MacroBaselines.risk_free_rate` carries no source flag, so an offline run uses 4.25% in WACC without saying so. | **Deferred** to the remaining-defaults batch (HANDOFF item 3, together with the orchestrator's 0.043 rf fallback). Both need one provenance field threaded through the macro state. |
| 5 | `battlefield.py:124` `mismatch_score` penalises deep undervaluation (major) | **Partly disputed. The behaviour is real; whether it is wrong is a design call.** A BUY with price at 40% of intrinsic gets mismatch 60 and drops to SPECULATIVE_BUY (`verdict.py:133`). A gap that large usually means the model is missing something the market sees, so lower conviction is defensible. AGY's suggested formula `|V_market − V_intrinsic| / |V_intrinsic|` is the same quantity as the current one, so it doesn't change the behaviour. A real alternative is to measure the gap in parameter space (implied vs intrinsic growth, in pp). | **Owner decision** (it changes a verdict penalty). Recorded under FIX_PLAN Q3. No code change. |
| 6 | `value_grid.py:36` widening to an extreme market point kills resolution (minor) | **Confirmed.** With implied growth of −50%, nine steps over about 56pp gives about 7pp per cell. | **Deferred** to the ROADMAP "Valuation Terrain → Consistent axes" item: clamp the widening and draw out-of-range market points at the edge with an arrow. |
| 7 | `test_grid_base_matches_intrinsic_base_case` checks only the value, not the axis position | **Agreed, minor.** | Folded into item 6. |
| — | Checks 2a (FCFE maths) and 3 (example drift thresholds) | Agree with AGY: both correct. | None. |
