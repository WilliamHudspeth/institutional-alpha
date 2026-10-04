> **Historical (2026-10-02).** This is the original takeover prompt that produced `docs/FIX_PLAN.md`.
> It is kept as a record. Current state, rules and workflow are in `CLAUDE.md` and
> `docs/ops/agy-coding-round1.md`. Several findings and counts below are out of date.

# Institutional Alpha — Fix Plan Takeover Prompt for Claude Code

Paste everything below the line into Claude Code, started from `C:\Users\wshb\projects\institutional-alpha`
(or tell it: "Read docs/ops/fix-plan-prompt.md and follow it.").

---

You are taking over remediation of **institutional-alpha** (Python equity valuation + factor scoring engine; Streamlit GUI `src/iam/ui/gui.py`, TUI `src/iam/ui/alpha_terminal.py` via `launch_tui.py`). Two independent reviews (Claude + AGY/Antigravity) agree on the core problem: **the valuation engine is real and well tested, but the app's outputs can't be trusted.** UIs show verdicts built from missing or random data, the backtest has never produced a real IC, and the docs overclaim. Your job is to **plan first, get my approval, then fix**, using AGY and every model tier available to you as efficiently as possible.

## Ground rules (non-negotiable)

1. **Truth over features.** Never add a fallback that fabricates numbers. Missing data means an explicit "insufficient data" state, never a default that looks computed. No random values anywhere outside an explicit `--demo` mode with a visible banner.
2. **Plan gate.** Phase 0 ends with a written plan (`docs/FIX_PLAN.md`). **Stop and wait for my approval** before changing any source file.
3. **Branch per workstream** (`fix/p0-crashes`, `fix/ui-truthfulness`, …) off `main`. Small commits, conventional-commit messages. **Never push or open PRs without asking me.**
4. **Every fix ships with a test** that would have failed before it. Full suite must stay green: `pytest -q` (install test extras first: `pip install -e ".[test]"`; `hypothesis` is already declared there).
5. **Verify before you trust.** The findings below are leads, not facts. Confirm each against the code (file:line) before acting. Two of them (marked ⚠) are already known to be partly wrong.
6. Windows machine: use PowerShell or Git Bash as appropriate. Don't run runtime `pip install` from app code.

## Model routing (be efficient)

Use subagents (Agent tool with `model`) and pick the cheapest model that can do each job well. Run `/model` first to see which models are available, then map them like this:

| Work | Model tier | Examples |
|---|---|---|
| Planning, architecture calls, adversarial review of diffs, financial-modeling correctness | **Strongest (Opus-class)**, the main session | Write FIX_PLAN.md; review the backtest point-in-time redesign; final review of each branch |
| Implementation of well-specified fixes | **Mid (Sonnet-class)** subagents, one per workstream, in parallel **git worktrees** | Remove mock fallbacks; wire `battlefield.py`; GUI verdict card |
| Mechanical / search / bulk | **Fast (Haiku-class)** subagents | `ruff --fix`, finding all `except Exception: pass`, updating test counts in docs, grep sweeps, dependency audits |
| Independent second opinion | **AGY CLI** | Review FIX_PLAN.md; review each branch diff; challenge financial-modeling choices |

Efficiency rules: give each subagent a self-contained brief (files, the exact defect, the acceptance test, "don't touch other files"). Parallelize independent workstreams. Don't have two agents edit the same file at once. Keep the main session for decisions and review, not bulk reading.

## Using AGY

1. Run `agy --help` first and find its non-interactive or headless prompt mode. **Don't guess flags.** If it has no headless mode, write the review prompt to a file and tell me to run it, then continue.
2. Use AGY as a **reviewer, not an implementer**, so the two systems don't edit the same tree:
   - after `docs/FIX_PLAN.md` is drafted, ask AGY to critique it (missing items, wrong order, effort estimates);
   - after each workstream branch is green, give AGY `git diff main...<branch>` and ask for bugs, regressions and anything still fabricated.
3. Where AGY and you disagree, record both positions in FIX_PLAN.md under "Disagreements" with your recommendation. Don't silently pick one.

