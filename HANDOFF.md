# Institutional Alpha: project handoff

> For the authoritative current state, rules and workflow, read **`CLAUDE.md`**. This file is a short
> orientation. It used to claim "v1.0 ready / functionally complete", which was never true and has
> been corrected (2026-10-06).

## 1. Current state: 0.4.0-rc1, under remediation
- **Valuation engine:** real and tested (about 1,660 tests; CI covers 3 OS × 3 Python; coverage gate 85%).
  It follows the owner's methodology:
  - Reverse DCF uses the consensus cost of equity (regression beta × US ERP).
  - Intrinsic uses the bottom-up cost of equity (Damodaran industry beta relevered × revenue-weighted ERP).
  - Marginal tax is weighted by revenue mix.
  - Terminal growth is capped at the risk-free rate.
  - Damodaran April 2026 reference data ships in `src/iam/data/reference/`.
- **No invented numbers:** missing data shows as n/a or a labelled default, and demo data appears only
  behind `--demo`.
- **Not done yet (do not describe these as working):**
  - **IC backtest:** it has never produced a measured result (`data/results/ic/ic_summary.txt` shows
    `n_obs: 0`), because the universe had no point-in-time fundamentals. An EDGAR-first point-in-time
    data layer is being built; see `docs/EDGAR_PLAN.md`.
  - **ML anomaly lens:** the IsolationForest is never fitted, so it cannot flag anything yet. It needs
    a training universe from the EDGAR layer.
  - **Geographic revenue mix for live tickers:** pending (EDGAR 10-K segments). Until then live tickers
    use the US ERP and tax rate.
  - **Survivorship-free backtest universe:** pending (owner decision in `docs/EDGAR_PLAN.md`, Phase D).

## 2. What exists
- **Front-ends:**
  - `launch_gui.py` (Streamlit);
  - `launch_tui.py [--demo]` (ANSI terminal; the TI-89 map plots a real growth × discount-rate value
    grid with a fair-value frontier);
  - the `institutional-alpha` launcher and the `iam-menu` text menu;
  - `python -m iam.backtest.cli dashboard` (local, read-only backtest results page).
- **Plugin architecture** (`src/iam/plugins`), **audit and governance logging** (`src/iam/audit`,
  `src/iam/governance`).
- **Desktop widget** (`src/desktop_widget/`, C# ASP.NET): a scaffold only. Whether to keep it is an open
  decision in `ROADMAP.md`.
- **Packaging:** `build.py` (PyInstaller) and `.github/workflows/build-artifacts.yml`.

## 3. Notes for the next developer or agent
- **Before changing code,** read `CLAUDE.md`, especially "Never weaken a test" and "No fabricated
  numbers".
- **PyInstaller:** if you add a runtime dependency, add it to the `--hidden-import` list in `build.py`,
  or the binaries will fail at start-up.
- **TUI ASCII layout** uses fixed-width spacing. Test the ANSI rendering after changing string lengths in
  `ti89_graph.py`.
- **History:** what was built, by whom, with which reviews, is recorded in
  `docs/ops/agy-coding-round1.md`. The original remediation plan is in `docs/FIX_PLAN.md`.
