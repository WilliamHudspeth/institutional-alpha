# Contributing to Institutional Alpha

Thanks for helping build a better valuation engine for everyone!

---

## Quick Start

1. **Fork** the repo and create a feature branch: `git checkout -b feat/your-feature`
2. **Make your changes** and write tests (see Testing section below)
3. **Commit** with a [Conventional Commit](#commit-message-format) message
4. **Push** and open a PR to `main`
5. **Review** feedback; maintainers will check code quality and design

---

## Domain contributions (factors, data sources, methodology)

Proposing a new factor, a new data source adapter, or a methodology change? See
[`docs/COMMUNITY_CONTRIBUTIONS.md`](docs/COMMUNITY_CONTRIBUTIONS.md) — it covers the
evidence (backtest IC, contract tests) those PRs need beyond what's below.

## Commit Message Format

We follow **[Conventional Commits](https://www.conventionalcommits.org/)** to automate changelog generation. Pre-commit hooks enforce this. Full guide, including exactly where this is enforced and how it feeds release notes: [`docs/CONVENTIONAL_COMMITS.md`](docs/CONVENTIONAL_COMMITS.md).

### Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Type (required)

- **`feat`** — new feature or capability
- **`fix`** — bug fix
- **`docs`** — documentation only (README, guides, comments)
- **`test`** — test additions or improvements (no feature change)
- **`perf`** — performance improvement
- **`refactor`** — code refactoring (no feature or bug change)
- **`chore`** — build, deps, config (no user-facing change)
- **`security`** — security fix or hardening

### Scope (optional)

Component or module:
- `reasoning` — `iam.reasoning` module
- `lenses` — valuation lenses
- `factors` — scoring factors
- `pipeline` — 7-stage pipeline
- `data` — data layer
- `backtest` — backtest harness
- `ui` — user interface

### Subject (required)

- Imperative mood: "add feature" not "added feature" or "adds feature"
- No period at the end
- Lowercase first letter
- Under 50 characters (aim for 40)

### Body (optional)

- Explain *why*, not *what* (the diff shows the what)
- Wrap at 72 characters
- Separate from subject with a blank line

### Footer (optional)

Use for breaking changes and issue references:

```
BREAKING CHANGE: <description of breaking change>

Closes #123
```

---

## Commit Message Examples

### Good ✅

```
feat(reasoning): add business reality engine

Implements Engine #3 of the Seven-Engine architecture: a theory-first
reasoning layer that decodes business durability across six dimensions
(revenue quality, cash-flow durability, growth quality, capital
allocation, ROIC durability, fragility).

Closes #41
```

```
fix(factors): guard against empty roic_history in quality factor

Prevents IndexError when roic_history has fewer than 3 elements.
```

```
docs: update ROADMAP for Phase 2.5 completion

Engine #3 (Business Reality) now marked complete.
```

```
chore: bump pytest from 7.4.0 to 7.4.3

Security patch: fixes minor issue in test runner.
```

---

## Testing

Run tests locally:

```bash
python -m pytest -q
```

Target: **85% coverage** on new code.

---

## Code Review Standards

Reviews check for:
1. Correctness (tests pass, no edge-case crashes)
2. Consistency (uses existing patterns)
3. Clarity (readable, assumptions documented)
4. Bounds (all inputs validated)
5. Scope (doesn't add unnecessary abstraction)

---

## Development Setup

```bash
git clone https://github.com/WilliamHudspeth/institutional-alpha
cd institutional-alpha
pip install -e ".[dev]"
pre-commit install --hook-type commit-msg
python -m pytest -q
```

---

## Release Process (Phase 1.1)

Releases are **automated**:
1. Conventional commits trigger changelog entries
2. `release-drafter` generates release notes automatically
3. Semver tags (v0.4.2) created on `main`

**Cadence**: Patch every Friday, Minor every 6 weeks, Major quarterly.

Full cadence, versioning policy, and what's automated vs. still manual:
[`docs/RELEASE_SCHEDULE.md`](docs/RELEASE_SCHEDULE.md).

---

Welcome aboard! 🚀