## Consolidated findings (verify each)

### P0 — crashes and fabricated output
- **F821 crash bugs:**
  - `src/iam/ui/cli.py:236, 239, 247`: `get_settings` is not imported, so the CLI dies on every run.
  - `src/iam/ui/gui.py:456`: `sec` is undefined (should be `security`). The error is swallowed, so the ML panel always says "unavailable".
  - `src/iam/pipeline/orchestrator.py:100`: `JustifiedPremiumResult` is not imported.
  - Add `ruff check src --select F` as a blocking CI step.
- **GUI valuing an empty security:** `gui.py` ~201-205. When the fetch fails it builds `Security(ticker=ticker)` and still renders a verdict ("High cost of equity", $0.00 PWEV). Stop with a clear error instead, and require price, shares and revenue before any verdict.
- **TUI mock verdicts:** `alpha_terminal.py:349-391` (`_MockScore`, `_MockVerdict` use `random.choice` / `random.uniform`), plus the `_mock_load` path at ~662. The watchlist prices for non-active tickers and the sparklines are random too. Move all of this behind `--demo` with a banner.
- **Hardcoded inputs presented as data:**
  - `src/iam/data/providers/yfinance_adapter.py:341-345`: payout, ROE, ROIC and tax are fixed at 0.0 / 0.12 / 0.10 / 0.21.
  - `:357`: ROA is labelled as ROIC.
  - `gui.py:169-170`: PBO and DSR fall back to 0.042 and 1.48.
  - `gui.py:517`: expected return is a hardcoded 4.3% + 5%.
  - Compute these or mark them missing, and tag every defaulted input in the output.

### P1 — unwired or faked features
- **Valuation Battlefield** (confirmed): `orchestrator.py` ~575-586 builds `ExpectationsBattlefieldEngine` from hardcoded 0.2/0.5/0.3 probabilities and 0.8×/1.2× multipliers, while the real ceteris-paribus attribution in `src/iam/pipeline/battlefield.py` (`attribute_disagreement`, `build_battlefield`) is never imported. Wire the real one in.
- **⚠ Thesis drift constraints:** `orchestrator.py` ~595-599 falls back to `data/constraints/{ticker}.example.yml`.
  - AGY's claim that this "applies Apple's constraints to every security" is **wrong**: it uses the same ticker's example file, and only `MSFT.example.yml` exists.
  - The real issue is that example or template constraints are treated as the user's thesis. Require a real `{ticker}.yml`, or label the output "example thesis".
- **ML anomaly lens:**
  - `src/iam/ml/ml_lens.py` never calls `fit()`, so `anomaly_forest.py` always returns "normal" and the orchestrator's confidence haircut never fires.
  - Fit it on the universe cross-section, or remove the feature and the HANDOFF claim.
  - Add `scikit-learn` to dependencies and fix `tests/unit/test_ml_anomaly.py::test_anomaly_detector_with_sklearn`.
- **TI-89 "3D wireframe" (TUI):** `src/iam/ui/ti89_graph.py:16+` is a hardcoded ASCII picture with three numbers inserted into it. It also raises `SyntaxWarning: invalid escape sequence '\ '`, because the f-string lines aren't raw. Either build a real projection or rename it honestly as a "summary card". Fix the escapes either way.
- **Ghost dependency:** `textual` is installed by `launch_tui.py:18-22` and `bootstrap.py:57`, but the TUI doesn't use it; it's raw ANSI/termios. Remove it, or migrate to it deliberately.
- **CLI:** fix it, or fold it into the TUI.

### P1 — backtest validity (prerequisite for the v0.4.0 "empirical IC" milestone)
- **Look-ahead bias:** `src/iam/backtest/snapshots.py:126-144`. Only price and debt are point-in-time; revenue, margins, ROIC and **shares outstanding** come from today's pull, and missing shares default to 1e9.
- **Survivorship bias:** `data/universe/sp100.json` is frozen at 2024-12-31, but the backtest starts in 2018-01.
- **Row loss:**
  - `ic_runner.py:53`: `dropna(subset=["score","fwd","mcap"])` empties cross-sections.
  - `:138-161`: month-ends that fall on a weekend raise `KeyError` and those rows are dropped.
  - Failed fetches are cached permanently, with debt stored as 0.0.
