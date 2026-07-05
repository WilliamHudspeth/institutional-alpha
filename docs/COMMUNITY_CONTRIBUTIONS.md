# Community Contributions

This is for contributions specific to institutional-alpha's domain — factors, data
sources, and methodology — beyond the mechanics already covered in
[`CONTRIBUTING.md`](../CONTRIBUTING.md) (setup, commit format, generic PR flow).

**Philosophy** (from `ROADMAP.md` Phase 1.1): this tool is for retail and institutional
users alike. Open development — public roadmap, transparent triage, community-proposed
factors — is how it earns trust as something other than a black box.

---

## Ways to contribute

### 1. Factor proposals

A new factor is a claim that some measurable signal predicts return or risk. Claims
need evidence, not just code.

To propose one:

1. Implement the `Factor` ABC (`src/iam/factors/base.py`) — one method:
   ```python
   def compute(self, security: Security) -> FactorContribution
   ```
   `value` normalized to `[-1, 1]` (or `[0, 1]` with `is_penalty = True` for a penalty
   factor), `confidence` in `[0, 1]`, `components` populated for auditability.
2. Add unit tests under `tests/` covering the normal case, missing-data degradation, and
   boundary clamping — follow the pattern in existing factor tests (e.g. `tests/unit/`).
3. Run it through the backtest harness (`src/iam/backtest/`, `python -m iam.backtest.cli
   backtest` — see `docs/REAL_DATA_BACKTEST_STRATEGY.md`) and include in the PR:
   - Information Coefficient (IC) with and without the new factor
   - Correlation with existing factors (a factor redundant with an existing one at
     >0.80 correlation needs justification for why it's additive, not just noise)
4. Document it in `docs/factors.md` in the same table format as the existing entries
   (sub-components + default weights).
5. PR title: `feat(factors): add <name> factor` (see
   [`CONVENTIONAL_COMMITS.md`](CONVENTIONAL_COMMITS.md)).

A factor PR without backtest evidence will be asked for it before review proceeds —
this isn't gatekeeping, it's the same bar the existing 10 factors were held to.

### 2. Data source adapters

The backtest data layer is pluggable (`src/iam/backtest/sources/base.py`): implement the
`DataSource` ABC's four methods — `fetch_price`, `fetch_debt`, `download_history`,
`is_available` — and it composes into the existing fallback chain
(`CompositeDataSource` / `default_chain()`) with no changes to snapshots or the runner.

Existing adapters to use as reference: `yfinance_source.py`, `stooq_source.py`,
`fmp_source.py`, `tiingo_source.py`, `sec_edgar_source.py`.

To add one:

1. Implement `DataSource` in a new `src/iam/backtest/sources/<name>_source.py`.
2. Add it to `tests/test_backtest_sources.py`-style coverage (mocked network calls —
   no adapter test should hit a live API in CI).
3. Note API key requirements, rate limits, and free-tier constraints in the module
   docstring — a source that silently rate-limits under load is worse than one that's
   absent.
4. PR title: `feat(backtest): add <name> data source adapter`.

### 3. Documentation & educational material

Explainers, methodology write-ups, validation reports, worked examples. These land under
`docs/` and use `docs:` as the commit type regardless of file size or effort — the
Conventional Commits type describes the category, not the weight of the change.

### 4. Methodology discussions

Open questions about *how the model should work* (not bug reports, not feature
requests) belong in GitHub Discussions, not Issues — e.g. "should the macro regime
factor use the analytics 6-regime system or the pipeline 4-regime system for X?" (see
`docs/ARCHITECTURE.md` §4 for why there currently are three parallel regime systems).
Discussions that converge on a concrete change get filed as an Issue referencing the
thread.

---

## Issue labels & triage

| Label | Meaning |
|---|---|
| `bug` | Something is broken |
| `feature` | New capability request |
| `research` | Methodology/factor/backtest question |
| `documentation` | Docs gap or correction |
| `help-wanted` | Maintainer-confirmed, open for anyone to pick up |

**Target triage SLA** (aspirational — not yet enforced by tooling):
- `bug` / anything security-adjacent: response within 24 hours
- `feature`: response within 1 week

If an issue is closed without a fix, the closing comment should say why (won't-fix,
duplicate, out of scope) — silence erodes trust faster than a "no."

Issue templates live in `.github/ISSUE_TEMPLATE/` (bug report, feature request, factor
proposal, data source adapter) to route contributions into the right shape from the start.

---

## What maintainers check on a community PR

Same bar as [`CONTRIBUTING.md`](../CONTRIBUTING.md)'s Code Review Standards, plus for
domain contributions specifically:

1. **Evidence, not assertion** — a factor claim needs backtest numbers; a data source
   claim needs a mocked test proving the contract is honored under failure (rate limit,
   timeout, malformed response).
2. **No silent fallbacks** — a data source that fails should raise `DataSourceError`,
   not return a plausible-looking default.
3. **Consistency with existing conventions** — normalization ranges, confidence
   semantics, and naming should match `docs/ARCHITECTURE.md` and `docs/factors.md`,
   not invent a parallel convention.

---

## References

- [`../CONTRIBUTING.md`](../CONTRIBUTING.md) — setup, testing, generic PR flow
- [`CONVENTIONAL_COMMITS.md`](CONVENTIONAL_COMMITS.md) — commit/PR title format
- [`RELEASE_SCHEDULE.md`](RELEASE_SCHEDULE.md) — how merged PRs become releases
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — module map, factor/lens contracts
- [`factors.md`](factors.md) — existing factor inventory and weights
- [`REAL_DATA_BACKTEST_STRATEGY.md`](REAL_DATA_BACKTEST_STRATEGY.md) — backtest validation gates
