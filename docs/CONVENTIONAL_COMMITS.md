# Conventional Commits Guide

Canonical commit/PR-title convention for institutional-alpha. [`CONTRIBUTING.md`](../CONTRIBUTING.md)
and [`GOVERNANCE.md`](../.github/GOVERNANCE.md) both summarize this; this file is what they
point to for the full picture, including exactly where it's enforced.

We follow [Conventional Commits](https://www.conventionalcommits.org/) because it's the
input to two pieces of live automation: the changelog and the version bump. Get the
type wrong and a security fix quietly lands in the "Chores" section of the release notes.

---

## Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

## Type (required)

| Type | Use for | Release Drafter category |
|---|---|---|
| `feat` | New feature or capability | 🎉 Features |
| `fix` | Bug fix | 🐛 Bug Fixes |
| `security` | Security fix or hardening | 🚨 Security |
| `docs` | Documentation only | 📚 Documentation |
| `perf` | Performance improvement | ⚡ Performance |
| `refactor` | Code restructuring, no behavior change | 🔧 Refactoring |
| `test` | Test additions/improvements only | ✅ Tests |
| `chore` | Build, deps, config — no user-facing change | 🏗️ Chores |

This mapping is not just convention — it's `.github/release-drafter.yml`'s `autolabeler`
config, which regexes the PR title (`/^feat(\(.+\))?:/i`, etc.) to apply a GitHub label,
which then buckets the entry in the drafted release notes. Get the prefix wrong and the
entry lands in the wrong section (or none, if it doesn't match).

## Scope (optional)

Use the subpackage under `src/iam/` the change lives in — matches `docs/ARCHITECTURE.md`'s
subpackage inventory:

`analytics`, `api`, `arbitration`, `assumptions`, `audit`, `backtest`, `compliance`,
`config`, `data`, `elasticity`, `engine`, `factors`, `governance`, `integration`, `laws`,
`learning`, `lenses`, `monitoring`, `pipeline`, `portfolio`, `reasoning`, `reports`,
`thesis`, `ui`, `validation`, `valuation`

For cross-cutting changes, omit the scope rather than guessing.

## Subject (required)

- Imperative mood: "add feature", not "added feature" or "adds feature"
- Lowercase first letter, no trailing period
- Under 50 characters (aim for 40)

## Body (optional)

- Explain *why*, not *what* — the diff already shows what changed
- Wrap at 72 characters

## Footer (optional)

```
BREAKING CHANGE: <description>

Closes #123
```

---

## Where this is enforced

Two independent checkpoints, both currently live:

1. **Locally, per commit** — `.pre-commit-config.yaml` runs `conventional-pre-commit`
   at the `commit-msg` stage. Install with:
   ```bash
   pre-commit install --hook-type commit-msg
   ```
2. **In CI, on the PR title** — `.github/workflows/pr-title.yml` runs
   `amannn/action-semantic-pull-request` on every `opened`/`edited`/`synchronize` event.
   This is what actually feeds Release Drafter, since the drafted notes are built from
   merged PR titles, not individual commit messages. **If your PR squashes multiple
   commits, the PR title is what must be correct** — non-conforming intermediate commits
   inside the PR don't block the merge, but a non-conforming PR title does block CI.

---

## Examples

### Good

```
feat(reasoning): add business reality engine

Implements Engine #3 of the Seven-Engine architecture: a theory-first
reasoning layer that decodes business durability across six dimensions.

Closes #41
```

```
fix(factors): guard against empty roic_history in quality factor

Prevents IndexError when roic_history has fewer than 3 elements.
```

```
security(data): validate ticker input before shell-adjacent cache path build

Untrusted ticker strings were interpolated into a cache filename;
an adversarial value could traverse outside data_cache/.
```

```
docs: update ROADMAP for Phase 1.1 release management docs
```

### Bad (and why)

```
Update stuff
```
No type, no imperative mood, no information — release notes would show "Update stuff"
under no category and it'd be dropped by the drafter.

```
feat: fixed the bug in the DCF calc
```
Wrong type — this is a `fix`, not a `feat`. It'll land in 🎉 Features, misleading anyone
scanning the changelog for bug fixes.

```
chore: rewrite the composite scoring engine to use a new weighting model
```
Wrong type for the size of the change — a new weighting model is user-facing behavior,
not a chore. Should be `feat` or, if it changes existing output, called out with a
`BREAKING CHANGE:` footer.

---

## References

- [`RELEASE_SCHEDULE.md`](RELEASE_SCHEDULE.md) — cadence this convention feeds
- [`COMMUNITY_CONTRIBUTIONS.md`](COMMUNITY_CONTRIBUTIONS.md) — contribution workflow
- [`../CONTRIBUTING.md`](../CONTRIBUTING.md) — quick-start contributor guide
- [`../.github/GOVERNANCE.md`](../.github/GOVERNANCE.md) — merge gate policy