- **Never run for real:**
  - No real IC has ever been produced: `data/results/ic/` is NaN or empty.
  - The v0.3.5 CSV is synthetic (`hit_rate = 0.5 + 0.4·IC` on every row).
  - The only IC test mocks `score`, `build_snapshot` and the process pool.
- **⚠ Data-source disagreement:**
  - Claude proposed SEC EDGAR for point-in-time fundamentals.
  - AGY says an EDGAR XBRL parser is a sinkhole and suggests commercial APIs.
  - The repo already has tiered sources (FMP, Tiingo, SEC EDGAR; `backtest/sources/sec_edgar_source.py` exists).
  - Evaluate **FMP historical statements with filing dates** as the middle path, then EDGAR's companyfacts JSON (not raw XBRL) as the fallback.
  - Put a recommendation with effort estimates in the plan.
- **Deliverable:** one real IC run at 1/3/6/12 months with coverage stats per month, committed with its manifest and shown in the GUI's Research Integrity panel. If coverage is too thin for a valid IC, say so plainly rather than imputing your way to a number.

### P2 — UX, hygiene, docs
- **GUI fixes:**
  - The stray `</tbody>` renders above the scenario table.
  - The verdict card describes the cost of equity instead of giving Buy/Hold/Sell with current price, upside vs PWEV and the conviction band.
  - The "WACC" card shows the cost of equity.
  - Hide always-empty panels until they have data.
  - Use one Streamlit theme.
  - Replace `use_container_width`.
  - Run one pipeline per click, not both `Orchestrator` and `ValuationPipeline`.
- **⚠ Terminals:**
  - AGY disagreed with "collapse 4 terminals to 1", but that was about GUI vs TUI. The GUI and TUI stay separate.
  - The proposal is to consolidate the four **terminal** front-ends (`alpha_terminal`, `institutional_terminal`, `menu`, `ia_shell`) into one TUI.
  - Also delete `ui/modern_terminal.py` (unused) and the duplicate `learning_engine.py`.
- **Exceptions and logging:**
  - Narrow the 135 broad `except Exception` blocks (35 silently pass); log at warning level.
  - Move the audit logger out of `score()`, give it an absolute path and a single instance across processes.
- **Packaging:**
  - `pyproject.toml` still says version 0.2.0a0, author "Your Name", URLs `YOUR_USERNAME`.
  - Make `version.py` the single source of truth.
  - `streamlit` and `scikit-learn` are missing from dependencies; `mutmut` is listed as a runtime dependency.
  - Stop committing `config.yml` and `coverage.xml`.
- **Docs:**
  - Rewrite `HANDOFF.md`: it claims "v1.0, functionally complete" and that only SEC/GDPR work remains.
  - Fix the README test count (says 502; there are ~1,169) and remove its duplicate "Layer 2" section.
  - Tick ROADMAP Phase 4 Kelly, risk parity, sector rotation and macro hedging as done (implemented July 6).
  - Move Phase 1.5b Legal (111 items) and most of Phase 1.5 to `docs/if-commercialized.md`.
  - Rule: every ROADMAP checkmark links to a test or commit.

## Phase 0 deliverable: `docs/FIX_PLAN.md`

1. **Baseline:** commit SHA, `pytest -q` result, `ruff check src` and `mypy src` counts.
2. **Verified findings table:** finding, file:line, confirmed / partly / wrong, and evidence.
3. **Workstreams:** for each one, its scope, branch name, files touched, acceptance tests, model tier, and whether it can run in parallel.
4. **Order and dependencies:** P0 first. The backtest work gates the IC run, and the IC run gates any "v0.4.0" claim.
5. **Disagreements:** you vs AGY, with your recommendation.
6. **Out of scope** (deferred) and **open questions for me.**

Then **stop and ask me to approve.** After approval, run the workstreams, checkpoint with me after P0 lands, and finish each branch with a summary of what changed, the test evidence, and AGY's review verdict.
