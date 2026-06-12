# Damodaran Laws Constraint Layer

**Module**: `src/iam/laws/`
**Status**: Implemented and wired into the valuation pipeline
**Roadmap**: Phase 2.5 — Reasoning-Engine Evolution ("Damodaran Laws constraint layer")

---

## Philosophy

The laws are **theory-first consistency checks that flag fragile analyses** —
they never invent numbers. A valuation whose assumptions break the laws is not
auto-corrected; it is *interrogated*: the verdict keeps its rating but loses
conviction, and the analyst sees exactly which assumption needs a story.

The registry evaluates the assumptions the Stage 3 intrinsic DCF *actually
used* (`ValuationResult.assumptions`), optionally cross-referenced with the
Stage 1 reverse-DCF implied expectations, against the security's own
fundamentals. It is a pure function — no I/O, no mutation — matching the
lens/elasticity contract.

Each check returns one of four statuses:

| Status | Meaning |
|---|---|
| `PASS` | Assumptions are internally consistent with the law |
| `FLAG` | Assumptions need an explanation (e.g. an unexplained moat) |
| `VIOLATION` | Assumptions are internally inconsistent with valuation theory |
| `NOT_EVALUATED` | Inputs too sparse to check — never penalised |

---

## The Five Laws

### LAW 1 — Narrative must match numbers

High growth + **shrinking** margins is a reinvestment story (probably valid).
High growth + **expanding** margins is a competitive-moat story that demands an
explanation. The check reads the operating-margin trend (newest observation vs
the trailing mean, ≥ 3 points required) and, when forecast growth ≥ 12% with
margins expanding ≥ 2pp, looks for a supplied moat narrative
(`qualitative["moat"]`, `"moat_narrative"`, or `"narrative"`). No story → FLAG.

### LAW 2 — Growth requires reinvestment

`g = ROIC × reinvestment_rate` is a law. Sustainable growth is computed from
the mean of the last 5 ROIC observations and a reinvestment rate resolved in
priority order:

1. explicit `qualitative["reinvestment_rate"]`
2. accounting estimate `1 − FCF/NI` (the share of earnings not converted to
   free cash flow — a coarse proxy for (capex − D&A + ΔWC)/NOPAT)
3. the reverse-DCF *market-implied* rate (noted as the market's assumption,
   not the business's track record)

Forecast growth more than **3pp** above sustainable growth → FLAG; more than
**8pp** above → VIOLATION.

### LAW 3 — Terminal growth ≤ risk-free rate

Already enforced by the input guards (`iam.validation.financial_guards`);
folded into the registry so every analysis carries the check in its audit
trail. Terminal growth above the risk-free rate
(`qualitative["risk_free_rate"]`, default 4.3%) → VIOLATION; within 25bps
below it → FLAG ("at the ceiling, no headroom for estimation error").

### LAW 4 — Excess returns fade

High ROIC attracts competition → margin pressure → ROIC mean-reversion. The
platform's two-stage DCF holds growth flat across the horizon, so high excess
returns (ROIC − WACC ≥ 5pp) combined with high flat growth (≥ 12%) over a long
horizon (≥ 8y) is an implicit *no-fade* assumption → FLAG. When the excess
return is extreme (≥ 10pp) and growth ≥ 15% for ≥ 8 years → VIOLATION.

The expected glide path is made explicit via `excess_return_fade_path()`:
linear fade over 8 years toward `WACC + 10% × excess` (truly durable
franchises retain a sliver of excess return — assuming a full fade would
double-penalise wide-moat names Law 1 already interrogates).
`fade_adjusted_growth()` reports the sustainable growth at the end of the
glide path: the rate the model should be converging toward.

### LAW 5 — Risk is not double-counted

Risk lives in the cash flows **or** the discount rate, never both. The check
compares the WACC against the platform baseline (9%) and forecast growth
against the historical revenue CAGR (≥ 3 observations):

- WACC > baseline + 2pp **and** growth > 5pp below history → FLAG
  (risk priced in both channels)
- WACC < baseline − 2pp **and** growth > 5pp above history → FLAG
  (optimism priced in both channels)

This law only ever flags — it is a heuristic on direction, not a theorem.

---

## Conviction degradation

`LawReport.conviction_multiplier` maps the aggregate onto `[0.5, 1.0]`:

```
multiplier = 1.0 − 0.15 × violations − 0.05 × flags    (floored at 0.50)
```

The Stage 7 verdict consumes it:

- multiplier ≤ 0.85 → confidence band downgraded one level
- multiplier ≤ 0.70 → downgraded two levels

`NOT_EVALUATED` checks never penalise: "couldn't look" is distinct from
"looked and failed". Every non-pass check lands verbatim in the verdict
notes (`[LAW n VIOLATED] …` / `[LAW n FLAGGED] …`), the pipeline summary,
and `PipelineReport.explain()`.

---

## Usage

```python
from iam.laws import DamodaranLawRegistry

report = DamodaranLawRegistry().evaluate(
    security,
    intrinsic_result.assumptions,     # what Stage 3 actually used
    implied=stage1_result.implied,    # optional reverse-DCF context
)
report.conviction_multiplier   # [0.5, 1.0] — feed the verdict layer
report.narrative               # one-line audit summary
report.violations / report.flags / report.passes / report.not_evaluated
```

The `ValuationPipeline` runs the registry automatically on every analysis and
attaches the result as `PipelineReport.law_report`.

---

## Design principles honored

- **No magic numbers** — every threshold is a documented module constant in
  `iam/laws/registry.py`.
- **Everything is auditable** — each check exposes the sub-values it used in
  `components` and its caveats in `notes`.
- **Degrade, don't crash** — missing data yields `NOT_EVALUATED`, never an
  exception, never a guess.
- **Reasoning, not numbers** — the laws temper a verdict; they do not veto or
  rewrite it.
